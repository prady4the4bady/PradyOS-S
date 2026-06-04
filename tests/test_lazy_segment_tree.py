"""Phase 163 — unit tests for LazySegmentTree (pradyos/core/lazy_segment_tree.py)."""
from __future__ import annotations

import random

import pytest

from pradyos.core.lazy_segment_tree import LazySegmentTree, LazySegmentTreeError


# ── differential vs brute array (centerpieces) ───────────────────────────────────────────

def test_interleaved_differential():
    rng = random.Random(1)
    for n in (1, 2, 5, 8, 9, 16, 17, 50, 100):
        ref = [rng.randint(-50, 50) for _ in range(n)]
        st = LazySegmentTree(ref[:])
        for _ in range(n * 4):
            op = rng.random(); l = rng.randrange(n); r = rng.randint(l, n - 1)
            if op < 0.3:
                d = rng.randint(-30, 30)
                for k in range(l, r + 1):
                    ref[k] += d
                st.range_add(l, r, d)
            elif op < 0.5:
                v = rng.randint(-50, 50)
                for k in range(l, r + 1):
                    ref[k] = v
                st.range_assign(l, r, v)
            elif op < 0.65:
                assert st.range_sum(l, r) == sum(ref[l:r + 1])
            elif op < 0.78:
                assert st.range_min(l, r) == min(ref[l:r + 1])
            elif op < 0.9:
                assert st.range_max(l, r) == max(ref[l:r + 1])
            else:
                i = rng.randrange(n)
                assert st.point_query(i) == ref[i]
        assert st.range_sum(0, n - 1) == sum(ref)
        assert st.range_min(0, n - 1) == min(ref) and st.range_max(0, n - 1) == max(ref)
        assert all(st.point_query(i) == ref[i] for i in range(n))


def test_large_differential():
    rng = random.Random(2)
    big = list(range(1000))
    st = LazySegmentTree(big[:])
    for _ in range(500):
        l = rng.randrange(1000); r = rng.randint(l, 999)
        if rng.random() < 0.5:
            d = rng.randint(-10, 10)
            for k in range(l, r + 1):
                big[k] += d
            st.range_add(l, r, d)
        else:
            v = rng.randint(-100, 100)
            for k in range(l, r + 1):
                big[k] = v
            st.range_assign(l, r, v)
    for _ in range(100):
        l = rng.randrange(1000); r = rng.randint(l, 999)
        assert st.range_sum(l, r) == sum(big[l:r + 1])
        assert st.range_min(l, r) == min(big[l:r + 1]) and st.range_max(l, r) == max(big[l:r + 1])


# ── lazy tag composition ──────────────────────────────────────────────────────────────────

def test_assign_clears_add_then_add_accumulates():
    st = LazySegmentTree([0] * 10)
    st.range_add(0, 9, 5)
    st.range_assign(2, 7, 100)
    st.range_add(0, 9, 1)
    ref = [6, 6, 101, 101, 101, 101, 101, 101, 6, 6]
    assert all(st.point_query(i) == ref[i] for i in range(10)) and st.range_sum(0, 9) == sum(ref)


def test_min_max_after_assign():
    st = LazySegmentTree([1, 2, 3, 4, 5])
    st.range_assign(1, 3, 0)
    assert st.range_min(0, 4) == 0 and st.range_max(0, 4) == 5 and st.range_sum(0, 4) == 6


def test_add_shifts_min_max():
    st = LazySegmentTree([10, 20, 30])
    st.range_add(0, 2, -5)
    assert st.range_min(0, 2) == 5 and st.range_max(0, 2) == 25 and st.range_sum(0, 2) == 45


def test_nested_overlapping():
    st = LazySegmentTree([0] * 20)
    st.range_add(0, 19, 1); st.range_add(5, 14, 10); st.range_assign(8, 11, 100); st.range_add(10, 12, 1)
    ref = [1] * 20
    for k in range(5, 15):
        ref[k] += 10
    for k in range(8, 12):
        ref[k] = 100
    for k in range(10, 13):
        ref[k] += 1
    assert all(st.point_query(i) == ref[i] for i in range(20)) and st.range_sum(0, 19) == sum(ref)


# ── basics ───────────────────────────────────────────────────────────────────────────────

def test_range_sum_basic():
    st = LazySegmentTree([1, 2, 3, 4, 5])
    assert st.range_sum(0, 4) == 15 and st.range_sum(1, 3) == 9


