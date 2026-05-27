"""Phase 34C — 20 tests for pradyos.core.integration_bus.SovereignBus."""
from __future__ import annotations

import pytest

from pradyos.core.integration_bus import SovereignBus
from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.watchpoint import WatchpointSystem
from pradyos.core.decision_journal import DecisionJournal
from pradyos.core.bus_inspector import BusInspector
from pradyos.core.capability_registry import CapabilityRegistry, Capability
from pradyos.core.health_scorecard import HealthScorecard


# ── factories ─────────────────────────────────────────────────────────────────

def _empty_bus() -> SovereignBus:
    return SovereignBus()


def _full_bus() -> tuple[SovereignBus, dict]:
    sa = SignalAggregator()
    ws = WatchpointSystem()
    dj = DecisionJournal()
    bi = BusInspector()
    cr = CapabilityRegistry()
    hs = HealthScorecard()
    bus = SovereignBus(
        signal_aggregator=sa,
        watchpoint_system=ws,
        decision_journal=dj,
        bus_inspector=bi,
        capability_registry=cr,
        health_scorecard=hs,
    )
    return bus, {"sa": sa, "ws": ws, "dj": dj, "bi": bi, "cr": cr, "hs": hs}


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_all_none():
    bus = _empty_bus()
    assert bus._signal_aggregator is None
    assert bus._watchpoint_system is None
    assert bus._decision_journal is None
    assert bus._bus_inspector is None
    assert bus._capability_registry is None
    assert bus._health_scorecard is None


def test_status_structure_when_empty():
    bus = _empty_bus()
    s = bus.status()
    assert "wired" in s
    assert "wire_count" in s


def test_wire_count_zero_when_empty():
    bus = _empty_bus()
    assert bus.status()["wire_count"] == 0


def test_wire_count_six_when_all_wired():
    bus, _ = _full_bus()
    assert bus.status()["wire_count"] == 6


# ── record_signal ─────────────────────────────────────────────────────────────

def test_record_signal_returns_none_when_no_aggregator():
    bus = _empty_bus()
    result = bus.record_signal("cpu", 50.0)
    assert result is None


def test_record_signal_calls_aggregator_record():
    sa = SignalAggregator()
    bus = SovereignBus(signal_aggregator=sa)
    bus.record_signal("cpu", 42.0)
    pts = sa.get("cpu", limit=10)
    assert len(pts) == 1
    assert pts[0].value == 42.0


def test_record_signal_calls_watchpoint_check():
    sa = SignalAggregator()
    ws = WatchpointSystem()
    ws.register("cpu_high", metric="cpu", operator="gt", threshold=80.0, severity="warn")
    bus = SovereignBus(signal_aggregator=sa, watchpoint_system=ws)
    bus.record_signal("cpu", 99.0)
    alerts = ws.get_alerts()
    assert len(alerts) == 1
    assert alerts[0].watchpoint_name == "cpu_high"


def test_record_signal_no_watchpoint_when_no_aggregator():
    # watchpoint.check is only reached after signal is recorded
    ws = WatchpointSystem()
    ws.register("cpu_high", metric="cpu", operator="gt", threshold=80.0)
    bus = SovereignBus(watchpoint_system=ws)
    # No aggregator → check still called (wiring is independent)
    # But with aggregator=None, record_signal returns None
    result = bus.record_signal("cpu", 99.0)
    assert result is None
    # check() is still called if watchpoint_system is set
    alerts = ws.get_alerts()
    assert len(alerts) == 1


def test_watchpoint_fires_decision_journal_record():
    sa = SignalAggregator()
    ws = WatchpointSystem()
    ws.register("cpu_high", metric="cpu", operator="gt", threshold=80.0, severity="critical")
    dj = DecisionJournal()
    bus = SovereignBus(signal_aggregator=sa, watchpoint_system=ws, decision_journal=dj)
    bus.record_signal("cpu", 95.0)
    entries = dj.get_entries()
    assert len(entries) == 1
    assert entries[0].decision_type == "watchpoint_alert"


