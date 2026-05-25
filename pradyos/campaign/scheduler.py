"""CampaignScheduler -- cron-driven campaign execution daemon.

Schedule storage: var/state/schedules.jsonl (append-only; latest record
per schedule_id wins).

Daemon: threading.Thread, polls every POLL_INTERVAL seconds (default 60),
fires campaigns whose next_run timestamp has elapsed.

Windows-safe:
  - No fork(), os.killpg(), or start_new_session
  - All paths via pathlib
  - TCP sockets only (no AF_UNIX)
  - sys.platform guards where required
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from pradyos.core.ids import new_id

log = logging.getLogger("pradyos.campaign.scheduler")

_ROOT      = Path(__file__).resolve().parents[2]
_STATE_DIR = Path(os.environ.get("PRADYOS_STATE_PATH",
                                  str(_ROOT / "var" / "state")))

POLL_INTERVAL = int(os.environ.get("PRADYOS_SCHEDULER_POLL", "60"))

# ---------------------------------------------------------------------------
# Cron parser
# ---------------------------------------------------------------------------

def _matches_field(field: str, value: int) -> bool:
    """Return True if cron *field* matches integer *value*.

    Supports: '*' (wildcard), exact integers, and '/N' step syntax.
    No ranges (a-b) or lists (a,b) -- intentionally minimal.
    """
    if field == "*":
        return True
    if field.startswith("*/"):
        try:
            step = int(field[2:])
            return value % step == 0
        except ValueError:
            return False
    try:
        return int(field) == value
    except ValueError:
        return False


def _next_run_after(cron: str, after: float | None = None) -> float:
    """Return the next Unix timestamp when *cron* fires after *after*.

    Accepts standard 5-field cron:
        minute  hour  day_of_month  month  day_of_week
    day_of_week: 0=Monday (Python localtime.tm_wday convention).

    Raises ValueError for malformed expressions or if no match within 366 days.
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"Cron expression must have exactly 5 fields, got {len(fields)}: {cron!r}"
        )
    f_min, f_hour, f_dom, f_month, f_dow = fields

    if after is None:
        after = time.time()

    # Start at the next whole minute after 'after'
    candidate = after - (after % 60) + 60  # floor to minute, then +1 minute

    max_minutes = 366 * 24 * 60
    for _ in range(max_minutes):
        t = time.localtime(candidate)
        if (
            _matches_field(f_min,   t.tm_min)
            and _matches_field(f_hour,  t.tm_hour)
            and _matches_field(f_dom,   t.tm_mday)
            and _matches_field(f_month, t.tm_mon)
            and _matches_field(f_dow,   t.tm_wday)
        ):
            return candidate
        candidate += 60

    raise ValueError(
        f"Cannot compute next run for cron {cron!r} within 366 days"
    )


def _should_fire(schedule: dict[str, Any], now: float) -> bool:
    """Return True if *schedule* is enabled and its next_run <= now."""
    if not schedule.get("enabled", True):
        return False
    next_run = schedule.get("next_run")
    if next_run is None:
        return False
    return float(next_run) <= now


# ---------------------------------------------------------------------------
# CampaignScheduler
# ---------------------------------------------------------------------------


