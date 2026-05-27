from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.signal_aggregator import SignalAggregator, SignalPoint
    from pradyos.core.watchpoint import WatchpointSystem
    from pradyos.core.decision_journal import DecisionJournal
    from pradyos.core.bus_inspector import BusInspector
    from pradyos.core.capability_registry import CapabilityRegistry
    from pradyos.core.health_scorecard import HealthScorecard


class SovereignBus:
    def __init__(
        self,
        signal_aggregator: "SignalAggregator | None" = None,
        watchpoint_system: "WatchpointSystem | None" = None,
        decision_journal: "DecisionJournal | None" = None,
        bus_inspector: "BusInspector | None" = None,
        capability_registry: "CapabilityRegistry | None" = None,
        health_scorecard: "HealthScorecard | None" = None,
    ) -> None:
        self._signal_aggregator = signal_aggregator
        self._watchpoint_system = watchpoint_system
        self._decision_journal = decision_journal
        self._bus_inspector = bus_inspector
        self._capability_registry = capability_registry
        self._health_scorecard = health_scorecard

    # ── WIRE 1 ────────────────────────────────────────────────────────────────

    def record_signal(
        self,
        name: str,
        value: float,
        timestamp: "float | None" = None,
    ) -> "SignalPoint | None":
        pt = None
        if self._signal_aggregator is not None:
            pt = self._signal_aggregator.record(name, value, timestamp)

        if self._watchpoint_system is not None:
            fired = self._watchpoint_system.check(name, value)
            if self._decision_journal is not None:
                for alert in fired:
                    self._decision_journal.record(
                        agent_id="integration_bus",
                        decision_type="watchpoint_alert",
                        rationale=(
                            f"signal={name} value={value} "
                            f"watchpoint={alert.watchpoint_name} "
                            f"severity={alert.severity}"
                        ),
                        outcome=f"alert:{alert.watchpoint_name}",
                    )

        return pt

    # ── WIRE 2 ────────────────────────────────────────────────────────────────

    def record_bus_event(self, topic: str, payload: "dict | None" = None) -> None:
        if self._bus_inspector is not None:
            self._bus_inspector.record(topic, payload or {})
        if self._signal_aggregator is not None:
            self._signal_aggregator.record(f"bus.{topic}", 1.0)
        return None

    # ── WIRE 3 ────────────────────────────────────────────────────────────────

    def update_capability(self, name: str, status: str) -> None:
        if self._capability_registry is not None:
            self._capability_registry.update_status(name, status)
        if self._health_scorecard is not None and status == "degraded":
            self._health_scorecard.update(name, 0)
        return None

    # ── STATUS ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        wired = {
            "signal_aggregator": self._signal_aggregator is not None,
            "watchpoint_system": self._watchpoint_system is not None,
            "decision_journal": self._decision_journal is not None,
            "bus_inspector": self._bus_inspector is not None,
            "capability_registry": self._capability_registry is not None,
            "health_scorecard": self._health_scorecard is not None,
        }
        return {
            "wired": wired,
            "wire_count": sum(1 for v in wired.values() if v),
        }
