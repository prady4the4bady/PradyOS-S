"""Phase 39C — 20 tests for pradyos.core.memory_store.MemoryStore."""
from __future__ import annotations

import time

import pytest

from pradyos.core.memory_store import MemoryEntry, MemoryStore
from pradyos.core.snapshot_store import SnapshotStore


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    m = MemoryStore()
    assert m._entries == {}
    assert m.count() == 0


# ── store ────────────────────────────────────────────────────────────────────

def test_store_returns_entry():
    m = MemoryStore()
    e = m.store("k1", {"x": 1})
    assert isinstance(e, MemoryEntry)
    assert e.value == {"x": 1}


def test_store_new_created_at_equals_updated_at():
    m = MemoryStore()
    e = m.store("k1", "v")
    assert e.created_at == e.updated_at


def test_store_upsert_preserves_created_at_updates_updated_at():
    m = MemoryStore()
    e1 = m.store("k1", "v1")
    orig_created = e1.created_at
    time.sleep(0.01)
    e2 = m.store("k1", "v2")
    assert e2.created_at == orig_created
    assert e2.updated_at > orig_created


def test_store_upsert_updates_value_and_tags():
    m = MemoryStore()
    m.store("k1", "v1", tags=["a"])
    e2 = m.store("k1", "v2", tags=["b", "c"])
    assert e2.value == "v2"
    assert e2.tags == ["b", "c"]


# ── recall ───────────────────────────────────────────────────────────────────

def test_recall_returns_entry_when_present():
    m = MemoryStore()
    m.store("k1", "hello")
    e = m.recall("k1")
    assert e is not None
    assert e.value == "hello"


def test_recall_returns_none_for_unknown_key():
    m = MemoryStore()
    assert m.recall("phantom") is None


def test_recall_returns_none_for_expired_entry():
    m = MemoryStore()
    m.store("k1", "v", ttl=0.001)
    time.sleep(0.01)
    assert m.recall("k1") is None


def test_recall_removes_expired_entry_from_dict():
    m = MemoryStore()
    m.store("k1", "v", ttl=0.001)
    time.sleep(0.01)
    m.recall("k1")
    assert "k1" not in m._entries


# ── search ───────────────────────────────────────────────────────────────────

def test_search_returns_matching_tag():
    m = MemoryStore()
    m.store("k1", "v1", tags=["a", "b"])
    m.store("k2", "v2", tags=["b", "c"])
    m.store("k3", "v3", tags=["c"])
    results = m.search("b")
    keys = [e.key for e in results]
    assert sorted(keys) == ["k1", "k2"]


def test_search_empty_for_unknown_tag():
    m = MemoryStore()
    m.store("k1", "v", tags=["a"])
    assert m.search("nope") == []


def test_search_excludes_expired():
    m = MemoryStore()
    m.store("k1", "v1", tags=["a"], ttl=0.001)
    m.store("k2", "v2", tags=["a"])
    time.sleep(0.01)
    results = m.search("a")
    keys = [e.key for e in results]
    assert keys == ["k2"]


def test_search_sorted_by_key():
    m = MemoryStore()
    m.store("zzz", "v", tags=["x"])
    m.store("aaa", "v", tags=["x"])
    m.store("mmm", "v", tags=["x"])
    keys = [e.key for e in m.search("x")]
    assert keys == ["aaa", "mmm", "zzz"]


# ── forget ───────────────────────────────────────────────────────────────────

def test_forget_returns_true_and_removes():
    m = MemoryStore()
    m.store("k1", "v")
    assert m.forget("k1") is True
    assert "k1" not in m._entries


def test_forget_returns_false_unknown():
    m = MemoryStore()
    assert m.forget("phantom") is False


# ── expire ───────────────────────────────────────────────────────────────────

def test_expire_removes_and_returns_count():
    m = MemoryStore()
    m.store("k1", "v", ttl=0.001)
    m.store("k2", "v", ttl=0.001)
    m.store("k3", "v")  # no ttl
    time.sleep(0.01)
    n = m.expire()
    assert n == 2
    assert "k3" in m._entries


def test_expire_keeps_non_expired():
    m = MemoryStore()
    m.store("k1", "v")  # no ttl
    m.store("k2", "v", ttl=1000.0)  # far future
    n = m.expire()
    assert n == 0
    assert len(m._entries) == 2


# ── count ─────────────────────────────────────────────────────────────────────

def test_count_returns_correct_number_without_calling_expire():
    m = MemoryStore()
    m.store("k1", "v")
    m.store("k2", "v")
    assert m.count() == 2


def test_count_counts_all_including_expired():
    m = MemoryStore()
    m.store("k1", "v", ttl=0.001)
    m.store("k2", "v")
    time.sleep(0.01)
    # count() does not evict expired — they stay until recall/search/expire
    assert m.count() == 2


# ── snapshot integration ──────────────────────────────────────────────────────

def test_snapshot_integration_persists_and_reloads(tmp_path):
    ss = SnapshotStore(base_dir=tmp_path)
    m1 = MemoryStore(snapshot_store=ss)
    m1.store("k1", {"hello": "world"}, tags=["greeting"])
    m1.store("k2", 42)

    m2 = MemoryStore(snapshot_store=ss)
    e = m2.recall("k1")
    assert e is not None
    assert e.value == {"hello": "world"}
    assert "greeting" in e.tags
    assert m2.recall("k2").value == 42
