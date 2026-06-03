"""Phase 137 — unit tests for IntervalTree / CLRS augmented BST (pradyos/core/interval_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.interval_tree import IntervalTree, IntervalTreeError


def overlaps(a, b):
    return a[0] <= b[1] and b[0] <= a[1]


def max_invariant_ok(tree):
    """Iterative post-order check that every node.max == max high in its subtree."""
    root = tree._root
    if root is None:
        return True
    submax = {}
    stack = [(root, False)]
    while stack:
        node, processed = stack.pop()
        if processed:
            m = node.high
            if node.left is not None:
                m = max(m, submax[id(node.left)])
            if node.right is not None:
                m = max(m, submax[id(node.right)])
            submax[id(node)] = m
            if node.max != m:
                return False
        else:
            stack.append((node, True))
            if node.left is not None:
                stack.append((node.left, False))
            if node.right is not None:
                stack.append((node.right, False))
    return True


def filled(intervals):
    t = IntervalTree()
    for lo, hi in intervals:
        t.insert(lo, hi)
    return t


# ── differential vs brute force (centerpiece) ────────────────────────────────────────────

def test_insert_remove_differential():
    rng = random.Random(11)
    it = IntervalTree()
    ref = []
    inv_ok = True
    for step in range(6000):
        if ref and rng.random() < 0.35:
            iv = rng.choice(ref)
            ref.remove(iv)
            it.remove(iv[0], iv[1])
        else:
            lo = rng.randint(0, 200)
            hi = lo + rng.randint(0, 50)
            ref.append((lo, hi))
            it.insert(lo, hi)
        if step % 600 == 0 and not max_invariant_ok(it):
            inv_ok = False
    assert len(it) == len(ref) and inv_ok


def test_overlap_matches_brute_force():
    rng = random.Random(3)
    ref = [(rng.randint(0, 200), 0) for _ in range(1500)]
    ref = [(lo, lo + rng.randint(0, 40)) for lo, _ in ref]
    it = filled(ref)
    for _ in range(200):
        qlo = rng.randint(-10, 210)
        qhi = qlo + rng.randint(0, 40)
        assert it.overlap(qlo, qhi) == sorted(iv for iv in ref if overlaps(iv, (qlo, qhi)))


def test_stab_matches_brute_force():
    rng = random.Random(4)
    ref = [(lo, lo + rng.randint(0, 30)) for lo in (rng.randint(0, 200) for _ in range(1000))]
    it = filled(ref)
    for _ in range(200):
        p = rng.randint(-10, 210)
        assert it.stab(p) == sorted(iv for iv in ref if iv[0] <= p <= iv[1])


def test_overlap_any_valid_or_none():
    rng = random.Random(5)
    ref = [(lo, lo + rng.randint(0, 20)) for lo in (rng.randint(0, 100) for _ in range(500))]
    it = filled(ref)
    for _ in range(200):
        qlo = rng.randint(-10, 110)
        qhi = qlo + rng.randint(0, 20)
        a = it.overlap_any(qlo, qhi)
        exp_any = any(overlaps(iv, (qlo, qhi)) for iv in ref)
        if exp_any:
            assert a is not None and overlaps(a, (qlo, qhi))
        else:
            assert a is None


# ── adversarial (no recursion limit — iterative ops) ─────────────────────────────────────

def test_adversarial_sorted_insert():
    it = IntervalTree()
    for i in range(15000):
        it.insert(i, i + 5)
    assert len(it) == 15000 and max_invariant_ok(it)
    exp = sorted((i, i + 5) for i in range(15000) if overlaps((i, i + 5), (100, 103)))
    assert it.overlap(100, 103) == exp


# ── semantics / edges ────────────────────────────────────────────────────────────────────

def test_overlap_inclusive_endpoints():
    it = filled([(1, 5), (5, 10)])
    assert it.overlap(5, 5) == [(1, 5), (5, 10)]          # both touch 5


def test_overlap_no_match_empty():
    assert filled([(1, 3), (10, 12)]).overlap(5, 7) == []


def test_stab_point():
    it = filled([(1, 5), (2, 8), (10, 12)])
    assert it.stab(3) == [(1, 5), (2, 8)] and it.stab(11) == [(10, 12)]


def test_stab_no_match():
    assert filled([(1, 5), (10, 12)]).stab(7) == []


def test_overlap_any_specific():
    it = filled([(1, 5), (20, 25)])
    assert it.overlap_any(3, 4) == (1, 5) and it.overlap_any(100, 200) is None


def test_single_point_intervals():
    it = filled([(5, 5), (3, 3), (5, 5)])
    assert it.stab(5) == [(5, 5), (5, 5)] and it.stab(4) == []


def test_negative_endpoints():
    it = filled([(-10, -5), (-3, 2), (0, 4)])
    assert it.stab(-7) == [(-10, -5)] and it.overlap(-4, -2) == [(-3, 2)]


def test_remove_then_query_excludes():
    it = filled([(1, 5), (2, 8), (10, 12)])
    it.remove(2, 8)
    assert it.overlap(3, 4) == [(1, 5)] and not it.contains(2, 8)


def test_float_intervals():
    it = filled([(1.5, 2.5), (0.0, 1.0)])
    assert it.stab(2.0) == [(1.5, 2.5)]


def test_empty_overlap_and_stab():
    e = IntervalTree()
    assert e.overlap(0, 10) == [] and e.stab(5) == [] and e.overlap_any(0, 10) is None


# ── contains / remove ──────────────────────────────────────────────────────────────────────

def test_contains():
    it = filled([(1, 5), (2, 8), (10, 12)])
    assert it.contains(2, 8) and not it.contains(3, 3)


def test_duplicates_counted():
    assert len(filled([(1, 5), (1, 5), (1, 5)])) == 3


def test_remove_one_duplicate():
    it = filled([(1, 5), (1, 5)])
    assert it.remove(1, 5) is True and it.contains(1, 5) and len(it) == 1


def test_remove_absent():
    assert filled([(1, 5)]).remove(2, 3) is False


def test_remove_root():
    it = filled([(5, 9)])
    assert it.remove(5, 9) is True and len(it) == 0 and it.max_endpoint is None


def test_remove_two_children_preserves_set():
    ivs = [(5, 10), (2, 6), (8, 12), (1, 3), (3, 7), (9, 11), (7, 9)]
    it = filled(ivs)
    it.remove(5, 10)                                       # interior node with two children
    remaining = sorted(iv for iv in ivs if iv != (5, 10))
    assert it.overlap(-100, 100) == remaining and max_invariant_ok(it)


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_low_gt_high_raises():
    with pytest.raises(IntervalTreeError):
        IntervalTree().insert(5, 2)


def test_bool_endpoint_raises():
    with pytest.raises(IntervalTreeError):
        IntervalTree().insert(True, 3)


def test_non_numeric_endpoint_raises():
    with pytest.raises(IntervalTreeError):
        IntervalTree().insert("a", 3)


def test_stab_non_numeric_raises():
    with pytest.raises(IntervalTreeError):
        IntervalTree().stab("x")


def test_error_stores_detail():
    err = IntervalTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ─────────────────────────────────────────────────────

def test_reset_clears():
    it = filled([(1, 5), (2, 8)])
    it.reset()
    assert len(it) == 0 and it.max_endpoint is None


def test_max_endpoint_property():
    assert filled([(1, 5), (2, 20), (3, 8)]).max_endpoint == 20


def test_height_in_range():
    it = filled([(lo, lo + 2) for lo in range(200)])
    assert 1 <= it.height() <= len(it)


def test_stats_keys():
    assert set(IntervalTree().stats()) == {"size", "max_endpoint", "height"}


def test_len_size():
    it = filled([(1, 2), (3, 4), (5, 6)])
    assert len(it) == 3 and it.size == 3


def test_deterministic():
    ivs = [(5, 10), (1, 3), (7, 8), (2, 6), (9, 12)]
    assert filled(ivs).overlap(4, 7) == filled(ivs).overlap(4, 7)


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    it = IntervalTree()
    errors = []

    def worker(base):
        try:
            for i in range(500):
                it.insert(base * 1000 + i, base * 1000 + i + 10)
        except Exception as exc:                           # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(it) == 5000 and max_invariant_ok(it)
