"""Phase 145 — unit tests for CartesianTree / Vuillemin (pradyos/core/cartesian_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.cartesian_tree import CartesianTree, CartesianTreeError


def invariants_ok(ct, vals):
    s = ct.structure()
    root, L, R, P, n = s["root"], s["left"], s["right"], s["parent"], len(vals)
    if n == 0:
        return root == -1
    if [i for i in range(n) if P[i] == -1] != [root]:
        return False
    for i in range(n):
        if L[i] != -1 and not (L[i] < i and vals[L[i]] >= vals[i] and P[L[i]] == i):
            return False
        if R[i] != -1 and not (R[i] > i and vals[R[i]] >= vals[i] and P[R[i]] == i):
            return False
    return True


# ── differential vs brute (centerpieces) ─────────────────────────────────────────────────

def test_inorder_is_identity():
    rng = random.Random(1)
    for _ in range(150):
        n = rng.randint(1, 40)
        vals = [rng.randint(-100, 100) for _ in range(n)]
        assert CartesianTree(vals).inorder() == list(range(n))


def test_invariants():
    rng = random.Random(2)
    for _ in range(150):
        n = rng.randint(1, 40)
        vals = [rng.randint(-100, 100) for _ in range(n)]
        assert invariants_ok(CartesianTree(vals), vals)


def test_range_min_all_ranges():
    rng = random.Random(3)
    for _ in range(120):
        n = rng.randint(1, 40)
        vals = [rng.randint(-100, 100) for _ in range(n)]
        ct = CartesianTree(vals)
        for l in range(n):
            for r in range(l, n):
                assert ct.range_min(l, r) == min(vals[l:r + 1])


def test_range_argmin_all_ranges():
    rng = random.Random(4)
    for _ in range(120):
        n = rng.randint(1, 40)
        vals = [rng.randint(-100, 100) for _ in range(n)]
        ct = CartesianTree(vals)
        for l in range(n):
            for r in range(l, n):
                am = ct.range_argmin(l, r)
                assert l <= am <= r and vals[am] == min(vals[l:r + 1])


# ── degenerate (no recursion limit) ─────────────────────────────────────────────────────────

def test_degenerate_ascending():
    ct = CartesianTree(list(range(5000)))
    assert ct.root_index == 0 and ct.range_min(100, 200) == 100 and len(ct.inorder()) == 5000


def test_degenerate_descending():
    vals = list(range(5000, 0, -1))
    ct = CartesianTree(vals)
    assert ct.range_min(100, 200) == min(vals[100:201])


# ── specific / semantics ──────────────────────────────────────────────────────────────────

def test_specific_sequence():
    vals = [5, 3, 8, 1, 9, 2]
    ct = CartesianTree(vals)
    assert ct.root_index == 3 and ct.range_min(0, 2) == 3 and ct.range_min(4, 5) == 2
    assert ct.range_min(0, 5) == 1


def test_ties_leftmost():
    ct = CartesianTree([3, 1, 1, 2, 1])
    assert ct.range_min(0, 4) == 1 and ct.range_argmin(0, 4) == 1


def test_root_is_global_argmin():
    vals = [5, 3, 8, 1, 9, 2]
    assert CartesianTree(vals).root_index == vals.index(min(vals))


def test_single_element():
    ct = CartesianTree([42])
    assert ct.range_min(0, 0) == 42 and ct.inorder() == [0] and ct.root_index == 0


def test_range_min_subrange():
    ct = CartesianTree([4, 2, 6, 1, 5])
    assert ct.range_min(0, 2) == 2 and ct.range_min(2, 4) == 1


def test_float_values():
    assert CartesianTree([1.5, 0.3, 2.7]).range_min(0, 2) == 0.3


def test_negative_values():
    assert CartesianTree([-1, -5, -3]).range_min(0, 2) == -5


def test_two_elements():
    ct = CartesianTree([7, 3])
    assert ct.root_index == 1 and ct.range_min(0, 1) == 3 and ct.range_min(0, 0) == 7


def test_range_min_each_single_index():
    vals = [4, 9, 1, 6]
    ct = CartesianTree(vals)
    assert all(ct.range_min(i, i) == vals[i] and ct.range_argmin(i, i) == i for i in range(4))


# ── empty / validation ────────────────────────────────────────────────────────────────────

def test_empty():
    e = CartesianTree([])
    assert len(e) == 0 and e.root_index == -1 and e.inorder() == []


def test_empty_range_min_raises():
    with pytest.raises(CartesianTreeError):
        CartesianTree([]).range_min(0, 0)


def test_non_numeric_raises():
    with pytest.raises(CartesianTreeError):
        CartesianTree([1, "x"])


def test_bool_raises():
    with pytest.raises(CartesianTreeError):
        CartesianTree([1, True])


def test_range_min_lo_gt_hi_raises():
    with pytest.raises(CartesianTreeError):
        CartesianTree([1, 2, 3]).range_min(2, 1)


def test_range_min_out_of_range_raises():
    with pytest.raises(CartesianTreeError):
        CartesianTree([1, 2, 3]).range_min(0, 3)


def test_range_min_non_int_raises():
    with pytest.raises(CartesianTreeError):
        CartesianTree([1, 2, 3]).range_min(0.5, 2)


def test_error_stores_detail():
    err = CartesianTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / build / reset / determinism ──────────────────────────────────────────────

def test_build_replaces():
    ct = CartesianTree([1, 2])
    ct.build([5, 4, 6])
    assert ct.range_min(0, 2) == 4 and len(ct) == 3


def test_reset_clears():
    ct = CartesianTree([1, 2, 3])
    ct.reset()
    assert len(ct) == 0 and ct.root_index == -1


def test_size_len():
    ct = CartesianTree([1, 2, 3, 4, 5])
    assert len(ct) == 5 and ct.size == 5


def test_root_index_property():
    assert CartesianTree([3, 1, 2]).root_index == 1


def test_height_in_range():
    ct = CartesianTree([random.Random(9).randint(0, 100) for _ in range(200)])
    assert 1 <= ct.height() <= len(ct)


def test_stats_keys():
    assert set(CartesianTree([1, 2]).stats()) == {"size", "height", "root_index"}


def test_structure_keys():
    assert set(CartesianTree([1, 2]).structure()) == {"root", "parent", "left", "right"}


def test_sequence():
    assert CartesianTree([3, 1, 2]).sequence() == [3, 1, 2]


def test_deterministic():
    assert CartesianTree([3, 1, 4, 1, 5]).structure() == CartesianTree([3, 1, 4, 1, 5]).structure()


# ── concurrency (read-only queries on a static tree) ──────────────────────────────────────────

def test_concurrent_queries():
    vals = [random.Random(5).randint(-1000, 1000) for _ in range(2000)]
    ct = CartesianTree(vals)
    errors = []
    results = []

    def worker():
        try:
            ok = all(ct.range_min(l, l + 50) == min(vals[l:l + 51]) for l in range(0, 1900, 100))
            results.append(ok)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
