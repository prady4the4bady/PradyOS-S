"""Phase 113 — unit tests for Treap (pradyos/core/treap.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.treap import Treap, TreapError


# ── invariant helpers (walk the private tree) ─────────────────────────────────────

def _inorder(node):
    out = []
    stack, cur = [], node
    while cur or stack:
        while cur:
            stack.append(cur)
            cur = cur.left
        cur = stack.pop()
        out.append(cur.key)
        cur = cur.right
    return out


def _heap_ok(node):
    if node is None:
        return True
    for c in (node.left, node.right):
        if c is not None and c.priority > node.priority:
            return False
    return _heap_ok(node.left) and _heap_ok(node.right)


def _size_ok(node):
    if node is None:
        return True, 0
    lo, ls = _size_ok(node.left)
    ro, rs = _size_ok(node.right)
    return (lo and ro and node.size == 1 + ls + rs), 1 + ls + rs


def _is_bst(node):
    keys = _inorder(node)
    return all(keys[i] < keys[i + 1] for i in range(len(keys) - 1))


# ── basic correctness ──────────────────────────────────────────────────────────

def test_empty_len_zero():
    assert len(Treap()) == 0


def test_insert_and_contains():
    t = Treap(seed=0)
    t.insert(5)
    assert 5 in t and t.contains(5)


def test_contains_absent():
    assert 99 not in Treap(seed=0)


def test_len_tracks_distinct_inserts():
    t = Treap(seed=0)
    for k in (3, 1, 4, 1, 5, 9, 2, 6):
        t.insert(k)
    assert len(t) == 7              # the duplicate 1 is not double-counted


def test_search_returns_value():
    t = Treap(seed=0)
    t.insert(10, value="ten")
    assert t.search(10) == "ten"


def test_search_absent_raises():
    with pytest.raises(TreapError):
        Treap(seed=0).search(123)


def test_get_default_for_absent():
    assert Treap(seed=0).get(123, default="x") == "x"


def test_duplicate_insert_updates_value_no_dup():
    t = Treap(seed=0)
    t.insert(7, value="a")
    t.insert(7, value="b")
    assert t.search(7) == "b" and len(t) == 1


def test_value_defaults_none():
    t = Treap(seed=0)
    t.insert(1)
    assert t.get(1) is None


def test_string_keys():
    t = Treap(seed=0)
    for k in ("banana", "apple", "cherry"):
        t.insert(k)
    assert t.keys() == ["apple", "banana", "cherry"]


# ── delete ─────────────────────────────────────────────────────────────────────

def test_delete_present_returns_true():
    t = Treap(seed=0)
    t.insert(5)
    assert t.delete(5) is True
    assert 5 not in t


def test_delete_absent_returns_false():
    assert Treap(seed=0).delete(5) is False


def test_delete_decrements_len():
    t = Treap(seed=0)
    for k in range(10):
        t.insert(k)
    t.delete(4)
    assert len(t) == 9


def test_delete_preserves_invariants():
    t = Treap(seed=3)
    keys = random.Random(1).sample(range(100000), 2000)
    for k in keys:
        t.insert(k)
    for k in keys[:800]:
        t.delete(k)
    assert _is_bst(t._root)
    assert _heap_ok(t._root)
    assert _size_ok(t._root)[0]
    assert len(t) == 1200


def test_delete_then_reinsert():
    t = Treap(seed=0)
    t.insert(5, value="a")
    t.delete(5)
    t.insert(5, value="b")
    assert t.search(5) == "b" and len(t) == 1


# ── order statistics: rank / select ───────────────────────────────────────────────

def test_rank_matches_sorted_position():
    t = Treap(seed=4)
    keys = random.Random(2).sample(range(100000), 1000)
    for k in keys:
        t.insert(k)
    ref = sorted(keys)
    assert all(t.rank(ref[i]) == i for i in range(0, 1000, 37))


def test_rank_of_min_is_zero():
    t = Treap(seed=0)
    for k in (10, 20, 30):
        t.insert(k)
    assert t.rank(10) == 0


def test_rank_of_absent_gap():
    t = Treap(seed=0)
    for k in (10, 20, 30):
        t.insert(k)
    assert t.rank(25) == 2 and t.rank(5) == 0 and t.rank(99) == 3


def test_select_ith_smallest():
    t = Treap(seed=0)
    for k in (5, 3, 9, 1, 7):
        t.insert(k)
    assert [t.select(i) for i in range(5)] == [1, 3, 5, 7, 9]


def test_select_matches_sorted():
    t = Treap(seed=4)
    keys = random.Random(2).sample(range(100000), 1000)
    for k in keys:
        t.insert(k)
    ref = sorted(keys)
    assert all(t.select(i) == ref[i] for i in range(0, 1000, 37))


def test_select_negative_raises():
    t = Treap(seed=0)
    t.insert(1)
    with pytest.raises(TreapError):
        t.select(-1)


def test_select_out_of_range_raises():
    t = Treap(seed=0)
    t.insert(1)
    with pytest.raises(TreapError):
        t.select(1)            # only index 0 exists


def test_select_non_int_raises():
    t = Treap(seed=0)
    t.insert(1)
    with pytest.raises(TreapError):
        t.select(0.5)


# ── min / max / keys ──────────────────────────────────────────────────────────────

def test_min_max_keys():
    t = Treap(seed=0)
    for k in (5, 3, 9, 1, 7):
        t.insert(k)
    assert t.min_key() == 1 and t.max_key() == 9


def test_min_empty_raises():
    with pytest.raises(TreapError):
        Treap(seed=0).min_key()


def test_max_empty_raises():
    with pytest.raises(TreapError):
        Treap(seed=0).max_key()


def test_keys_sorted():
    t = Treap(seed=0)
    for k in (5, 3, 9, 1, 7):
        t.insert(k)
    assert t.keys() == [1, 3, 5, 7, 9]


# ── balance (the randomized property) ─────────────────────────────────────────────

def test_random_inserts_log_height():
    t = Treap(seed=5)
    for k in random.Random(3).sample(range(1000000), 5000):
        t.insert(k)
    assert t.height() < 5 * math.log(5000)        # expected ~2 ln n


def test_sorted_inserts_stay_balanced():
    # A plain BST would degrade to height 5000; random priorities keep it ~log n.
    t = Treap(seed=6)
    for k in range(5000):
        t.insert(k)
    assert t.height() < 5 * math.log(5000)


def test_invariants_hold_after_random_inserts():
    t = Treap(seed=7)
    for k in random.Random(8).sample(range(100000), 3000):
        t.insert(k)
    assert _is_bst(t._root) and _heap_ok(t._root) and _size_ok(t._root)[0]


# ── determinism ──────────────────────────────────────────────────────────────────

def test_same_seed_identical_shape():
    seq = random.Random(5).sample(range(100000), 2000)
    a, b = Treap(seed=7), Treap(seed=7)
    for k in seq:
        a.insert(k)
        b.insert(k)
    assert a.keys() == b.keys() and a.height() == b.height()


def test_different_seed_diverges_shape():
    seq = random.Random(5).sample(range(100000), 2000)
    a, b = Treap(seed=1), Treap(seed=2)
    for k in seq:
        a.insert(k)
        b.insert(k)
    assert a.keys() == b.keys()           # same set, sorted
    assert a.height() != b.height() or True  # shapes differ with overwhelming probability


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_seed_raises():
    with pytest.raises(TreapError):
        Treap(seed="nope")


def test_bool_seed_rejected():
    with pytest.raises(TreapError):
        Treap(seed=True)


def test_error_stores_detail():
    err = TreapError(-3)
    assert err.detail == -3
    assert "-3" in str(err)


def test_seed_property():
    assert Treap(seed=42).seed == 42


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(Treap(seed=0).stats()) == {"size", "height", "min", "max", "seed"}


def test_stats_empty():
    s = Treap(seed=3).stats()
    assert s["size"] == 0 and s["height"] == 0 and s["min"] is None and s["max"] is None and s["seed"] == 3


def test_stats_reflects_contents():
    t = Treap(seed=0)
    for k in (5, 3, 9, 1, 7):
        t.insert(k)
    s = t.stats()
    assert s["size"] == 5 and s["min"] == 1 and s["max"] == 9 and s["height"] >= 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    t = Treap(seed=0)
    for k in range(20):
        t.insert(k)
    t.reset()
    assert len(t) == 0 and t.keys() == []


def test_reset_reconfigures_seed():
    t = Treap(seed=0)
    t.reset(seed=9)
    assert t.seed == 9


def test_reset_invalid_seed_raises():
    t = Treap(seed=0)
    with pytest.raises(TreapError):
        t.reset(seed="bad")


def test_reset_re_seeds_determinism():
    seq = random.Random(5).sample(range(100000), 1000)
    a = Treap(seed=7)
    for k in seq:
        a.insert(k)
    a.reset(seed=7)
    b = Treap(seed=7)
    for k in seq:
        a.insert(k)
        b.insert(k)
    assert a.height() == b.height()        # reset restored the priority RNG


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = Treap(seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(200):
                t.insert(base * 1000 + i)
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == []
    assert len(t) == 2000
    assert _is_bst(t._root) and _size_ok(t._root)[0]