def test_range_min_basic():
    st = LazySegmentTree([4, 2, 6, 1, 5])
    assert st.range_min(0, 4) == 1 and st.range_min(0, 2) == 2


def test_range_max_basic():
    st = LazySegmentTree([4, 2, 6, 1, 5])
    assert st.range_max(0, 4) == 6 and st.range_max(3, 4) == 5


def test_point_query():
    st = LazySegmentTree([7, 8, 9])
    assert st.point_query(0) == 7 and st.point_query(2) == 9


def test_full_assign():
    st = LazySegmentTree(list(range(100)))
    st.range_assign(0, 99, 7)
    assert st.range_sum(0, 99) == 700 and st.range_min(0, 99) == 7 and st.range_max(0, 99) == 7


def test_single_element():
    st = LazySegmentTree([7])
    st.range_add(0, 0, 3)
    assert st.range_sum(0, 0) == 10 and st.range_min(0, 0) == 10 and st.point_query(0) == 10
    st.range_assign(0, 0, -1)
    assert st.point_query(0) == -1 and st.range_max(0, 0) == -1


def test_range_single_index():
    st = LazySegmentTree([4, 8, 15, 16, 23])
    assert st.range_sum(2, 2) == 15 and st.range_min(2, 2) == 15 and st.range_max(2, 2) == 15


def test_negative_deltas():
    st = LazySegmentTree([10] * 5)
    st.range_add(0, 4, -7)
    assert st.range_sum(0, 4) == 15 and st.range_min(0, 4) == 3


def test_floats():
    st = LazySegmentTree([1.5, 2.5, 3.0])
    st.range_add(0, 2, 0.5)
    assert abs(st.range_sum(0, 2) - 8.5) < 1e-9


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_non_numeric_value_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([1, "x"])


def test_range_add_lo_gt_hi_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([1, 2, 3]).range_add(2, 1, 5)


def test_range_out_of_range_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([1, 2, 3]).range_sum(0, 5)


def test_range_add_non_num_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([1, 2, 3]).range_add(0, 0, "x")


def test_range_assign_non_num_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([1, 2, 3]).range_assign(0, 0, "x")


def test_point_query_out_of_range_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([1, 2, 3]).point_query(9)


def test_empty_query_raises():
    with pytest.raises(LazySegmentTreeError):
        LazySegmentTree([]).range_sum(0, 0)


def test_error_stores_detail():
    err = LazySegmentTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / introspection ─────────────────────────────────────────────────────────

def test_build_replaces():
    st = LazySegmentTree([1, 2])
    st.build([5, 5, 5, 5])
    assert st.range_sum(0, 3) == 20 and len(st) == 4


def test_reset_clears():
    st = LazySegmentTree([1, 2, 3])
    st.reset()
    assert len(st) == 0


def test_size_len():
    st = LazySegmentTree([1, 2, 3, 4, 5])
    assert st.size == 5 and len(st) == 5


def test_stats_keys():
    assert set(LazySegmentTree([1, 2, 3]).stats()) == {"size", "total", "min", "max"}


def test_stats_values():
    st = LazySegmentTree([1, 2, 3])
    st.range_add(0, 2, 10)
    s = st.stats()
    assert s["total"] == 36 and s["min"] == 11 and s["max"] == 13


def test_deterministic():
    def build():
        x = LazySegmentTree([3, 1, 4, 1, 5, 9, 2, 6])
        x.range_add(2, 5, 10); x.range_assign(0, 1, 0)
        return x.range_sum(0, 7)
    assert build() == build()


def test_range_min_after_partial_add():
    st = LazySegmentTree([5, 5, 5, 5, 5])
    st.range_add(2, 4, -3)                         # [5,5,2,2,2]
    assert st.range_min(0, 4) == 2 and st.range_min(0, 1) == 5 and st.range_max(0, 4) == 5


def test_assign_then_query_subrange():
    st = LazySegmentTree(list(range(10)))
    st.range_assign(3, 6, 99)
    assert st.range_max(0, 9) == 99 and st.range_sum(3, 6) == 396 and st.point_query(5) == 99


def test_two_element():
    st = LazySegmentTree([10, 20])
    st.range_add(0, 1, 5)
    assert st.range_sum(0, 1) == 40 and st.range_min(0, 1) == 15 and st.range_max(0, 1) == 25


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_range_adds():
    import threading
    st = LazySegmentTree([0] * 100)
    errors = []

    def worker():
        try:
            for _ in range(200):
                st.range_add(0, 99, 1)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and st.range_sum(0, 99) == 100 * 2000
