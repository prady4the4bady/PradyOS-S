"""Phase 12 — ObservabilityDashboard tests.

20 tests covering:
    1.  get_live_snapshot() returns a DashboardSnapshot
    2.  DashboardSnapshot has bus_events, quarantine, system_health fields
    3.  bus ring buffer is capped at 50 events
    4.  oldest event is dropped when the ring is full
    5.  quarantine list reflects kernel's SelfHealEngine state
    6.  system_health status is "ok" when no issues
    7.  system_health status is "degraded" when dead_letter_count >= 1
    8.  system_health status is "degraded" when active_tasks >= 5
    9.  system_health status is "critical" when dead_letter_count >= 5
    10. system_health status is "critical" when active_tasks >= 20
    11. start() subscribes to the bus
    12. stop() unsubscribes from the bus
    13. _on_bus_event appends to the ring buffer
    14. last_event_ts updates on new event
    15. last_event_ts is None before any event
    16. active_tasks count comes from kernel.stats()
    17. dead_letter_count comes from kernel.dead_letter_queue()
    18. DashboardSnapshot is JSON-serialisable
    19. bus_events dict contains "topic" and "payload" keys
    20. stop() called twice does not raise
"""

from __future__ import annotations

import json
import time
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from pradyos.aurora_throne.dashboard import (
    DashboardSnapshot,
    ObservabilityDashboard,
    _CRITICAL_ACTIVE,
    _CRITICAL_DLQ,
    _DEGRADED_ACTIVE,
    _DEGRADED_DLQ,
)
from pradyos.core.bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kernel(active_tasks: int = 0, dlq_count: int = 0, quarantine: list | None = None) -> MagicMock:
    """Return a mock Imperium kernel with configurable metrics."""
    kernel = MagicMock()
    kernel.stats.return_value = {"active_tasks": active_tasks}
    kernel.dead_letter_queue.return_value = [object()] * dlq_count

    she = MagicMock()
    she.quarantine_list.return_value = list(quarantine or [])
    kernel._self_heal_engine = she

    return kernel


def _make_dashboard(
    bus: EventBus | None = None,
    kernel: MagicMock | None = None,
) -> ObservabilityDashboard:
    if bus is None:
        bus = EventBus()
    if kernel is None:
        kernel = _make_kernel()
    return ObservabilityDashboard(bus=bus, kernel=kernel)


# ---------------------------------------------------------------------------
# Test 1: get_live_snapshot() returns DashboardSnapshot
# ---------------------------------------------------------------------------

def test_snapshot_returns_dashboard_snapshot():
    dash = _make_dashboard()
    snap = dash.get_live_snapshot()
    assert isinstance(snap, DashboardSnapshot)


# ---------------------------------------------------------------------------
# Test 2: DashboardSnapshot has the three required fields
# ---------------------------------------------------------------------------

def test_snapshot_has_required_fields():
    dash = _make_dashboard()
    snap = dash.get_live_snapshot()
    assert hasattr(snap, "bus_events")
    assert hasattr(snap, "quarantine")
    assert hasattr(snap, "system_health")


# ---------------------------------------------------------------------------
# Test 3: bus ring buffer is capped at 50 events
# ---------------------------------------------------------------------------

def test_ring_buffer_capped_at_50():
    bus = EventBus()
    dash = _make_dashboard(bus=bus)
    dash.start()

    for i in range(75):
        bus.publish("test.event", {"i": i})

    snap = dash.get_live_snapshot()
    assert len(snap.bus_events) == 50
    dash.stop()


# ---------------------------------------------------------------------------
# Test 4: oldest event is dropped when the ring overflows
# ---------------------------------------------------------------------------

def test_ring_buffer_oldest_dropped():
    bus = EventBus()
    dash = _make_dashboard(bus=bus)
    dash.start()

    # Publish 51 events with distinct payloads
    for i in range(51):
        bus.publish("test.event", {"seq": i})

    snap = dash.get_live_snapshot()
    assert len(snap.bus_events) == 50
    # The first event (seq=0) should have been evicted
    seqs = [ev["payload"]["seq"] for ev in snap.bus_events]
    assert 0 not in seqs
    assert 50 in seqs
    dash.stop()


# ---------------------------------------------------------------------------
# Test 5: quarantine list reflects kernel SelfHealEngine state
# ---------------------------------------------------------------------------

def test_quarantine_reflects_kernel_state():
    kernel = _make_kernel(quarantine=["task-aaa", "task-bbb"])
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert set(snap.quarantine) == {"task-aaa", "task-bbb"}


# ---------------------------------------------------------------------------
# Test 6: system_health status is "ok" when no issues
# ---------------------------------------------------------------------------

def test_system_health_ok_when_no_issues():
    kernel = _make_kernel(active_tasks=0, dlq_count=0)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 7: system_health status is "degraded" when dead_letter_count >= 1
# ---------------------------------------------------------------------------

def test_system_health_degraded_on_dead_letter():
    kernel = _make_kernel(active_tasks=0, dlq_count=_DEGRADED_DLQ)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["status"] == "degraded"


# ---------------------------------------------------------------------------
# Test 8: system_health status is "degraded" when active_tasks >= threshold
# ---------------------------------------------------------------------------

def test_system_health_degraded_on_active_tasks():
    kernel = _make_kernel(active_tasks=_DEGRADED_ACTIVE, dlq_count=0)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["status"] == "degraded"


