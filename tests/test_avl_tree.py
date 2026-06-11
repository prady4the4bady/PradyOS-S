"""Phase 155 — unit tests for AVLTree (pradyos/core/avl_tree.py)."""
from __future__ import annotations

import bisect
import math
import random
import threading

import pytest

from pradyos.core.avl_tree import AVLTree, AVLTreeError


def _invariant_ok(t):
    root = t._root
    if root is None:
        return True
    order = []; stack = [root]
    while stack:
        nd = stack.pop(); order.append(nd)
        if nd.left:
            stack.append(nd.left)
        if nd.right:
            stack.append(nd.right)
    H = {None: 0}
    for nd in reversed(order):
        lh = H.get(nd.left, 0); rh = H.get(nd.right, 0)
        H[nd] = 1 + max(lh, rh)
        if abs(lh - rh) > 1 or nd.height != 1 + max(lh, rh):
            return False
    return True


def _succ(s, x):
    i = bisect.bisect_right(s, x)
    return s[i] if i < len(s) else None


def _pred(s, x):
    i = bisect.bisect_left(s, x)
    return s[i - 1] if i > 0 else None


# ── differential vs sorted set (centerpieces) ────────────────────────────────────────────

def test_inorder_and_invariant_differential():
    rng = random.Random(1)
    for _ in range(40):
        t = AVLTree(); s = set()
        for _ in range(300):
            x = rng.randint(0, 500)
            if rng.random() < 0.65:
                assert t.insert(x) == (x not in s); s.add(x)
            else:
                assert t.delete(x) == (x in s); s.discard(x)
        srt = sorted(s)
        assert t.in_order() == srt
        assert _invariant_ok(t)
        if s:
            assert t.height() <= 1.4404 * math.log2(len(s) + 2)
        assert t.minimum() == (srt[0] if srt else None)
        assert t.maximum() == (srt[-1] if srt else None)


def test_successor_predecessor_differential():
    rng = random.Random(2)
    t = AVLTree()
    for _ in range(400):
        t.insert(rng.randint(0, 1000))
    srt = t.in_order()
    for q in range(0, 1000, 7):
        assert t.successor(q) == _succ(srt, q)
        assert t.predecessor(q) == _pred(srt, q)


def test_contains_differential():
    rng = random.Random(3)
    t = AVLTree(); s = set()
    for _ in range(500):
        x = rng.randint(0, 300); t.insert(x); s.add(x)
    assert all(t.contains(k) == (k in s) for k in range(0, 300))


# ── balance under adversarial insertion order ────────────────────────────────────────────

def test_sorted_insert_balanced():
    t = AVLTree()
    for i in range(5000):
        t.insert(i)
    assert _invariant_ok(t) and t.height() <= 1.4404 * math.log2(5002)
    assert t.in_order() == list(range(5000))


def test_sorted_delete_balanced():
    t = AVLTree()
    for i in range(5000):
        t.insert(i)
    for i in range(2500):
        t.delete(i)
    assert _invariant_ok(t) and t.in_order() == list(range(2500, 5000)) and t.size == 2500


def test_reverse_insert_balanced():
    t = AVLTree()
    for i in range(5000, 0, -1):
        t.insert(i)
    assert _invariant_ok(t) and t.minimum() == 1 and t.maximum() == 5000


def test_large_shuffled_balanced():
    rng = random.Random(4)
    t = AVLTree(); big = list(range(3000)); rng.shuffle(big)
    for v in big:
        t.insert(v)
    assert t.in_order() == list(range(3000)) and _invariant_ok(t)


# ── semantics ──────────────────────────────────────────────────────────────────────────────

def test_duplicates_ignored():
    t = AVLTree()
    assert t.insert(5) is True and t.insert(5) is False and t.size == 1


def test_delete_absent_false():
    assert AVLTree().delete(99) is False


def test_delete_node_types():
    t = AVLTree()
    for v in (50, 30, 70, 20, 40, 60, 80):
        t.insert(v)
    assert t.delete(20) is True                  # leaf
    assert t.delete(30) is True                  # one child (40)
    assert t.delete(50) is True                  # two children (root)
    assert t.in_order() == [40, 60, 70, 80] and _invariant_ok(t)


def test_string_keys():
    t = AVLTree()
    for w in "banana apple cherry date apple".split():
        t.insert(w)
    assert t.in_order() == ["apple", "banana", "cherry", "date"]
    assert t.contains("cherry") and t.successor("apple") == "banana"


def test_float_keys():
    t = AVLTree()
    for v in (1.5, 0.5, 2.5, 1.5):
        t.insert(v)
    assert t.in_order() == [0.5, 1.5, 2.5] and t.predecessor(2.0) == 1.5


def test_successor_boundaries():
    t = AVLTree()
    for v in (10, 20, 30):
        t.insert(v)
    assert t.successor(5) == 10 and t.successor(30) is None and t.successor(15) == 20


def test_predecessor_boundaries():
    t = AVLTree()
    for v in (10, 20, 30):
        t.insert(v)
    assert t.predecessor(30) == 20 and t.predecessor(10) is None and t.predecessor(25) == 20


def test_contains_basic():
    t = AVLTree()
    for v in (5, 3, 8):
        t.insert(v)
    assert t.contains(3) and not t.contains(4)


def test_minimum_maximum():
    t = AVLTree()
    for v in (5, 1, 9, 3):
        t.insert(v)
    assert t.minimum() == 1 and t.maximum() == 9


def test_insert_returns_bool():
    t = AVLTree()
    assert t.insert(1) is True


def test_height_basic():
    t = AVLTree()
    assert t.height() == 0
    t.insert(1)
    assert t.height() == 1


def test_empty():
    e = AVLTree()
    assert e.minimum() is None and e.maximum() is None and e.successor(5) is None
    assert e.height() == 0 and not e.contains(1) and e.in_order() == []


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_insert_none_raises():
    with pytest.raises(AVLTreeError):
        AVLTree().insert(None)


def test_insert_bool_raises():
    with pytest.raises(AVLTreeError):
        AVLTree().insert(True)


def test_insert_unorderable_raises():
    with pytest.raises(AVLTreeError):
        AVLTree().insert([1, 2])


def test_mixed_type_raises():
    t = AVLTree(); t.insert(5)
    with pytest.raises(AVLTreeError):
        t.insert("x")                            # int vs str → not comparable


def test_contains_none_raises():
    with pytest.raises(AVLTreeError):
        AVLTree().contains(None)


def test_successor_none_raises():
    with pytest.raises(AVLTreeError):
        AVLTree().successor(None)


def test_error_stores_detail():
    err = AVLTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    t = AVLTree()
    for v in (3, 1, 2):
        t.insert(v)
    t.reset()
    assert t.is_empty() and t.height() == 0


def test_size_len():
    t = AVLTree()
    t.insert(1); t.insert(2)
    assert t.size == 2 and len(t) == 2


def test_stats_keys():
    assert set(AVLTree().stats()) == {"size", "height", "min", "max"}


def test_stats_values():
    t = AVLTree()
    for v in (5, 2, 8):
        t.insert(v)
    s = t.stats()
    assert s["size"] == 3 and s["min"] == 2 and s["max"] == 8


def test_deterministic():
    def build():
        x = AVLTree()
        for v in (5, 3, 8, 1, 4, 7, 9, 2, 6):
            x.insert(v)
        return x.in_order() + [x.height()]
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = AVLTree()
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
    assert _invariant_ok(t)
