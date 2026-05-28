"""Phase 51C — 20 tests for pradyos.core.statesync.StateSyncManager."""
from __future__ import annotations

import time

import pytest

from pradyos.core.pubsub import PubSubBroker
from pradyos.core.statesync import StateSyncManager, SyncPeer, SyncSession


def _mgr_with_two_brokers() -> tuple[StateSyncManager, PubSubBroker, PubSubBroker]:
    mgr = StateSyncManager()
    a = PubSubBroker()
    b = PubSubBroker()
    mgr.register_broker("a", a)
    mgr.register_broker("b", b)
    return mgr, a, b


# ── init / register ──────────────────────────────────────────────────────────

def test_init_empty():
    mgr = StateSyncManager()
    assert mgr._sessions == {}
    assert mgr._brokers == {}


def test_register_broker_stores():
    mgr = StateSyncManager()
    broker = PubSubBroker()
    mgr.register_broker("x", broker)
    assert mgr._brokers["x"] is broker


def test_register_broker_overwrites_silently():
    mgr = StateSyncManager()
    b1, b2 = PubSubBroker(), PubSubBroker()
    mgr.register_broker("x", b1)
    mgr.register_broker("x", b2)
    assert mgr._brokers["x"] is b2


# ── create_session validation ────────────────────────────────────────────────

def test_create_session_unknown_broker_a_raises():
    mgr = StateSyncManager()
    mgr.register_broker("b", PubSubBroker())
    with pytest.raises(ValueError, match="unknown broker"):
        mgr.create_session("a", "b", ["x"], ["x"])


def test_create_session_unknown_broker_b_raises():
    mgr = StateSyncManager()
    mgr.register_broker("a", PubSubBroker())
    with pytest.raises(ValueError, match="unknown broker"):
        mgr.create_session("a", "missing", ["x"], ["x"])


def test_create_session_returns_syncsession():
    mgr, _, _ = _mgr_with_two_brokers()
    s = mgr.create_session("a", "b", ["x"], ["x"])
    assert isinstance(s, SyncSession)


def test_create_session_is_active():
    mgr, _, _ = _mgr_with_two_brokers()
    s = mgr.create_session("a", "b", ["x"], ["x"])
    assert s.active is True


def test_create_session_has_unique_uuid_id():
    mgr, _, _ = _mgr_with_two_brokers()
    s1 = mgr.create_session("a", "b", ["x"], ["x"])
    s2 = mgr.create_session("a", "b", ["y"], ["y"])
    assert s1.id != s2.id
    int(s1.id, 16)


# ── A→B and B→A sync ─────────────────────────────────────────────────────────

def test_sync_a_to_b():
    mgr, broker_a, broker_b = _mgr_with_two_brokers()
    received: list[dict] = []
    broker_b.subscribe("topic1", lambda msg: received.append(msg))
    mgr.create_session("a", "b", ["topic1"], [])
    broker_a.publish("topic1", {"v": 1})
    assert any(m.get("v") == 1 for m in received)


def test_sync_b_to_a():
    mgr, broker_a, broker_b = _mgr_with_two_brokers()
    received: list[dict] = []
    broker_a.subscribe("topic2", lambda msg: received.append(msg))
    mgr.create_session("a", "b", [], ["topic2"])
    broker_b.publish("topic2", {"v": 2})
    assert any(m.get("v") == 2 for m in received)


# ── cycle detection ──────────────────────────────────────────────────────────

def test_cycle_detection_no_infinite_loop():
    mgr, broker_a, broker_b = _mgr_with_two_brokers()
    s = mgr.create_session("a", "b", ["x"], ["x"])
    # Publish once; cycle detection should prevent infinite forwarding.
    broker_a.publish("x", {"v": 1})
    # synced_count should be exactly 1 (one forward A→B) — NOT 2+.
    assert s.synced_count == 1


def test_synced_count_increments_per_forward():
    mgr, broker_a, broker_b = _mgr_with_two_brokers()
    s = mgr.create_session("a", "b", ["x"], [])
    broker_a.publish("x", {"v": 1})
    broker_a.publish("x", {"v": 2})
    broker_a.publish("x", {"v": 3})
    assert s.synced_count == 3


# ── stop_session ─────────────────────────────────────────────────────────────

def test_stop_session_returns_true_sets_inactive():
    mgr, _, _ = _mgr_with_two_brokers()
    s = mgr.create_session("a", "b", ["x"], ["x"])
    assert mgr.stop_session(s.id) is True
    assert s.active is False


def test_stop_session_unknown_returns_false():
    mgr = StateSyncManager()
    assert mgr.stop_session("phantom") is False


def test_stop_session_unsubscribes_so_no_more_forwards():
    mgr, broker_a, broker_b = _mgr_with_two_brokers()
    received: list[dict] = []
    broker_b.subscribe("x", lambda msg: received.append(msg))
    s = mgr.create_session("a", "b", ["x"], [])
    broker_a.publish("x", {"v": 1})  # forwarded
    mgr.stop_session(s.id)
    broker_a.publish("x", {"v": 2})  # NOT forwarded
    forwarded_vs = [m.get("v") for m in received if m.get("__synced__")]
    assert 1 in forwarded_vs
    assert 2 not in forwarded_vs


# ── introspection ────────────────────────────────────────────────────────────

def test_list_sessions_sorted_by_created_at():
    mgr, _, _ = _mgr_with_two_brokers()
    s1 = mgr.create_session("a", "b", ["x"], [])
    time.sleep(0.001)
    s2 = mgr.create_session("a", "b", ["y"], [])
    ids = [s.id for s in mgr.list_sessions()]
    assert ids == [s1.id, s2.id]


def test_list_sessions_active_only_filters():
    mgr, _, _ = _mgr_with_two_brokers()
    s1 = mgr.create_session("a", "b", ["x"], [])
    s2 = mgr.create_session("a", "b", ["y"], [])
    mgr.stop_session(s1.id)
    active = mgr.list_sessions(active_only=True)
    assert [s.id for s in active] == [s2.id]


def test_get_session_returns_correct():
    mgr, _, _ = _mgr_with_two_brokers()
    s = mgr.create_session("a", "b", ["x"], [])
    assert mgr.get_session(s.id) is s


def test_get_session_unknown_returns_none():
    mgr = StateSyncManager()
    assert mgr.get_session("phantom") is None


def test_count_includes_stopped():
    mgr, _, _ = _mgr_with_two_brokers()
    s1 = mgr.create_session("a", "b", ["x"], [])
    mgr.create_session("a", "b", ["y"], [])
    mgr.stop_session(s1.id)
    assert mgr.count() == 2