def test_watchpoint_fires_no_journal_no_error():
    sa = SignalAggregator()
    ws = WatchpointSystem()
    ws.register("cpu_high", metric="cpu", operator="gt", threshold=80.0)
    bus = SovereignBus(signal_aggregator=sa, watchpoint_system=ws)
    # Should not raise even without decision_journal
    bus.record_signal("cpu", 99.0)


# ── record_bus_event ──────────────────────────────────────────────────────────

def test_record_bus_event_returns_none_when_no_inspector():
    bus = _empty_bus()
    result = bus.record_bus_event("heartbeat")
    assert result is None


def test_record_bus_event_calls_bus_inspector_record():
    bi = BusInspector()
    bus = SovereignBus(bus_inspector=bi)
    bus.record_bus_event("heartbeat", {"tick": 1})
    events = bi.get_events()
    assert len(events) == 1
    assert events[0].topic == "heartbeat"


def test_record_bus_event_records_signal_in_aggregator():
    sa = SignalAggregator()
    bus = SovereignBus(signal_aggregator=sa)
    bus.record_bus_event("heartbeat")
    pts = sa.get("bus.heartbeat", limit=10)
    assert len(pts) == 1
    assert pts[0].value == 1.0


def test_record_bus_event_no_crash_when_aggregator_none():
    bi = BusInspector()
    bus = SovereignBus(bus_inspector=bi)
    bus.record_bus_event("tick")  # no aggregator → should not raise


# ── update_capability ─────────────────────────────────────────────────────────

def test_update_capability_calls_update_status():
    cr = CapabilityRegistry()
    cr.register("svc", version="1.0")
    bus = SovereignBus(capability_registry=cr)
    bus.update_capability("svc", "active")
    cap = cr.get("svc")
    assert cap is not None
    assert cap.status == "active"


def test_update_capability_degraded_calls_health_scorecard():
    cr = CapabilityRegistry()
    cr.register("svc", version="1.0")
    hs = HealthScorecard()
    bus = SovereignBus(capability_registry=cr, health_scorecard=hs)
    bus.update_capability("svc", "degraded")
    report = hs.get_report()
    # "svc" should now have score=0
    names = [c.name for c in report.components]
    assert "svc" in names


def test_update_capability_active_does_not_call_health_scorecard():
    cr = CapabilityRegistry()
    cr.register("svc", version="1.0")
    hs = HealthScorecard()
    bus = SovereignBus(capability_registry=cr, health_scorecard=hs)
    bus.update_capability("svc", "active")
    report = hs.get_report()
    # health_scorecard.update() should NOT have been called
    names = [c.name for c in report.components]
    assert "svc" not in names


def test_update_capability_no_crash_when_health_scorecard_none():
    cr = CapabilityRegistry()
    cr.register("svc", version="1.0")
    bus = SovereignBus(capability_registry=cr)
    bus.update_capability("svc", "degraded")  # no health_scorecard → no crash


# ── status wired dict ─────────────────────────────────────────────────────────

def test_status_wired_dict_reflects_modules():
    sa = SignalAggregator()
    bus = SovereignBus(signal_aggregator=sa)
    s = bus.status()
    assert s["wired"]["signal_aggregator"] is True
    assert s["wired"]["watchpoint_system"] is False
    assert s["wire_count"] == 1


# ── end-to-end ────────────────────────────────────────────────────────────────

def test_end_to_end_all_6_wired_watchpoint_fires_journal():
    bus, m = _full_bus()
    # Register a watchpoint
    m["ws"].register("mem_high", metric="mem", operator="gt",
                     threshold=90.0, severity="critical")
    # Fire the signal
    bus.record_signal("mem", 95.0)
    # Decision journal should have one entry
    entries = m["dj"].get_entries()
    assert len(entries) == 1
    assert entries[0].decision_type == "watchpoint_alert"
    assert "mem_high" in entries[0].outcome
