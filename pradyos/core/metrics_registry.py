"""Sovereign Metrics Registry — Phase 22.

A Prometheus-compatible plain-text metrics collector.
Thread-safe via threading.Lock.  Zero external dependencies (stdlib only).
"""
from __future__ import annotations

import threading
from typing import Dict


class MetricsRegistry:
    """Lightweight counter registry with Prometheus text-format export."""

    _PRE_REGISTERED = (
        "pradyos_campaigns_run_total",
        "pradyos_tasks_dispatched_total",
        "pradyos_errors_total",
        "pradyos_ledger_entries_total",
        "pradyos_intent_suggestions_total",
        "pradyos_policy_violations_total",
        "pradyos_scheduler_jobs_fired_total",
        "pradyos_config_reloads_total",
    )

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._counters: Dict[str, float] = {name: 0.0 for name in self._PRE_REGISTERED}

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def increment(self, name: str, value: float = 1.0) -> None:
        """Add *value* to counter *name* (creates counter if absent)."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + value

    def set(self, name: str, value: float) -> None:
        """Set counter *name* to *value* (creates counter if absent)."""
        with self._lock:
            self._counters[name] = value

    def reset(self, name: str) -> None:
        """Set counter *name* to 0.0."""
        with self._lock:
            self._counters[name] = 0.0

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get(self, name: str) -> float:
        """Return current value of *name*, or 0.0 if absent."""
        with self._lock:
            return self._counters.get(name, 0.0)

    def get_all(self) -> Dict[str, float]:
        """Return a shallow copy of all counters."""
        with self._lock:
            return dict(self._counters)

    # ------------------------------------------------------------------
    # Prometheus export
    # ------------------------------------------------------------------

    def render_prometheus(self) -> str:
        """Return a Prometheus plain-text exposition string.

        Format (sorted by metric name):
            # HELP {name} PradyOS metric
            # TYPE {name} counter
            {name} {value}

        Integer values are rendered without a decimal point (e.g. ``5``);
        non-integer floats are rendered with a decimal point (e.g. ``1.5``).
        The output ends with a trailing newline.
        """
        with self._lock:
            snapshot = sorted(self._counters.items())

        lines: list[str] = []
        for name, value in snapshot:
            # Render as integer when whole, float otherwise
            if value == int(value):
                rendered = str(int(value))
            else:
                rendered = str(value)
            lines.append(f"# HELP {name} PradyOS metric")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {rendered}")

        return "\n".join(lines) + "\n"
