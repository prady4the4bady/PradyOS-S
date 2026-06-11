"""Phase 15A — Sovereign Scheduler.

Cron-style recurring campaign launcher with:
  - Pure-stdlib cron parser (minute hour dom month dow)
  - Priority queue semantics
  - SLA-aware dispatch metadata
  - Background tick thread
  - EventBus integration for "scheduler.job.fired" events

No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import copy
import datetime
import threading
import time
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Cron parser
# ---------------------------------------------------------------------------


def _parse_field(field: str, lo: int, hi: int) -> list[int]:
    """Expand a single cron field into a sorted list of matching integers.

    Supports:
      * — all values in [lo, hi]
      */N — every N-th value starting from lo
      N — single integer (must be in [lo, hi])
    """
    if field == "*":
        return list(range(lo, hi + 1))
    if field.startswith("*/"):
        step = int(field[2:])
        if step <= 0:
            raise ValueError(f"Invalid step in cron field: {field!r}")
        return list(range(lo, hi + 1, step))
    val = int(field)
    if not (lo <= val <= hi):
        raise ValueError(f"Cron field value {val} out of range [{lo}, {hi}]")
    return [val]


def _parse_cron(cron_expr: str) -> dict[str, list[int]]:
    """Parse a 5-field cron expression and return expanded field sets.

    Fields: minute hour dom month dow
    Ranges: minute 0-59, hour 0-23, dom 1-31, month 1-12, dow 0-6 (Sun=0)
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Cron expression must have exactly 5 fields, got {len(parts)}: {cron_expr!r}"
        )
    minute_f, hour_f, dom_f, month_f, dow_f = parts
    return {
        "minute": _parse_field(minute_f, 0, 59),
        "hour": _parse_field(hour_f, 0, 23),
        "dom": _parse_field(dom_f, 1, 31),
        "month": _parse_field(month_f, 1, 12),
        "dow": _parse_field(dow_f, 0, 6),
    }


def next_run_after(cron_expr: str, after_ts: float) -> float:
    """Return the next unix timestamp >= after_ts that matches cron_expr.

    Scans minute-by-minute up to 1 year ahead; raises RuntimeError if
    no match is found within that window (should never happen with valid
    expressions).
    """
    fields = _parse_cron(cron_expr)
    # Start from the next whole minute >= after_ts
    dt = datetime.datetime.fromtimestamp(after_ts, datetime.timezone.utc).replace(tzinfo=None)
    # Advance to next minute boundary (ceil to next minute if not already on one)
    if dt.second > 0 or dt.microsecond > 0:
        dt = dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    else:
        dt = dt.replace(second=0, microsecond=0)

    # Scan up to 366 days * 24 * 60 = 527040 minutes
    for _ in range(527040):
        if (
            dt.month in fields["month"]
            and dt.day in fields["dom"]
            and dt.hour in fields["hour"]
            and dt.minute in fields["minute"]
            and dt.weekday() in [w % 7 for w in fields["dow"]]
            # Python weekday: Mon=0..Sun=6 but cron dow: Sun=0..Sat=6
            # Remap: cron_dow 0=Sun → python 6, cron_dow 1=Mon → python 0, ...
        ):
            return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
        dt += datetime.timedelta(minutes=1)

    raise RuntimeError(f"No matching time found for cron expression {cron_expr!r} within 1 year")


def _python_weekday_to_cron_dow(python_wd: int) -> int:
    """Convert Python weekday (Mon=0..Sun=6) to cron dow (Sun=0..Sat=6)."""
    # python Mon=0 → cron Mon=1
    # python Sun=6 → cron Sun=0
    return (python_wd + 1) % 7


def next_run_after(cron_expr: str, after_ts: float) -> float:  # noqa: F811 — intentional re-def
    """Return the next unix timestamp >= after_ts that matches cron_expr.

    Uses UTC for all datetime arithmetic.
    Scans minute-by-minute; raises RuntimeError if no match in 1 year.
    """
    fields = _parse_cron(cron_expr)
    dt = datetime.datetime.fromtimestamp(after_ts, datetime.timezone.utc).replace(tzinfo=None)
    # Advance to next whole minute
    if dt.second > 0 or dt.microsecond > 0:
        dt = dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    else:
        dt = dt.replace(second=0, microsecond=0)

    for _ in range(527040):
        cron_dow = _python_weekday_to_cron_dow(dt.weekday())
        if (
            dt.month in fields["month"]
            and dt.day in fields["dom"]
            and dt.hour in fields["hour"]
            and dt.minute in fields["minute"]
            and cron_dow in fields["dow"]
        ):
            # Return UTC unix timestamp
            epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
            aware = dt.replace(tzinfo=datetime.timezone.utc)
            return (aware - epoch).total_seconds()
        dt += datetime.timedelta(minutes=1)

    raise RuntimeError(f"No matching time found for cron expression {cron_expr!r} within 1 year")