# ---------------------------------------------------------------------------
# Test 9: system_health status is "critical" when dead_letter_count >= 5
# ---------------------------------------------------------------------------

def test_system_health_critical_on_dead_letter():
    kernel = _make_kernel(active_tasks=0, dlq_count=_CRITICAL_DLQ)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["status"] == "critical"


# ---------------------------------------------------------------------------
# Test 10: system_health status is "critical" when active_tasks >= 20
# ---------------------------------------------------------------------------

def test_system_health_critical_on_active_tasks():
    kernel = _make_kernel(active_tasks=_CRITICAL_ACTIVE, dlq_count=0)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["status"] == "critical"


# ---------------------------------------------------------------------------
# Test 11: start() subscribes to the bus
# ---------------------------------------------------------------------------

def test_start_subscribes_to_bus(isolated_bus):
    dash = _make_dashboard(bus=isolated_bus)
    dash.start()

    received: list = []
    # The dashboard's _on_bus_event should now be subscribed to "*"
    isolated_bus.publish("system.test", {"x": 1})

    snap = dash.get_live_snapshot()
    assert len(snap.bus_events) == 1
    dash.stop()


# ---------------------------------------------------------------------------
# Test 12: stop() unsubscribes from the bus
# ---------------------------------------------------------------------------

def test_stop_unsubscribes_from_bus(isolated_bus):
    dash = _make_dashboard(bus=isolated_bus)
    dash.start()
    isolated_bus.publish("test.before_stop", {"a": 1})

    dash.stop()

    # Events published after stop should NOT appear
    isolated_bus.publish("test.after_stop", {"b": 2})

    snap = dash.get_live_snapshot()
    topics = [ev["topic"] for ev in snap.bus_events]
    assert "test.after_stop" not in topics
    assert "test.before_stop" in topics


# ---------------------------------------------------------------------------
# Test 13: _on_bus_event appends to the ring buffer
# ---------------------------------------------------------------------------

def test_on_bus_event_appends_to_ring():
    dash = _make_dashboard()
    dash._on_bus_event("imperium.task_queued", {"task_id": "t-1"})
    dash._on_bus_event("system.self_heal", {"task_id": "t-2"})

    snap = dash.get_live_snapshot()
    assert len(snap.bus_events) == 2
    assert snap.bus_events[0]["topic"] == "imperium.task_queued"
    assert snap.bus_events[1]["topic"] == "system.self_heal"


# ---------------------------------------------------------------------------
# Test 14: last_event_ts updates on new event
# ---------------------------------------------------------------------------

def test_last_event_ts_updates_on_new_event():
    dash = _make_dashboard()
    before = time.time()
    dash._on_bus_event("test.topic", {"val": 99})
    after = time.time()

    snap = dash.get_live_snapshot()
    ts = snap.system_health["last_event_ts"]
    assert ts is not None
    assert before <= ts <= after


# ---------------------------------------------------------------------------
# Test 15: last_event_ts is None before any event
# ---------------------------------------------------------------------------

def test_last_event_ts_none_initially():
    dash = _make_dashboard()
    snap = dash.get_live_snapshot()
    assert snap.system_health["last_event_ts"] is None


# ---------------------------------------------------------------------------
# Test 16: active_tasks count comes from kernel.stats()
# ---------------------------------------------------------------------------

def test_active_tasks_from_kernel_stats():
    kernel = _make_kernel(active_tasks=7)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["active_tasks"] == 7


# ---------------------------------------------------------------------------
# Test 17: dead_letter_count comes from kernel.dead_letter_queue()
# ---------------------------------------------------------------------------

def test_dead_letter_count_from_kernel():
    kernel = _make_kernel(dlq_count=3)
    dash = _make_dashboard(kernel=kernel)
    snap = dash.get_live_snapshot()
    assert snap.system_health["dead_letter_count"] == 3


# ---------------------------------------------------------------------------
# Test 18: DashboardSnapshot is JSON-serialisable
# ---------------------------------------------------------------------------

def test_snapshot_is_json_serialisable():
    dash = _make_dashboard()
    dash._on_bus_event("test.event", {"msg": "hello"})
    snap = dash.get_live_snapshot()
    # Must not raise
    serialised = json.dumps(snap.to_dict())
    reloaded = json.loads(serialised)
    assert "bus_events" in reloaded
    assert "quarantine" in reloaded
    assert "system_health" in reloaded


# ---------------------------------------------------------------------------
# Test 19: bus_events dict contains "topic" and "payload" keys
# ---------------------------------------------------------------------------

def test_bus_events_contain_topic_and_payload():
    dash = _make_dashboard()
    dash._on_bus_event("oracle.plan_stored", {"step_count": 3})
    snap = dash.get_live_snapshot()
    ev = snap.bus_events[0]
    assert "topic" in ev
    assert "payload" in ev
    assert ev["topic"] == "oracle.plan_stored"
    assert ev["payload"]["step_count"] == 3


# ---------------------------------------------------------------------------
# Test 20: stop() called twice does not raise
# ---------------------------------------------------------------------------

def test_stop_twice_no_error(isolated_bus):
    dash = _make_dashboard(bus=isolated_bus)
    dash.start()
    dash.stop()
    dash.stop()  # second call must be silent
