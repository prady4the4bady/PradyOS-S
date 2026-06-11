"""Phase 63C — 20 tests for pradyos.core.aggregate_root."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.aggregate_root import (
    AggregateRegistry,
    AggregateRoot,
    DomainEvent,
)


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_version_zero_event_count_zero():
    agg = AggregateRoot("a1")
    assert agg.version == 0
    assert agg.event_count() == 0


# ── apply ─────────────────────────────────────────────────────────────────────

def test_apply_returns_domain_event():
    agg = AggregateRoot("a1")
    event = agg.apply("created", {"x": 1})
    assert isinstance(event, DomainEvent)
    assert event.event_type == "created"


def test_first_apply_increments_version_to_1():
    agg = AggregateRoot("a1")
    event = agg.apply("created", {})
    assert event.version == 1
    assert agg.version == 1


def test_second_apply_increments_version_to_2():
    agg = AggregateRoot("a1")
    agg.apply("created", {})
    e2 = agg.apply("updated", {})
    assert e2.version == 2
    assert agg.version == 2


def test_apply_merges_payload_into_state():
    agg = AggregateRoot("a1")
    agg.apply("created", {"name": "alice"})
    agg.apply("updated", {"role": "admin"})
    assert agg.get_state() == {"name": "alice", "role": "admin"}


# ── get_state / get_events ───────────────────────────────────────────────────

def test_get_state_returns_copy():
    agg = AggregateRoot("a1")
    agg.apply("created", {"x": 1})
    state = agg.get_state()
    state["x"] = 99  # mutate the returned copy
    assert agg.get_state()["x"] == 1  # internal unaffected


def test_get_events_since_version_zero_returns_all():
    agg = AggregateRoot("a1")
    agg.apply("a", {})
    agg.apply("b", {})
    agg.apply("c", {})
    assert len(agg.get_events(since_version=0)) == 3


def test_get_events_since_version_1_skips_first():
    agg = AggregateRoot("a1")
    agg.apply("a", {})
    agg.apply("b", {})
    agg.apply("c", {})
    events = agg.get_events(since_version=1)
    assert [e.version for e in events] == [2, 3]


def test_get_events_sorted_ascending_by_version():
    agg = AggregateRoot("a1")
    for et in ["a", "b", "c", "d"]:
        agg.apply(et, {})
    events = agg.get_events()
    versions = [e.version for e in events]
    assert versions == sorted(versions)


# ── rebuild_state ─────────────────────────────────────────────────────────────

def test_rebuild_state_replays_and_restores_state():
    agg = AggregateRoot("a1")
    agg.apply("created", {"name": "alice"})
    agg.apply("updated", {"role": "admin"})
    snapshot = agg.get_events()

    new_agg = AggregateRoot("a1")
    new_agg.apply("noise", {"junk": True})  # dirty state to overwrite
    new_agg.rebuild_state(snapshot)
    assert new_agg.get_state() == {"name": "alice", "role": "admin"}


def test_rebuild_state_resets_version():
    agg = AggregateRoot("a1")
    agg.apply("a", {})
    agg.apply("b", {})

    new_agg = AggregateRoot("a1")
    new_agg.apply("x", {})
    new_agg.apply("y", {})
    new_agg.apply("z", {})  # version=3 before rebuild
    new_agg.rebuild_state(agg.get_events())
    assert new_agg.version == 2


def test_rebuild_state_resets_event_count():
    agg = AggregateRoot("a1")
    agg.apply("a", {})
    agg.apply("b", {})

    new_agg = AggregateRoot("a1")
    for _ in range(5):
        new_agg.apply("noise", {})
    new_agg.rebuild_state(agg.get_events())
    assert new_agg.event_count() == 2


# ── AggregateRegistry ────────────────────────────────────────────────────────

def test_registry_get_or_create_creates_new():
    reg = AggregateRegistry()
    agg = reg.get_or_create("a1")
    assert isinstance(agg, AggregateRoot)
    assert reg.count() == 1


def test_registry_get_or_create_returns_same_instance():
    reg = AggregateRegistry()
    a1 = reg.get_or_create("a1")
    a2 = reg.get_or_create("a1")
    assert a1 is a2


def test_registry_get_unknown_returns_none():
    reg = AggregateRegistry()
    assert reg.get("phantom") is None


def test_registry_list_sorted():
    reg = AggregateRegistry()
    reg.get_or_create("zzz")
    reg.get_or_create("aaa")
    reg.get_or_create("mmm")
    ids = [a["aggregate_id"] for a in reg.list_aggregates()]
    assert ids == ["aaa", "mmm", "zzz"]


def test_registry_list_entry_has_required_keys():
    reg = AggregateRegistry()
    reg.get_or_create("a1").apply("created", {"x": 1})
    entry = reg.list_aggregates()[0]
    for key in ("aggregate_id", "version", "event_count", "state_keys"):
        assert key in entry
    assert entry["version"] == 1
    assert entry["event_count"] == 1
    assert entry["state_keys"] == 1


def test_registry_delete_returns_true_removes():
    reg = AggregateRegistry()
    reg.get_or_create("a1")
    assert reg.delete("a1") is True
    assert reg.get("a1") is None


def test_registry_delete_unknown_returns_false():
    reg = AggregateRegistry()
    assert reg.delete("phantom") is False


def test_registry_count_correct():
    reg = AggregateRegistry()
    reg.get_or_create("a1")
    reg.get_or_create("a2")
    reg.get_or_create("a3")
    assert reg.count() == 3


# ── concurrency ───────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_applies():
    agg = AggregateRoot("hot")
    errors: list[Exception] = []

    def worker(i: int):
        try:
            agg.apply("ping", {"i": i})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert agg.event_count() == 50
    assert agg.version == 50
    versions = sorted(e.version for e in agg.get_events())
    assert versions == list(range(1, 51))  # no duplicates, no gaps
