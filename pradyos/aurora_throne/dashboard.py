"""AURORA THRONE — ObservabilityDashboard (Phase 12).

Provides a live window into the PRADY OS runtime:

  - ``bus_events``    — last 50 events from the EventBus (ring buffer)
  - ``quarantine``    — tasks currently quarantined by SelfHealEngine
  - ``system_health`` — coarse health signal derived from kernel metrics

Usage
-----
    from pradyos.aurora_throne.dashboard import ObservabilityDashboard

    dash = ObservabilityDashboard(bus=bus, kernel=kernel, audit=audit)
    dash.start()                        # subscribe to bus
    snap = dash.get_live_snapshot()     # DashboardSnapshot
    dash.stop()                         # unsubscribe

Health thresholds
-----------------
  ok       — dead_letter_count == 0  AND active_tasks < 5
  degraded  — dead_letter_count >= 1  OR  active_tasks >= 5  (and not critical)
  critical  — dead_letter_count >= 5  OR  active_tasks >= 20
"""

from __future__ import annotations

import dataclasses
import time
from collections import deque
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus

# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

_CRITICAL_DLQ = 5
_CRITICAL_ACTIVE = 20
_DEGRADED_DLQ = 1
_DEGRADED_ACTIVE = 5


# ---------------------------------------------------------------------------
# DashboardSnapshot
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class DashboardSnapshot:
    """Immutable snapshot of the observability state at a point in time.

    Attributes
    ----------
    bus_events:
        Up to the last 50 events received on the EventBus, each stored as a
        dict with at least ``"topic"`` and ``"payload"`` keys.
    quarantine:
        List of task IDs currently held in the SelfHealEngine quarantine.
    system_health:
        Coarse health signal with the following keys:

        * ``"status"``           -- ``"ok"`` | ``"degraded"`` | ``"critical"``
        * ``"active_tasks"``     -- number of currently active tasks
        * ``"dead_letter_count"``-- number of tasks in the dead-letter queue
        * ``"last_event_ts"``    -- float timestamp of the most recent bus event,
                                   or ``None`` if no events have been seen yet
    """

    bus_events: list[dict]
    quarantine: list[str]
    system_health: dict

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary representation."""
        return {
            "bus_events": self.bus_events,
            "quarantine": self.quarantine,
            "system_health": self.system_health,
        }


# ---------------------------------------------------------------------------
# ObservabilityDashboard
# ---------------------------------------------------------------------------

class ObservabilityDashboard:
    """Live observability dashboard -- injected dependencies, no singletons.

    Parameters
    ----------
    bus:
        :class:`~pradyos.core.bus.EventBus` (or compatible).
        Falls back to the process-global singleton.
    kernel:
        The IMPERIUM kernel.  Must expose:

        * ``stats() -> dict``              -- kernel statistics
        * ``dead_letter_queue() -> list``  -- tasks in the dead-letter queue
        * ``_self_heal_engine``            -- attribute that exposes
          ``quarantine_list() -> list[str]``, or ``None`` if not wired.
    audit:
        :class:`~pradyos.core.audit.AuditLog` -- available for future
        diagnostic writes.
    """

    AGENT_ID = "aurora_throne.dashboard"
    _BUS_TOPIC = "*"          # capture every event published on the bus
    _RING_SIZE = 50

    def __init__(
        self,
        bus: EventBus | None = None,
        kernel: Any | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._bus: EventBus = bus or get_bus()
        self._kernel: Any = kernel
        self._audit: AuditLog = audit or get_audit_log()

        # Ring buffer -- deque enforces the 50-event cap automatically.
        self._ring: deque = deque(maxlen=self._RING_SIZE)
        self._last_event_ts: float | None = None
        self._subscribed: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Subscribe to all bus events and begin filling the ring buffer."""
        if not self._subscribed:
            self._bus.subscribe(self._BUS_TOPIC, self._on_bus_event)
            self._subscribed = True

    def stop(self) -> None:
        """Unsubscribe from the bus (idempotent)."""
        if self._subscribed:
            self._bus.unsubscribe(self._BUS_TOPIC, self._on_bus_event)
            self._subscribed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_live_snapshot(self) -> DashboardSnapshot:
        """Return an immutable snapshot of the current observability state."""
        bus_events = list(self._ring)
        quarantine = self._get_quarantine()
        system_health = self._build_system_health()
        return DashboardSnapshot(
            bus_events=bus_events,
            quarantine=quarantine,
            system_health=system_health,
        )

    # ------------------------------------------------------------------
    # Bus subscriber
    # ------------------------------------------------------------------

    def _on_bus_event(self, topic: str, payload: dict) -> None:
        """EventBus subscriber -- appends every event to the ring buffer."""
        ts = time.time()
        self._ring.append({"topic": topic, "payload": payload, "ts": ts})
        self._last_event_ts = ts

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_quarantine(self) -> list:
        """Return the quarantine list from the kernel's SelfHealEngine."""
        if self._kernel is None:
            return []
        she = (
            getattr(self._kernel, "_self_heal_engine", None)
            or getattr(self._kernel, "self_heal_engine", None)
        )
        if she is None:
            return []
        try:
            return she.quarantine_list()
        except Exception:  # noqa: BLE001
            return []

    def _get_active_tasks(self) -> int:
        """Return the number of active tasks from kernel.stats()."""
        if self._kernel is None:
            return 0
        try:
            s = self._kernel.stats()
            # Try specific keys first, then common fallbacks.
            for key in ("active_tasks", "active", "running"):
                val = s.get(key)
                if isinstance(val, int):
                    return val
            # Derive from total minus terminal states.
            total = s.get("total", 0)
            done = (
                s.get("succeeded", 0)
                + s.get("failed", 0)
                + s.get("cancelled", 0)
                + s.get("rejected", 0)
            )
            return max(0, int(total) - int(done))
        except Exception:  # noqa: BLE001
            return 0

    def _get_dead_letter_count(self) -> int:
        """Return the number of dead-lettered tasks."""
        if self._kernel is None:
            return 0
        try:
            return len(self._kernel.dead_letter_queue())
        except Exception:  # noqa: BLE001
            return 0

    def _build_system_health(self) -> dict:
        """Compute the coarse health signal.

        Thresholds
        ----------
        critical  : dead_letter_count >= 5  OR active_tasks >= 20
        degraded  : dead_letter_count >= 1  OR active_tasks >= 5
        ok        : everything else
        """
        active_tasks = self._get_active_tasks()
        dead_letter_count = self._get_dead_letter_count()

        if dead_letter_count >= _CRITICAL_DLQ or active_tasks >= _CRITICAL_ACTIVE:
            status = "critical"
        elif dead_letter_count >= _DEGRADED_DLQ or active_tasks >= _DEGRADED_ACTIVE:
            status = "degraded"
        else:
            status = "ok"

        return {
            "status": status,
            "active_tasks": active_tasks,
            "dead_letter_count": dead_letter_count,
            "last_event_ts": self._last_event_ts,
        }
