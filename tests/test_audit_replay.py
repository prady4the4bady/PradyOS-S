"""Phase 25 — AuditReplayEngine unit tests (20 tests)."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.audit_replay import AuditReplayEngine, ReplayEntry, ReplaySnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeLedger:
    """Minimal ledger stub for testing."""

    def __init__(self, entries: list[dict] | None = None) -> None:
        self.entries: list[dict] = entries or []


# ---------------------------------------------------------------------------
# 1. AuditReplayEngine initialises with no entries
# ---------------------------------------------------------------------------

def test_engine_initialises_empty() -> None:
    engine = AuditReplayEngine()
    assert engine._internal == []


# ---------------------------------------------------------------------------
# 2. replay() with no entries returns empty snapshot
# ---------------------------------------------------------------------------

def test_replay_no_entries_returns_empty_snapshot() -> None:
    engine = AuditReplayEngine()
    snap = engine.replay(at=time.time())
    assert snap.entries == []
    assert snap.state == {}
    assert snap.event_count == 0


# ---------------------------------------------------------------------------
# 3. add_entry() adds to internal list
# ---------------------------------------------------------------------------

def test_add_entry_grows_internal_list() -> None:
    engine = AuditReplayEngine()
    engine.add_entry("test_event", {"k": "v"})
    assert len(engine._internal) == 1


# ---------------------------------------------------------------------------
# 4. replay() returns ReplaySnapshot
# ---------------------------------------------------------------------------

def test_replay_returns_snapshot_instance() -> None:
    engine = AuditReplayEngine()
    snap = engine.replay(at=time.time())
    assert isinstance(snap, ReplaySnapshot)


# ---------------------------------------------------------------------------
# 5. replay() filters entries after `at` timestamp
# ---------------------------------------------------------------------------

def test_replay_filters_future_entries() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    engine.add_entry("past", {"x": 1}, timestamp=now - 100)
    engine.add_entry("future", {"x": 2}, timestamp=now + 100)
    snap = engine.replay(at=now)
    assert snap.event_count == 1
    assert snap.entries[0].event_type == "past"


# ---------------------------------------------------------------------------
# 6. replay() includes entries exactly at `at` timestamp
# ---------------------------------------------------------------------------

def test_replay_includes_entry_at_exact_timestamp() -> None:
    engine = AuditReplayEngine()
    ts = 1_000_000.0
    engine.add_entry("exact", {"val": 42}, timestamp=ts)
    snap = engine.replay(at=ts)
    assert snap.event_count == 1
    assert snap.entries[0].timestamp == ts


# ---------------------------------------------------------------------------
# 7. replay() sorts entries by timestamp ascending
# ---------------------------------------------------------------------------

def test_replay_sorts_ascending() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    engine.add_entry("third", {}, timestamp=now - 1)
    engine.add_entry("first", {}, timestamp=now - 3)
    engine.add_entry("second", {}, timestamp=now - 2)
    snap = engine.replay(at=now)
    types = [e.event_type for e in snap.entries]
    assert types == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# 8. replay() reconstructs state via payload merge
# ---------------------------------------------------------------------------

def test_replay_reconstructs_state_from_payload() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    engine.add_entry("boot", {"status": "starting"}, timestamp=now - 10)
    snap = engine.replay(at=now)
    assert snap.state == {"status": "starting"}


# ---------------------------------------------------------------------------
# 9. replay() event_count matches filtered entries
# ---------------------------------------------------------------------------

def test_replay_event_count_matches_filtered() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    for i in range(5):
        engine.add_entry(f"e{i}", {}, timestamp=now - (5 - i))
    engine.add_entry("future", {}, timestamp=now + 100)
    snap = engine.replay(at=now)
    assert snap.event_count == 5
    assert snap.event_count == len(snap.entries)


# ---------------------------------------------------------------------------
# 10. replay() with multiple entries accumulates state
# ---------------------------------------------------------------------------

def test_replay_accumulates_state_across_entries() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    engine.add_entry("init", {"a": 1}, timestamp=now - 3)
    engine.add_entry("update", {"b": 2}, timestamp=now - 2)
    engine.add_entry("more", {"c": 3}, timestamp=now - 1)
    snap = engine.replay(at=now)
    assert snap.state == {"a": 1, "b": 2, "c": 3}


# ---------------------------------------------------------------------------
# 11. replay() later payload key overwrites earlier
# ---------------------------------------------------------------------------

def test_replay_later_key_overwrites_earlier() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    engine.add_entry("first", {"status": "starting"}, timestamp=now - 2)
    engine.add_entry("second", {"status": "running"}, timestamp=now - 1)
    snap = engine.replay(at=now)
    assert snap.state["status"] == "running"


# ---------------------------------------------------------------------------
# 12. clear() removes all internal entries
# ---------------------------------------------------------------------------

def test_clear_removes_all_entries() -> None:
    engine = AuditReplayEngine()
    now = time.time()
    for i in range(5):
        engine.add_entry(f"e{i}", {}, timestamp=now - i)
    engine.clear()
    assert engine._internal == []
    snap = engine.replay(at=now)
    assert snap.event_count == 0


# ---------------------------------------------------------------------------
# 13. ReplayEntry.to_dict() has required keys
# ---------------------------------------------------------------------------

def test_replay_entry_to_dict_has_required_keys() -> None:
    entry = ReplayEntry(timestamp=1.0, event_type="test", payload={"k": "v"})
    d = entry.to_dict()
    assert "timestamp" in d
    assert "event_type" in d
    assert "payload" in d


# ---------------------------------------------------------------------------
# 14. ReplaySnapshot.to_dict() has required keys
# ---------------------------------------------------------------------------

def test_replay_snapshot_to_dict_has_required_keys() -> None:
    snap = ReplaySnapshot(at=1.0, entries=[], state={}, event_count=0)
    d = snap.to_dict()
    assert "at" in d
    assert "entries" in d
    assert "state" in d
    assert "event_count" in d


# ---------------------------------------------------------------------------
# 15. replay() with ledger=None uses internal entries
# ---------------------------------------------------------------------------

def test_replay_uses_internal_when_ledger_is_none() -> None:
    engine = AuditReplayEngine(ledger=None)
    now = time.time()
    engine.add_entry("internal_event", {"x": 99}, timestamp=now - 1)
    snap = engine.replay(at=now)
    assert snap.event_count == 1
    assert snap.state == {"x": 99}


# ---------------------------------------------------------------------------
# 16. replay() with provided ledger uses ledger.entries
# ---------------------------------------------------------------------------

def test_replay_uses_provided_ledger() -> None:
    now = time.time()
    ledger = _FakeLedger(entries=[
        {"timestamp": now - 5, "event_type": "ledger_event", "payload": {"src": "ledger"}},
    ])
    engine = AuditReplayEngine(ledger=ledger)
    snap = engine.replay(at=now)
    assert snap.event_count == 1
    assert snap.state == {"src": "ledger"}


# ---------------------------------------------------------------------------
# 17. add_entry() returns ReplayEntry
# ---------------------------------------------------------------------------

def test_add_entry_returns_replay_entry() -> None:
    engine = AuditReplayEngine()
    entry = engine.add_entry("my_event", {"foo": "bar"})
    assert isinstance(entry, ReplayEntry)
    assert entry.event_type == "my_event"
    assert entry.payload == {"foo": "bar"}


# ---------------------------------------------------------------------------
# 18. add_entry() default timestamp is recent (within 1 second)
# ---------------------------------------------------------------------------

def test_add_entry_default_timestamp_is_recent() -> None:
    before = time.time()
    engine = AuditReplayEngine()
    entry = engine.add_entry("ts_test", {})
    after = time.time()
    assert before <= entry.timestamp <= after


# ---------------------------------------------------------------------------
# 19. replay() with no payload in entry treats payload as {}
# ---------------------------------------------------------------------------

def test_replay_missing_payload_treated_as_empty() -> None:
    now = time.time()
    ledger = _FakeLedger(entries=[
        {"timestamp": now - 1, "event_type": "no_payload"},
    ])
    engine = AuditReplayEngine(ledger=ledger)
    snap = engine.replay(at=now)
    assert snap.event_count == 1
    assert snap.state == {}
    assert snap.entries[0].payload == {}


# ---------------------------------------------------------------------------
# 20. thread safety: 50 concurrent add_entry() calls all register
# ---------------------------------------------------------------------------

def test_thread_safety_concurrent_add_entries() -> None:
    engine = AuditReplayEngine()
    threads = []
    for i in range(50):
        t = threading.Thread(
            target=engine.add_entry,
            args=(f"event_{i}", {"i": i}),
        )
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(engine._internal) == 50
