"""Phase 156 — unit tests for BTree (pradyos/core/b_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.b_tree import BTree, BTreeError


def _invariant_ok(bt):
    t = bt._t; root = bt._root
    leaf_depths = set(); ok = [True]

    def rec(node, depth, lo, hi):
        k = len(node.keys)
        if node is root:
            if bt._size > 0 and not (1 <= k <= 2 * t - 1):
                ok[0] = False
        elif not (t - 1 <= k <= 2 * t - 1):
            ok[0] = False
        for idx in range(k):
            if idx > 0 and not (node.keys[idx - 1] < node.keys[idx]):
                ok[0] = False
            if lo is not None and not (node.keys[idx] > lo):
                ok[0] = False
            if hi is not None and not (node.keys[idx] < hi):
                ok[0] = False
        if node.leaf:
            leaf_depths.add(depth)
            if node.children:
                ok[0] = False
        else:
            if len(node.children) != k + 1:
                ok[0] = False
            bounds = [lo] + list(node.keys) + [hi]
            for ci in range(len(node.children)):
                rec(node.children[ci], depth + 1, bounds[ci], bounds[ci + 1])

    rec(root, 0, None, None)
    return ok[0] and len(leaf_depths) <= 1


# ── differential vs sorted set + invariants (centerpieces) ───────────────────────────────

def test_inorder_and_invariant_differential():
    rng = random.Random(1)
    for t in (2, 3, 5):
        for _ in range(20):
            bt = BTree(min_degree=t); s = set()
            for _ in range(300):
                x = rng.randint(0, 400)
                if rng.random() < 0.65:
                    assert bt.insert(x) == (x not in s); s.add(x)
                else:
                    assert bt.delete(x) == (x in s); s.discard(x)
                assert _invariant_ok(bt)
            assert bt.in_order() == sorted(s)
            assert bt.minimum() == (min(s) if s else None)
            assert bt.maximum() == (max(s) if s else None)


def test_contains_differential():
    rng = random.Random(2)
    bt = BTree(min_degree=3); s = set()
    for _ in range(500):
        x = rng.randint(0, 300); bt.insert(x); s.add(x)
    assert all(bt.contains(k) == (k in s) for k in range(0, 300))


# ── balance under adversarial order ──────────────────────────────────────────────────────

def test_sorted_insert_invariant():
    bt = BTree(min_degree=3)
    for i in range(5000):
        bt.insert(i)
    assert bt.in_order() == list(range(5000)) and _invariant_ok(bt)


def test_sorted_delete_invariant():
    bt = BTree(min_degree=3)
    for i in range(5000):
        bt.insert(i)
    for i in range(2500):
        bt.delete(i)
    assert bt.in_order() == list(range(2500, 5000)) and _invariant_ok(bt) and bt.size == 2500


def test_reverse_insert_invariant():
    bt = BTree(min_degree=4)
    for i in range(3000, 0, -1):
        bt.insert(i)
    assert bt.in_order() == list(range(1, 3001)) and _invariant_ok(bt)


def test_234_tree_churn():
    rng = random.Random(3)
    bt = BTree(min_degree=2); s = set()
    for _ in range(2000):
        x = rng.randint(0, 100)
        if rng.random() < 0.5:
            bt.insert(x); s.add(x)
        else:
            bt.delete(x); s.discard(x)
        assert _invariant_ok(bt)
    assert bt.in_order() == sorted(s)


def test_large_shuffled_t5():
    rng = random.Random(4)
    bt = BTree(min_degree=5); big = list(range(4000)); rng.shuffle(big)
    for v in big:
        bt.insert(v)
    assert bt.in_order() == list(range(4000)) and _invariant_ok(bt)


def test_height_bounded():
    bt = BTree(min_degree=3)
    for i in range(10000):
        bt.insert(i)
    assert bt.height() <= 20 and _invariant_ok(bt)


def test_delete_all_empty():
    rng = random.Random(5)
    bt = BTree(min_degree=3); keys = list(range(500)); rng.shuffle(keys)
    for k in keys:
        bt.insert(k)
    rng.shuffle(keys)
    for k in keys:
        bt.delete(k)
    assert bt.size == 0 and bt._root.leaf and bt.in_order() == [] and bt.height() == 0


# ── semantics ──────────────────────────────────────────────────────────────────────────────

def test_dup_ignored():
    bt = BTree()
    assert bt.insert(5) is True and bt.insert(5) is False and bt.size == 1


def test_delete_absent():
    assert BTree().delete(99) is False


def test_delete_internal_node():
    bt = BTree(min_degree=2)
    for v in range(20):
        bt.insert(v)
    # delete a spread of keys (forces internal-node deletes + rebalancing)
    for v in (10, 5, 15, 0, 19, 7):
        assert bt.delete(v) is True
    remaining = [v for v in range(20) if v not in {10, 5, 15, 0, 19, 7}]
    assert bt.in_order() == remaining and _invariant_ok(bt)


def test_string_keys():
    bt = BTree(min_degree=2)
    for w in "pear fig kiwi lime fig date".split():
        bt.insert(w)
    assert bt.in_order() == ["date", "fig", "kiwi", "lime", "pear"] and bt.contains("kiwi")


def test_float_keys():
    bt = BTree()
    for v in (1.5, 0.5, 2.5, 1.5):
        bt.insert(v)
    assert bt.in_order() == [0.5, 1.5, 2.5]


def test_minimum_maximum():
    bt = BTree()
    for v in (5, 1, 9, 3):
        bt.insert(v)
    assert bt.minimum() == 1 and bt.maximum() == 9


def test_contains_basic():
    bt = BTree()
    for v in (5, 3, 8):
        bt.insert(v)
    assert bt.contains(3) and not bt.contains(4)


def test_in_order_basic():
    bt = BTree()
    for v in (5, 3, 8, 1):
        bt.insert(v)
    assert bt.in_order() == [1, 3, 5, 8]


def test_insert_returns_bool():
    assert BTree().insert(1) is True


def test_delete_returns_bool():
    bt = BTree(); bt.insert(1)
    assert bt.delete(1) is True


def test_height_basic():
    bt = BTree()
    assert bt.height() == 0
    bt.insert(1)
    assert bt.height() == 1


def test_min_degree_property():
    assert BTree(min_degree=7).min_degree == 7


def test_empty():
    e = BTree()
    assert e.minimum() is None and e.maximum() is None and not e.contains(1) and e.in_order() == []


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_min_degree_invalid_raises():
    with pytest.raises(BTreeError):
        BTree(min_degree=1)


def test_insert_none_raises():
    with pytest.raises(BTreeError):
        BTree().insert(None)


def test_insert_bool_raises():
    with pytest.raises(BTreeError):
        BTree().insert(True)


def test_insert_unorderable_raises():
    with pytest.raises(BTreeError):
        BTree().insert([1, 2])


def test_mixed_type_raises():
    bt = BTree(); bt.insert(5)
    with pytest.raises(BTreeError):
        bt.insert("x")


def test_contains_none_raises():
    with pytest.raises(BTreeError):
        BTree().contains(None)


def test_error_stores_detail():
    err = BTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    bt = BTree()
    for v in (3, 1, 2):
        bt.insert(v)
    bt.reset()
    assert bt.is_empty() and bt.height() == 0


def test_size_len():
    bt = BTree()
    bt.insert(1); bt.insert(2)
    assert bt.size == 2 and len(bt) == 2


def test_stats_keys():
    assert set(BTree().stats()) == {"size", "height", "min_degree", "min", "max"}


def test_stats_values():
    bt = BTree()
    for v in (5, 2, 8):
        bt.insert(v)
    s = bt.stats()
    assert s["size"] == 3 and s["min"] == 2 and s["max"] == 8 and s["min_degree"] == 3


def test_deterministic():
    def build():
        x = BTree(min_degree=3)
        for v in (5, 3, 8, 1, 4, 7, 9, 2, 6, 10, 11, 12):
            x.insert(v)
        return x.in_order() + [x.height()]
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    bt = BTree(min_degree=3)
    errors = []
    vals = list(range(400))

    def worker(chunk):
        try:
            for v in chunk:
                bt.insert(v)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(vals[i::4],)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and bt.size == 400 and bt.in_order() == list(range(400))
    assert _invariant_ok(bt)
