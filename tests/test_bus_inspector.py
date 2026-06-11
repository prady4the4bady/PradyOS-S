"""Phase 27: BusInspector core unit tests (20 tests)."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.bus_inspector import BusEvent, BusInspector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def insp() -> BusInspector:
    return BusInspector(max_size=10)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_init_empty_buffer(insp: BusInspector) -> None:
    """BusInspector initialises with empty buffer."""
    assert insp.get_events() == []


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------

def test_record_adds_event(insp: BusInspector) -> None:
    """record() adds an event to the buffer."""
    insp.record("test.topic")
    assert len(insp.get_events()) == 1


def test_record_returns_bus_event(insp: BusInspector) -> None:
    """record() returns a BusEvent instance."""
    result = insp.record("some.topic", {"key": "val"})
    assert isinstance(result, BusEvent)
    assert result.topic == "some.topic"
    assert result.payload == {"key": "val"}


def test_record_increments_topic_counter(insp: BusInspector) -> None:
    """record() increments the per-topic counter."""
    insp.record("a.topic")
    insp.record("a.topic")
    insp.record("b.topic")
    stats = insp.get_stats()
    assert stats["topics"]["a.topic"] == 2
    assert stats["topics"]["b.topic"] == 1


# ---------------------------------------------------------------------------
# get_events()
# ---------------------------------------------------------------------------

def test_get_events_returns_all(insp: BusInspector) -> None:
    """get_events() with no filter returns all buffered events."""
    for i in range(5):
        insp.record(f"topic.{i}")
    assert len(insp.get_events()) == 5


def test_get_events_filter_by_topic(insp: BusInspector) -> None:
    """get_events(topic=...) filters to that topic only."""
    insp.record("alpha")
    insp.record("beta")
    insp.record("alpha")
    result = insp.get_events(topic="alpha")
    assert len(result) == 2
    assert all(e.topic == "alpha" for e in result)


def test_get_events_limit(insp: BusInspector) -> None:
    """get_events(limit=N) returns at most N events."""
    for i in range(7):
        insp.record("t")
    result = insp.get_events(limit=3)
    assert len(result) == 3


def test_get_events_offset(insp: BusInspector) -> None:
    """get_events(offset=N) skips the first N events."""
    for i in range(5):
        insp.record("t", {"i": i})
    result = insp.get_events(offset=3)
    assert len(result) == 2
    assert result[0].payload == {"i": 3}


def test_get_events_combined_filters(insp: BusInspector) -> None:
    """get_events(topic, limit, offset) combined filters work correctly."""
    for i in range(8):
        insp.record("x" if i % 2 == 0 else "y", {"i": i})
    # 4 "x" events: i=0,2,4,6 — skip 1 (offset), take 2 (limit)
    result = insp.get_events(topic="x", limit=2, offset=1)
    assert len(result) == 2
    assert result[0].payload["i"] == 2
    assert result[1].payload["i"] == 4


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------

def test_get_stats_keys(insp: BusInspector) -> None:
    """get_stats() returns all required keys."""
    stats = insp.get_stats()
    assert "total_events" in stats
    assert "buffer_size" in stats
    assert "max_size" in stats
    assert "topics" in stats


def test_get_stats_total_events_beyond_overflow() -> None:
    """get_stats() total_events tracks beyond ring buffer overflow."""
    insp = BusInspector(max_size=5)
    for i in range(12):
        insp.record("t")
    stats = insp.get_stats()
    assert stats["total_events"] == 12
    assert stats["buffer_size"] == 5  # ring buffer capped


def test_get_stats_buffer_size(insp: BusInspector) -> None:
    """get_stats() buffer_size reflects current number of entries."""
    insp.record("a")
    insp.record("b")
    assert insp.get_stats()["buffer_size"] == 2


# ---------------------------------------------------------------------------
# Ring buffer overflow
# ---------------------------------------------------------------------------

def test_ring_buffer_respects_max_size() -> None:
    """Ring buffer evicts oldest events when max_size is exceeded."""
    insp = BusInspector(max_size=3)
    for i in range(5):
        insp.record("t", {"i": i})
    events = insp.get_events()
    assert len(events) == 3
    # Oldest three are i=2,3,4
    assert events[0].payload["i"] == 2
    assert events[-1].payload["i"] == 4


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------

def test_clear_empties_buffer_and_resets_counters(insp: BusInspector) -> None:
    """clear() empties the ring buffer and resets topic counters."""
    insp.record("t1")
    insp.record("t2")
    insp.clear()
    assert insp.get_events() == []
    stats = insp.get_stats()
    assert stats["buffer_size"] == 0
    assert stats["topics"] == {}
    assert stats["total_events"] == 0


# ---------------------------------------------------------------------------
# BusEvent.to_dict()
# ---------------------------------------------------------------------------

def test_bus_event_to_dict() -> None:
    """BusEvent.to_dict() returns expected keys."""
    ev = BusEvent(topic="foo", payload={"bar": 1}, timestamp=1_000_000.0)
    d = ev.to_dict()
    assert d["topic"] == "foo"
    assert d["payload"] == {"bar": 1}
    assert d["timestamp"] == 1_000_000.0


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

def test_record_default_timestamp_is_recent(insp: BusInspector) -> None:
    """record() default timestamp is within 1 second of now."""
    before = time.time()
    ev = insp.record("t")
    after = time.time()
    assert before <= ev.timestamp <= after


def test_record_default_payload_is_empty_dict(insp: BusInspector) -> None:
    """record() payload defaults to {} when None is passed."""
    ev = insp.record("t", payload=None)
    assert ev.payload == {}


# ---------------------------------------------------------------------------
# Multiple topics
# ---------------------------------------------------------------------------

def test_multiple_topics_tracked_independently(insp: BusInspector) -> None:
    """Multiple topics are counted independently in stats."""
    for _ in range(3):
        insp.record("alpha")
    for _ in range(5):
        insp.record("beta")
    topics = insp.get_stats()["topics"]
    assert topics["alpha"] == 3
    assert topics["beta"] == 5


# ---------------------------------------------------------------------------
# Oldest-first ordering
# ---------------------------------------------------------------------------

def test_get_events_oldest_first(insp: BusInspector) -> None:
    """get_events() returns events in oldest-first (insertion) order."""
    ts = [100.0, 200.0, 300.0]
    for t in ts:
        insp.record("t", timestamp=t)
    events = insp.get_events()
    assert [e.timestamp for e in events] == ts


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_thread_safety_concurrent_records() -> None:
    """100 concurrent record() calls all register successfully."""
    insp = BusInspector(max_size=200)
    errors: list[Exception] = []

    def worker() -> None:
        try:
            insp.record("concurrent", {"thread": threading.current_thread().name})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Errors in threads: {errors}"
    stats = insp.get_stats()
    assert stats["total_events"] == 100
    assert stats["topics"].get("concurrent", 0) == 100