class CampaignScheduler:
    """CRUD + daemon for cron-scheduled campaigns.

    Thread-safe. All state persisted to schedules.jsonl (JSONL, latest
    record per schedule_id wins on read).
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir   = state_dir or _STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._file        = self._state_dir / "schedules.jsonl"
        self._file_lock   = threading.Lock()
        self._stop_event  = threading.Event()
        self._tick_count  = 0
        self._archiver: "Any | None" = None

    def set_archiver(self, archiver: "Any") -> None:
        """Attach a CampaignArchiver (optional — called by integration code)."""
        self._archiver = archiver

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_schedule(
        self,
        name: str,
        cron: str,
        intent: str,
        tasks_payload: list[dict[str, Any]] | None = None,
        enabled: bool = True,
    ) -> str:
        """Add a new schedule. Returns schedule_id.

        Raises ValueError if *cron* is invalid.
        """
        next_run = _next_run_after(cron)   # validates cron; raises ValueError if bad

        sid = new_id("sc")
        record: dict[str, Any] = {
            "schedule_id":   sid,
            "name":          name,
            "cron":          cron,
            "intent":        intent,
            "tasks_payload": tasks_payload or [],
            "enabled":       enabled,
            "next_run":      next_run,
            "last_run":      None,
            "created_at":    time.time(),
            "_deleted":      False,
        }
        self._write(record)
        log.info("Schedule added [%s] %s (%s) next=%s",
                 sid[:8], name, cron,
                 time.strftime("%Y-%m-%d %H:%M", time.localtime(next_run)))
        return sid

    def remove_schedule(self, schedule_id: str) -> bool:
        """Soft-delete a schedule. Returns True if found."""
        schedules = self._load()
        # Support full ID or unique prefix
        targets = [
            s for s in schedules.values()
            if s["schedule_id"].startswith(schedule_id)
        ]
        if not targets:
            return False
        for s in targets:
            s["_deleted"] = True
            s["enabled"]  = False
            self._write(s)
        return True

    def list_schedules(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        """Return active (non-deleted) schedules."""
        all_s = list(self._load().values())
        if not include_deleted:
            all_s = [s for s in all_s if not s.get("_deleted", False)]
        return all_s

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        for s in self._load().values():
            if s["schedule_id"].startswith(schedule_id):
                return s
        return None

    def update_schedule(self, record: dict[str, Any]) -> None:
        """Persist an updated schedule record."""
        self._write(record)

    # ------------------------------------------------------------------
    # Daemon
    # ------------------------------------------------------------------

    def start_daemon(
        self,
        engine: Any | None = None,
        poll_interval: int = POLL_INTERVAL,
        stop_event: threading.Event | None = None,
    ) -> threading.Thread:
        """Start the scheduler daemon. Returns the daemon thread."""
        if stop_event is not None:
            self._stop_event = stop_event

        t = threading.Thread(
            target=self._daemon_loop,
            args=(engine, poll_interval),
            name="pradyos-campaign-scheduler",
            daemon=True,
        )
        t.start()
        log.info("CampaignScheduler daemon started (poll=%ds)", poll_interval)
        return t

    def stop(self) -> None:
        self._stop_event.set()

    def _daemon_loop(self, engine: Any | None, poll_interval: int) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick(engine)
            except Exception as e:
                log.error("Scheduler tick error: %s", e)
            self._stop_event.wait(timeout=poll_interval)

    def _tick(self, engine: Any | None, registry: Any | None = None) -> None:
        """Check for due schedules and fire them."""
        now = time.time()
        for s in self.list_schedules():
            if _should_fire(s, now):
                log.info("Firing scheduled campaign [%s] %s",
                         s["schedule_id"][:8], s["name"])
                self._fire(s, engine)
        # Run archiver pass every 10 scheduler ticks (Phase 6)
        self._tick_count += 1
        if self._tick_count % 10 == 0 and self._archiver is not None and registry is not None:
            try:
                archived = self._archiver.archive_old(registry)
                if archived:
                    log.info("CampaignArchiver: archived %d campaign(s)", archived)
            except Exception as exc:
                log.error("CampaignArchiver error: %s", exc)

    def _fire(self, schedule: dict[str, Any], engine: Any | None) -> None:
        """Fire a scheduled campaign in a background thread."""
        import asyncio

        sid = schedule["schedule_id"]

        try:
            from pradyos.campaign.engine import CampaignEngine
            from pradyos.imperium.task import ImperiumTask

            _engine = engine if engine is not None else CampaignEngine()

            tasks: list[Any] = []
            for tp in schedule.get("tasks_payload", []):
                tasks.append(ImperiumTask(
                    kind=tp.get("kind", "research"),
                    intent=tp.get("intent", schedule["intent"]),
                    payload=tp,
                    submitted_by="scheduler",
                ))

            if not tasks:
                tasks = [ImperiumTask(
                    kind="research",
                    intent=schedule["intent"],
                    payload={"intent": schedule["intent"]},
                    submitted_by="scheduler",
                )]

            campaign = _engine.create_campaign(
                name=schedule["name"],
                intent=schedule["intent"],
                tasks=tasks,
                submitted_by="scheduler",
                metadata={"schedule_id": sid, "cron": schedule["cron"]},
            )

            def _run_campaign() -> None:
                try:
                    asyncio.run(_engine.run_campaign(campaign))
                    log.info("Scheduled campaign [%s] complete",
                             campaign.campaign_id[:8])
                except Exception as exc:
                    log.error("Scheduled campaign [%s] failed: %s",
                              campaign.campaign_id[:8], exc)

            t = threading.Thread(
                target=_run_campaign,
                name=f"sched-{sid[:8]}",
                daemon=True,
            )
            t.start()

        except Exception as e:
            log.error("Failed to fire schedule [%s]: %s", sid[:8], e)

        finally:
            # Update last_run and compute next_run
            schedule["last_run"] = time.time()
            try:
                schedule["next_run"] = _next_run_after(schedule["cron"])
            except ValueError:
                schedule["next_run"] = None
            self._write(schedule)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        """Return latest record per schedule_id."""
        latest: dict[str, dict[str, Any]] = {}
        if not self._file.exists():
            return latest
        with self._file_lock:
            try:
                with self._file.open(encoding="utf-8") as fh:
                    for raw in fh:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            s = json.loads(raw)
                            latest[s["schedule_id"]] = s
                        except (json.JSONDecodeError, KeyError):
                            continue
            except OSError:
                pass
        return latest

    def _write(self, record: dict[str, Any]) -> None:
        with self._file_lock:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Entrypoint (daemon mode)
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
    sched = CampaignScheduler()
    poll  = int(os.environ.get("PRADYOS_SCHEDULER_POLL", str(POLL_INTERVAL)))
    t = sched.start_daemon(poll_interval=poll)
    log.info("CampaignScheduler daemon running (poll=%ds). Ctrl+C to stop.", poll)
    try:
        t.join()
    except KeyboardInterrupt:
        sched.stop()
        log.info("CampaignScheduler stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
