"""Phase 78 — unit tests for SkipList (ordered probabilistic index)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.skiplist import SkipList


# ── construction ──────────────────────────────────────────────────────────────

def test_default_max_level():
    assert SkipList().stats()["max_level"] == 16


def test_invalid_max_level_raises():
    with pytest.raises(ValueError):
        SkipList(max_level=0)


def test_invalid_p_raises():
    for bad in (0.0, 1.0, -0.5, 2.0):
        with pytest.raises(ValueError):
            SkipList(p=bad)


# ── insert / search ───────────────────────────────────────────────────────────

def test_insert_search_round_trip():
    s = SkipList(seed=1)
    s.insert("a", 100)
    assert s.search("a") == 100


def test_search_absent_returns_none():
    assert SkipList().search("ghost") is None


def test_insert_overwrites_value():
    s = SkipList(seed=1)
    s.insert("k", 1)
    s.insert("k", 2)
    assert s.search("k") == 2
    assert len(s) == 1


def test_contains_operator():
    s = SkipList(seed=1)
    s.insert("a", 1)
    assert "a" in s
    assert "b" not in s


def test_len_tracks_size():
    s = SkipList(seed=1)
    for k in ("a", "b", "c"):
        s.insert(k, k)
    assert len(s) == 3


def test_arbitrary_values():
    s = SkipList(seed=1)
    s.insert("i", 42)
    s.insert("d", {"x": [1, 2]})
    s.insert("l", [1, 2, 3])
    assert s.search("i") == 42
    assert s.search("d") == {"x": [1, 2]}
    assert s.search("l") == [1, 2, 3]


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_present_returns_true():
    s = SkipList(seed=1)
    s.insert("a", 1)
    assert s.delete("a") is True


def test_delete_absent_returns_false():
    assert SkipList().delete("ghost") is False


def test_delete_then_search_none():
    s = SkipList(seed=1)
    s.insert("a", 1)
    s.delete("a")
    assert s.search("a") is None


def test_delete_reduces_size():
    s = SkipList(seed=1)
    s.insert("a", 1); s.insert("b", 2)
    s.delete("a")
    assert len(s) == 1


# ── ordering / range ──────────────────────────────────────────────────────────

def test_items_sorted_after_unordered_insert():
    s = SkipList(seed=1)
    for k in ("c", "a", "e", "b", "d"):
        s.insert(k, k)
    assert [k for k, _ in s.items()] == ["a", "b", "c", "d", "e"]


def test_range_inclusive_bounds():
    s = SkipList(seed=1)
    for k in ("a", "b", "c", "d", "e"):
        s.insert(k, k.upper())
    assert s.range_query("b", "d") == [("b", "B"), ("c", "C"), ("d", "D")]


def test_range_single_element():
    s = SkipList(seed=1)
    for k in ("a", "b", "c"):
        s.insert(k, k)
    assert s.range_query("b", "b") == [("b", "b")]


def test_range_empty_when_lo_gt_hi():
    s = SkipList(seed=1)
    for k in ("a", "b", "c"):
        s.insert(k, k)
    assert s.range_query("z", "a") == []


def test_range_no_match():
    s = SkipList(seed=1)
    s.insert("a", 1); s.insert("b", 2)
    assert s.range_query("x", "y") == []


def test_range_is_sorted():
    s = SkipList(seed=1)
    for k in ("e", "a", "c", "b", "d"):
        s.insert(k, k)
    keys = [k for k, _ in s.range_query("a", "e")]
    assert keys == sorted(keys)


def test_ordering_invariant_after_mixed_ops():
    s = SkipList(seed=7)
    keys = [f"{i:03d}" for i in range(200)]
    random.Random(1).shuffle(keys)
    for k in keys:
        s.insert(k, int(k))
    for k in keys[:60]:
        s.delete(k)
    items = s.items()
    got = [k for k, _ in items]
    assert got == sorted(got)
    assert len(got) == 140
    assert all(s.search(k) == int(k) for k in keys[60:])
    assert all(s.search(k) is None for k in keys[:60])


def test_large_dataset_all_searchable():
    s = SkipList(seed=3)
    for i in range(200):
        s.insert(f"{i:03d}", i)
    assert len(s) == 200
    assert all(s.search(f"{i:03d}") == i for i in range(200))
    keys = [k for k, _ in s.items()]
    assert keys == sorted(keys)


# ── clear / stats ─────────────────────────────────────────────────────────────

def test_clear_resets():
    s = SkipList(seed=1)
    s.insert("a", 1); s.insert("b", 2)
    s.clear()
    assert len(s) == 0
    assert s.search("a") is None


def test_stats_keys():
    stats = SkipList().stats()
    for key in ("size", "level_count", "max_level"):
        assert key in stats


def test_stats_size_tracks():
    s = SkipList(seed=1)
    s.insert("a", 1); s.insert("b", 2)
    assert s.stats()["size"] == 2


def test_stats_level_count_within_bounds():
    s = SkipList(seed=1, max_level=8)
    for i in range(100):
        s.insert(f"{i:03d}", i)
    lc = s.stats()["level_count"]
    assert 1 <= lc <= 8


# ── error handling ────────────────────────────────────────────────────────────

def test_insert_none_key_raises():
    with pytest.raises(ValueError):
        SkipList().insert(None, 1)


def test_search_none_key_raises():
    with pytest.raises(ValueError):
        SkipList().search(None)


def test_delete_none_key_raises():
    with pytest.raises(ValueError):
        SkipList().delete(None)


def test_range_none_bound_raises():
    with pytest.raises(ValueError):
        SkipList().range_query(None, "x")
    with pytest.raises(ValueError):
        SkipList().range_query("a", None)


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_inserts_are_thread_safe():
    s = SkipList(seed=5)
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(100):
                s.insert(f"{base:02d}-{i:03d}", base * 1000 + i)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(s) == 1000
    assert s.search("05-050") == 5050
    keys = [k for k, _ in s.items()]
    assert keys == sorted(keys)
