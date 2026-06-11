"""Phase 159 — unit tests for ScapegoatTree (pradyos/core/scapegoat_tree.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.scapegoat_tree import ScapegoatTree, ScapegoatTreeError


def _hbound(n, alpha):
    return math.log(n) / math.log(1 / alpha) if n > 1 else 1


# ── differential vs sorted set + height bound (centerpieces) ──────────────────────────────

def test_inorder_sorted_differential():
    rng = random.Random(1)
    for alpha in (0.55, 2 / 3, 0.75, 0.9):
        for _ in range(20):
            t = ScapegoatTree(alpha); s = set()
            for _ in range(300):
                x = rng.randint(0, 400)
                if rng.random() < 0.65:
                    assert t.insert(x) == (x not in s); s.add(x)
                else:
                    assert t.delete(x) == (x in s); s.discard(x)
                if s:
                    assert t.height() <= _hbound(len(s), alpha) + 3
            assert t.in_order() == sorted(s)
            assert t.minimum() == (min(s) if s else None)
            assert t.maximum() == (max(s) if s else None)


def test_contains_differential():
    rng = random.Random(2)
    t = ScapegoatTree(); s = set()
    for _ in range(500):
        x = rng.randint(0, 300); t.insert(x); s.add(x)
    assert all(t.contains(k) == (k in s) for k in range(0, 300))


def test_sorted_insert_height_bounded():
    t = ScapegoatTree(2 / 3)
    for i in range(5000):
        t.insert(i)
    assert t.in_order() == list(range(5000)) and t.height() <= _hbound(5000, 2 / 3) + 2


def test_sorted_delete_height_bounded():
    t = ScapegoatTree(2 / 3)
    for i in range(5000):
        t.insert(i)
    for i in range(2500):
        t.delete(i)
    assert t.in_order() == list(range(2500, 5000)) and t.size == 2500
    assert t.height() <= _hbound(2500, 2 / 3) + 2


def test_reverse_insert():
    t = ScapegoatTree(2 / 3)
    for i in range(3000, 0, -1):
        t.insert(i)
    assert t.in_order() == list(range(1, 3001)) and t.height() <= _hbound(3000, 2 / 3) + 2


def test_large_shuffled():
    rng = random.Random(3)
    t = ScapegoatTree(2 / 3); big = list(range(4000)); rng.shuffle(big)
    for v in big:
        t.insert(v)
    assert t.in_order() == list(range(4000)) and t.height() <= _hbound(4000, 2 / 3) + 2


def test_delete_all_empty():
    rng = random.Random(4)
    t = ScapegoatTree(); keys = list(range(500)); rng.shuffle(keys)
    for k in keys:
        t.insert(k)
    rng.shuffle(keys)
    for k in keys:
        t.delete(k)
    assert t.size == 0 and t.in_order() == [] and t.height() == 0


# ── semantics ──────────────────────────────────────────────────────────────────────────────

def test_dup_ignored():
    t = ScapegoatTree()
    assert t.insert(5) is True and t.insert(5) is False and t.size == 1


def test_delete_absent():
    assert ScapegoatTree().delete(99) is False


def test_delete_node_types():
    t = ScapegoatTree(0.9)
    for v in (50, 30, 70, 20, 40, 60, 80):
        t.insert(v)
    for v in (20, 30, 50):
        assert t.delete(v) is True
    assert t.in_order() == [40, 60, 70, 80]


def test_string_keys():
    t = ScapegoatTree()
    for w in "pear fig kiwi lime fig date".split():
        t.insert(w)
    assert t.in_order() == ["date", "fig", "kiwi", "lime", "pear"] and t.contains("kiwi")


def test_float_keys():
    t = ScapegoatTree()
    for v in (1.5, 0.5, 2.5, 1.5):
        t.insert(v)
    assert t.in_order() == [0.5, 1.5, 2.5]


def test_minimum_maximum():
    t = ScapegoatTree()
    for v in (5, 1, 9, 3):
        t.insert(v)
    assert t.minimum() == 1 and t.maximum() == 9


def test_contains_basic():
    t = ScapegoatTree()
    for v in (5, 3, 8):
        t.insert(v)
    assert t.contains(3) and not t.contains(4)


def test_in_order_basic():
    t = ScapegoatTree()
    for v in (5, 3, 8, 1):
        t.insert(v)
    assert t.in_order() == [1, 3, 5, 8]


def test_insert_returns_bool():
    assert ScapegoatTree().insert(1) is True


def test_delete_returns_bool():
    t = ScapegoatTree(); t.insert(1)
    assert t.delete(1) is True


def test_height_basic():
    t = ScapegoatTree()
    assert t.height() == 0
    t.insert(1)
    assert t.height() == 1


def test_alpha_property():
    assert ScapegoatTree(0.75).alpha == 0.75


def test_empty():
    e = ScapegoatTree()
    assert e.minimum() is None and e.maximum() is None and not e.contains(1) and e.in_order() == []


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_alpha_too_low_raises():
    with pytest.raises(ScapegoatTreeError):
        ScapegoatTree(0.5)


def test_alpha_too_high_raises():
    with pytest.raises(ScapegoatTreeError):
        ScapegoatTree(1.0)


def test_insert_none_raises():
    with pytest.raises(ScapegoatTreeError):
        ScapegoatTree().insert(None)


def test_insert_bool_raises():
    with pytest.raises(ScapegoatTreeError):
        ScapegoatTree().insert(True)


def test_insert_unorderable_raises():
    with pytest.raises(ScapegoatTreeError):
        ScapegoatTree().insert([1, 2])


def test_mixed_type_raises():
    t = ScapegoatTree(); t.insert(5)
    with pytest.raises(ScapegoatTreeError):
        t.insert("x")


def test_contains_none_raises():
    with pytest.raises(ScapegoatTreeError):
        ScapegoatTree().contains(None)


def test_error_stores_detail():
    err = ScapegoatTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    t = ScapegoatTree()
    for v in (3, 1, 2):
        t.insert(v)
    t.reset()
    assert t.is_empty() and t.height() == 0


def test_size_len():
    t = ScapegoatTree()
    t.insert(1); t.insert(2)
    assert t.size == 2 and len(t) == 2


def test_stats_keys():
    assert set(ScapegoatTree().stats()) == {"size", "height", "alpha", "min", "max"}


def test_stats_values():
    t = ScapegoatTree()
    for v in (5, 2, 8):
        t.insert(v)
    s = t.stats()
    assert s["size"] == 3 and s["min"] == 2 and s["max"] == 8


def test_deterministic():
    def build():
        x = ScapegoatTree(2 / 3)
        for v in (5, 3, 8, 1, 4, 7, 9, 2, 6, 10, 11, 12):
            x.insert(v)
        return x.in_order()
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = ScapegoatTree(2 / 3)
    errors = []
    vals = list(range(400))

    def worker(chunk):
        try:
            for v in chunk:
                t.insert(v)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(vals[i::4],)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and t.size == 400 and t.in_order() == list(range(400))