# ---------------------------------------------------------------------------
# SovereignScheduler
# ---------------------------------------------------------------------------


class SovereignScheduler:
    """Cron-style campaign scheduler for PRADY OS.

    Parameters
    ----------
    campaign_engine:
        The campaign engine (or any callable accepting a campaign_spec dict).
        Currently stored for future execution; tick() fires via the bus.
    bus:
        EventBus instance.  ``bus.publish(topic, payload)`` is called when a
        job fires.
    clock:
        Callable returning current unix timestamp. Defaults to ``time.time``.
        Inject a lambda in tests to control time deterministically.
    """

    def __init__(
        self,
        campaign_engine: Any,
        bus: Any,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._campaign_engine = campaign_engine
        self._bus = bus
        self._clock: Callable[[], float] = clock if clock is not None else time.time

        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(
        self,
        job_id: str,
        cron_expr: str,
        campaign_spec: dict,
        priority: int = 5,
        sla_seconds: float | None = None,
    ) -> dict:
        """Register (or overwrite) a scheduled job.

        Returns the job dict with keys:
            job_id, cron_expr, campaign_spec, priority, sla_seconds,
            next_run, enabled
        """
        now = self._clock()
        next_run = next_run_after(cron_expr, now)
        job: dict = {
            "job_id": job_id,
            "cron_expr": cron_expr,
            "campaign_spec": campaign_spec,
            "priority": priority,
            "sla_seconds": sla_seconds,
            "next_run": next_run,
            "enabled": True,
        }
        with self._lock:
            self._jobs[job_id] = job
        return copy.deepcopy(job)

    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID.  Returns False if not found."""
        with self._lock:
            if job_id not in self._jobs:
                return False
            del self._jobs[job_id]
            return True

    def get_jobs(self) -> list[dict]:
        """Return a deep copy of all registered jobs."""
        with self._lock:
            return [copy.deepcopy(j) for j in self._jobs.values()]

    def enable_job(self, job_id: str) -> bool:
        """Enable a job.  Returns False if not found."""
        with self._lock:
            if job_id not in self._jobs:
                return False
            self._jobs[job_id]["enabled"] = True
            return True

    def disable_job(self, job_id: str) -> bool:
        """Disable a job.  Returns False if not found."""
        with self._lock:
            if job_id not in self._jobs:
                return False
            self._jobs[job_id]["enabled"] = False
            return True

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self) -> list[str]:
        """Check all enabled jobs; fire those whose next_run <= now.

        For each fired job:
          1. Publishes "scheduler.job.fired" bus event with
             {job_id, campaign_spec, priority}.
          2. Advances next_run to the next scheduled timestamp.

        Returns the list of fired job_ids (may be empty).
        """
        now = self._clock()
        fired: list[str] = []

        with self._lock:
            job_ids = list(self._jobs.keys())

        for job_id in job_ids:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                if not job["enabled"]:
                    continue
                if job["next_run"] > now:
                    continue
                # Mark as fired
                fired.append(job_id)
                payload = {
                    "job_id": job["job_id"],
                    "campaign_spec": copy.deepcopy(job["campaign_spec"]),
                    "priority": job["priority"],
                }
                # Advance to next run
                job["next_run"] = next_run_after(job["cron_expr"], now)

            # Publish outside the lock to avoid deadlock if bus calls back
            try:
                self._bus.publish("scheduler.job.fired", payload)
            except Exception:  # noqa: BLE001
                pass

        return fired

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def start(self, interval_seconds: float = 1.0) -> None:
        """Launch a background daemon thread that calls tick() every interval.

        Idempotent — calling start() on an already-running scheduler is a
        no-op.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()

        def _run() -> None:
            while not self._stop_event.is_set():
                try:
                    self.tick()
                except Exception:  # noqa: BLE001
                    pass
                self._stop_event.wait(timeout=interval_seconds)

        thread = threading.Thread(target=_run, daemon=True, name="sovereign-scheduler")
        thread.start()
        with self._lock:
            self._thread = thread

    def stop(self) -> None:
        """Stop the background thread.  Idempotent."""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=5.0)
