"""Phase 48C — 20 tests for pradyos.core.event_store.EventStore."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.event_store import Event, EventStore
from pradyos.core.snapshot_store import SnapshotStore


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_no_streams():
    es = EventStore()
    assert es._streams == {}


# ── append ────────────────────────────────────────────────────────────────────

def test_append_returns_event():
    es = EventStore()
    e = es.append("orders", "created", {"id": 1})
    assert isinstance(e, Event)


def test_append_sequence_starts_at_1():
    es = EventStore()
    e = es.append("orders", "created", {})
    assert e.sequence == 1


def test_append_second_event_sequence_2():
    es = EventStore()
    es.append("orders", "created", {})
    e2 = es.append("orders", "updated", {})
    assert e2.sequence == 2


def test_append_id_non_empty_hex():
    es = EventStore()
    e = es.append("orders", "created", {})
    assert isinstance(e.id, str)
    assert len(e.id) >= 16
    # uuid4 hex is hex chars only
    int(e.id, 16)


def test_append_occurred_at_is_recent():
    es = EventStore()
    e = es.append("orders", "created", {})
    assert abs(e.occurred_at - time.time()) < 2.0


# ── read ──────────────────────────────────────────────────────────────────────

def test_read_returns_all_from_seq_zero():
    es = EventStore()
    es.append("orders", "a", {})
    es.append("orders", "b", {})
    es.append("orders", "c", {})
    evs = es.read("orders", from_seq=0)
    assert len(evs) == 3


def test_read_filters_correctly_from_seq_1():
    es = EventStore()
    es.append("orders", "a", {})  # seq 1
    es.append("orders", "b", {})  # seq 2
    es.append("orders", "c", {})  # seq 3
    evs = es.read("orders", from_seq=1)
    seqs = [e.sequence for e in evs]
    assert seqs == [2, 3]


def test_read_unknown_stream_empty():
    es = EventStore()
    assert es.read("phantom") == []


# ── project ───────────────────────────────────────────────────────────────────

def test_project_unknown_stream_returns_initial():
    es = EventStore()
    state = es.project("phantom", lambda s, e: s, initial={"x": 1})
    assert state == {"x": 1}


def test_project_folds_events():
    es = EventStore()
    es.append("counter", "increment", {"by": 1})
    es.append("counter", "increment", {"by": 2})
    es.append("counter", "increment", {"by": 3})

    def reducer(state: dict, event) -> dict:
        state["total"] = state.get("total", 0) + event.payload.get("by", 0)
        return state

    state = es.project("counter", reducer, initial={"total": 0})
    assert state["total"] == 6


def test_project_empty_stream_returns_initial():
    es = EventStore()
    es.append("other", "x", {})  # different stream
    state = es.project("counter", lambda s, e: s, initial={})
    assert state == {}


# ── stream_names / event_count ────────────────────────────────────────────────

def test_stream_names_sorted():
    es = EventStore()
    es.append("zzz", "x", {})
    es.append("aaa", "x", {})
    es.append("mmm", "x", {})
    assert es.stream_names() == ["aaa", "mmm", "zzz"]


def test_stream_names_empty():
    es = EventStore()
    assert es.stream_names() == []


def test_event_count_total():
    es = EventStore()
    es.append("a", "x", {})
    es.append("a", "x", {})
    es.append("b", "x", {})
    assert es.event_count() == 3


def test_event_count_scoped():
    es = EventStore()
    es.append("a", "x", {})
    es.append("a", "x", {})
    es.append("b", "x", {})
    assert es.event_count("a") == 2
    assert es.event_count("b") == 1


# ── Event.to_dict ─────────────────────────────────────────────────────────────

def test_event_to_dict_has_all_keys():
    es = EventStore()
    e = es.append("orders", "created", {"x": 1})
    d = e.to_dict()
    for key in ("id", "stream", "event_type", "payload", "sequence", "occurred_at"):
        assert key in d


# ── persistence ───────────────────────────────────────────────────────────────

def test_persistence_reload_events(tmp_path):
    store = SnapshotStore(base_dir=tmp_path)
    es1 = EventStore(snapshot_store=store)
    es1.append("orders", "created", {"id": 1})
    es1.append("orders", "updated", {"id": 1, "status": "paid"})

    es2 = EventStore(snapshot_store=store)
    evs = es2.read("orders")
    assert len(evs) == 2
    assert evs[0].event_type == "created"
    assert evs[1].payload == {"id": 1, "status": "paid"}


def test_persistence_sequence_preserved(tmp_path):
    store = SnapshotStore(base_dir=tmp_path)
    es1 = EventStore(snapshot_store=store)
    es1.append("s", "a", {})
    es1.append("s", "b", {})

    es2 = EventStore(snapshot_store=store)
    evs = es2.read("s")
    assert [e.sequence for e in evs] == [1, 2]
    # Appending after reload should continue from 3
    e3 = es2.append("s", "c", {})
    assert e3.sequence == 3


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_no_sequence_duplicates():
    es = EventStore()
    errors: list[Exception] = []

    def worker(i: int):
        try:
            es.append("hot", "tick", {"i": i})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    evs = es.read("hot")
    assert len(evs) == 40
    seqs = sorted(e.sequence for e in evs)
    assert seqs == list(range(1, 41))  # no duplicates, no gaps
