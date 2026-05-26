"""Phase 13 — CampaignMonitor unit tests (20 tests).

Covers:
    1.  get_snapshot() returns CampaignMonitorSnapshot
    2.  step_timeline ring buffer capped at 100
    3.  titan_ops_feed ring buffer capped at 50
    4.  active_campaigns reflects registry state
    5.  _on_campaign_event appends to step_timeline with ts
    6.  _on_titan_event appends to titan_ops_feed with ts
    7.  start() subscribes to campaign.* and titan.*
    8.  stop() unsubscribes both topics
    9.  snapshot is JSON-serialisable
    10. all required keys present in snapshot dict
    11. step_timeline evicts oldest on overflow
    12. titan_ops_feed evicts oldest on overflow
    13. double-stop is idempotent (no error)
    14. empty registry returns empty active_campaigns
    15. ts is a float in each event
    16. campaign_id present in step_timeline entries
    17. topic present in titan_ops_feed entries
    18. get_snapshot() before start() returns empty lists (safe default)
    19. ring buffers are independent (campaign events don't go to titan feed)
    20. snapshot dict has exactly the 3 top-level keys
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from pradyos.aurora_throne.campaign_monitor import (
    CampaignMonitor,
    CampaignMonitorSnapshot,
)
from pradyos.core.bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(active: list | None = None) -> MagicMock:
    """Return a mock CampaignRegistry with a configurable active() list."""
    reg = MagicMock()
    reg.active.return_value = list(active or [])
    return reg


def _make_monitor(
    bus: EventBus | None = None,
    registry: MagicMock | None = None,
) -> CampaignMonitor:
    if bus is None:
        bus = EventBus()
    return CampaignMonitor(bus=bus, campaign_registry=registry)


# ---------------------------------------------------------------------------
# Test 1: get_snapshot() returns CampaignMonitorSnapshot
# ---------------------------------------------------------------------------

def test_snapshot_returns_correct_type():
    mon = _make_monitor()
    snap = mon.get_snapshot()
    assert isinstance(snap, CampaignMonitorSnapshot)


# ---------------------------------------------------------------------------
# Test 2: step_timeline ring buffer capped at 100
# ---------------------------------------------------------------------------

def test_step_timeline_capped_at_100(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()
    for i in range(120):
        isolated_bus.publish("campaign.step", {"campaign_id": f"c-{i}", "step": "run"})
    snap = mon.get_snapshot()
    assert len(snap.step_timeline) == 100
    mon.stop()


# ---------------------------------------------------------------------------
# Test 3: titan_ops_feed ring buffer capped at 50
# ---------------------------------------------------------------------------

def test_titan_ops_feed_capped_at_50(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()
    for i in range(70):
        isolated_bus.publish("titan.exec", {"task_id": f"t-{i}"})
    snap = mon.get_snapshot()
    assert len(snap.titan_ops_feed) == 50
    mon.stop()


# ---------------------------------------------------------------------------
# Test 4: active_campaigns reflects registry state
# ---------------------------------------------------------------------------

def test_active_campaigns_reflects_registry():
    camp_a = MagicMock()
    camp_a.to_dict.return_value = {"campaign_id": "ca-001", "name": "Alpha", "status": "running"}
    camp_b = MagicMock()
    camp_b.to_dict.return_value = {"campaign_id": "ca-002", "name": "Beta", "status": "running"}

    reg = _make_registry(active=[camp_a, camp_b])
    mon = _make_monitor(registry=reg)
    snap = mon.get_snapshot()
    ids = [c["campaign_id"] for c in snap.active_campaigns]
    assert "ca-001" in ids
    assert "ca-002" in ids


# ---------------------------------------------------------------------------
# Test 5: _on_campaign_event appends to step_timeline with ts
# ---------------------------------------------------------------------------

def test_on_campaign_event_appends_with_ts():
    mon = _make_monitor()
    before = time.time()
    mon._on_campaign_event("campaign.step_started", {"campaign_id": "cx-1", "step": "node-A", "status": "running"})
    after = time.time()

    snap = mon.get_snapshot()
    assert len(snap.step_timeline) == 1
    ev = snap.step_timeline[0]
    assert ev["campaign_id"] == "cx-1"
    assert before <= ev["ts"] <= after


# ---------------------------------------------------------------------------
# Test 6: _on_titan_event appends to titan_ops_feed with ts
# ---------------------------------------------------------------------------

def test_on_titan_event_appends_with_ts():
    mon = _make_monitor()
    before = time.time()
    mon._on_titan_event("titan.shell_exec", {"task_id": "tx-99", "cmd": "ls"})
    after = time.time()

    snap = mon.get_snapshot()
    assert len(snap.titan_ops_feed) == 1
    ev = snap.titan_ops_feed[0]
    assert ev["topic"] == "titan.shell_exec"
    assert before <= ev["ts"] <= after


# ---------------------------------------------------------------------------
# Test 7: start() subscribes — campaign.* events captured
# ---------------------------------------------------------------------------

def test_start_subscribes_campaign_events(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()

    isolated_bus.publish("campaign.step_completed", {"campaign_id": "c-7", "step": "deploy"})
    isolated_bus.publish("titan.shell_exec", {"task_id": "t-7"})

    snap = mon.get_snapshot()
    assert len(snap.step_timeline) == 1
    assert len(snap.titan_ops_feed) == 1
    mon.stop()


# ---------------------------------------------------------------------------
# Test 8: stop() unsubscribes — no new events captured after stop
# ---------------------------------------------------------------------------

def test_stop_unsubscribes_both(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()
    isolated_bus.publish("campaign.step_started", {"campaign_id": "c-8", "step": "prepare"})
    mon.stop()

    # Events published after stop should NOT appear
    isolated_bus.publish("campaign.step_completed", {"campaign_id": "c-8b", "step": "deploy"})
    isolated_bus.publish("titan.exec", {"task_id": "t-8"})

    snap = mon.get_snapshot()
    assert len(snap.step_timeline) == 1  # only the pre-stop event
    assert len(snap.titan_ops_feed) == 0


# ---------------------------------------------------------------------------
# Test 9: snapshot is JSON-serialisable
# ---------------------------------------------------------------------------

def test_snapshot_is_json_serialisable():
    mon = _make_monitor()
    mon._on_campaign_event("campaign.step_started", {"campaign_id": "c-9", "step": "run", "status": "ok"})
    mon._on_titan_event("titan.exec", {"task_id": "t-9"})
    snap = mon.get_snapshot()
    serialised = json.dumps(snap.to_dict())
    reloaded = json.loads(serialised)
    assert "active_campaigns" in reloaded
    assert "step_timeline" in reloaded
    assert "titan_ops_feed" in reloaded


# ---------------------------------------------------------------------------
# Test 10: all required keys present in snapshot dict
# ---------------------------------------------------------------------------

def test_snapshot_dict_has_required_keys():
    mon = _make_monitor()
    snap = mon.get_snapshot()
    d = snap.to_dict()
    assert "active_campaigns" in d
    assert "step_timeline" in d
    assert "titan_ops_feed" in d


# ---------------------------------------------------------------------------
# Test 11: step_timeline evicts oldest on overflow
# ---------------------------------------------------------------------------

def test_step_timeline_evicts_oldest(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()
    for i in range(101):
        isolated_bus.publish("campaign.step", {"campaign_id": f"c-{i}", "step": f"s{i}", "status": "ok"})
    snap = mon.get_snapshot()
    assert len(snap.step_timeline) == 100
    # First event (c-0) should have been evicted
    ids = [ev["campaign_id"] for ev in snap.step_timeline]
    assert "c-0" not in ids
    assert "c-100" in ids
    mon.stop()


# ---------------------------------------------------------------------------
# Test 12: titan_ops_feed evicts oldest on overflow
# ---------------------------------------------------------------------------

def test_titan_ops_feed_evicts_oldest(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()
    for i in range(51):
        isolated_bus.publish("titan.exec", {"task_id": f"t-{i}"})
    snap = mon.get_snapshot()
    assert len(snap.titan_ops_feed) == 50
    # First event should have been evicted
    task_ids = [ev["payload"]["task_id"] for ev in snap.titan_ops_feed]
    assert "t-0" not in task_ids
    assert "t-50" in task_ids
    mon.stop()


# ---------------------------------------------------------------------------
# Test 13: double-stop is idempotent (no error)
# ---------------------------------------------------------------------------

def test_double_stop_is_idempotent(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()
    mon.stop()
    mon.stop()  # second call must be silent — no exception


# ---------------------------------------------------------------------------
# Test 14: empty registry returns empty active_campaigns
# ---------------------------------------------------------------------------

def test_empty_registry_returns_empty_active():
    reg = _make_registry(active=[])
    mon = _make_monitor(registry=reg)
    snap = mon.get_snapshot()
    assert snap.active_campaigns == []


# ---------------------------------------------------------------------------
# Test 15: ts is a float in each event
# ---------------------------------------------------------------------------

def test_ts_is_float_in_events():
    mon = _make_monitor()
    mon._on_campaign_event("campaign.step_started", {"campaign_id": "c-15", "step": "go"})
    mon._on_titan_event("titan.exec", {"task_id": "t-15"})
    snap = mon.get_snapshot()
    assert isinstance(snap.step_timeline[0]["ts"], float)
    assert isinstance(snap.titan_ops_feed[0]["ts"], float)


# ---------------------------------------------------------------------------
# Test 16: campaign_id present in step_timeline entries
# ---------------------------------------------------------------------------

def test_campaign_id_in_step_timeline_entries():
    mon = _make_monitor()
    mon._on_campaign_event("campaign.step_started", {"campaign_id": "c-16", "step": "build"})
    snap = mon.get_snapshot()
    ev = snap.step_timeline[0]
    assert "campaign_id" in ev
    assert ev["campaign_id"] == "c-16"


# ---------------------------------------------------------------------------
# Test 17: topic present in titan_ops_feed entries
# ---------------------------------------------------------------------------

def test_topic_in_titan_ops_feed_entries():
    mon = _make_monitor()
    mon._on_titan_event("titan.rollback", {"task_id": "t-17"})
    snap = mon.get_snapshot()
    ev = snap.titan_ops_feed[0]
    assert "topic" in ev
    assert ev["topic"] == "titan.rollback"


# ---------------------------------------------------------------------------
# Test 18: get_snapshot() before start() returns empty lists (safe default)
# ---------------------------------------------------------------------------

def test_get_snapshot_before_start_is_safe(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    # Publish events before start — should NOT be captured
    isolated_bus.publish("campaign.step", {"campaign_id": "c-18", "step": "x"})
    isolated_bus.publish("titan.exec", {"task_id": "t-18"})

    snap = mon.get_snapshot()
    assert snap.step_timeline == []
    assert snap.titan_ops_feed == []


# ---------------------------------------------------------------------------
# Test 19: ring buffers are independent (campaign events don't go to titan feed)
# ---------------------------------------------------------------------------

def test_ring_buffers_are_independent(isolated_bus):
    mon = _make_monitor(bus=isolated_bus)
    mon.start()

    isolated_bus.publish("campaign.step_started", {"campaign_id": "c-19", "step": "build"})
    isolated_bus.publish("titan.exec", {"task_id": "t-19"})
    # A random unrelated event — should not appear in either buffer
    isolated_bus.publish("oracle.plan_stored", {"plan_id": "p-19"})

    snap = mon.get_snapshot()
    assert len(snap.step_timeline) == 1
    assert len(snap.titan_ops_feed) == 1
    # Confirm cross-contamination did not happen
    assert snap.step_timeline[0]["campaign_id"] == "c-19"
    assert snap.titan_ops_feed[0]["topic"] == "titan.exec"
    mon.stop()


# ---------------------------------------------------------------------------
# Test 20: snapshot dict has exactly the 3 top-level keys
# ---------------------------------------------------------------------------

def test_snapshot_dict_has_exactly_3_keys():
    mon = _make_monitor()
    d = mon.get_snapshot().to_dict()
    assert set(d.keys()) == {"active_campaigns", "step_timeline", "titan_ops_feed"}
