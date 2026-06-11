"""Phase 166 — unit tests for SparseSegmentTree (pradyos/core/sparse_segment_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.sparse_segment_tree import SparseSegmentTree, SparseSegmentTreeError


def _brute_sum(d, lo, hi):
    return sum(v for k, v in d.items() if lo <= k <= hi)


# ── differential vs brute dict over a huge universe (centerpieces) ────────────────────────

def test_huge_universe_differential():
    rng = random.Random(1)
    U = 10 ** 18
    for _ in range(30):
        st = SparseSegmentTree(U); d = {}
        idxs = [rng.randrange(U) for _ in range(60)]
        for _ in range(300):
            op = rng.random(); i = rng.choice(idxs)
            if op < 0.4:
                x = rng.randint(-50, 50); st.update(i, x); d[i] = d.get(i, 0) + x
            elif op < 0.55:
                v = rng.randint(-100, 100); st.point_assign(i, v); d[i] = v
            elif op < 0.8:
                a = rng.choice(idxs); b = rng.choice(idxs); lo, hi = min(a, b), max(a, b)
                assert st.range_sum(lo, hi) == _brute_sum(d, lo, hi)
            else:
                assert st.point_query(i) == d.get(i, 0)
        assert st.range_sum(0, U - 1) == sum(d.values())
        assert all(st.point_query(i) == d.get(i, 0) for i in idxs)


def test_sparse_node_count():
    rng = random.Random(2)
    st = SparseSegmentTree(10 ** 18)
    for _ in range(1000):
        st.update(rng.randrange(10 ** 18), 1)
    assert st.num_nodes <= 1000 * 62 and st.total() == 1000


# ── basics ───────────────────────────────────────────────────────────────────────────────

def test_point_add_range():
    st = SparseSegmentTree(1000)
    st.update(5, 10); st.update(100, 20); st.update(999, 30)
    assert st.range_sum(0, 999) == 60 and st.range_sum(0, 99) == 10 and st.range_sum(100, 999) == 50


def test_point_query():
    st = SparseSegmentTree(1000)
    st.update(5, 10); st.update(999, 30)
    assert st.point_query(5) == 10 and st.point_query(50) == 0 and st.point_query(999) == 30


def test_accumulate():
    st = SparseSegmentTree(100)
    st.update(42, 5); st.update(42, 3); st.update(42, -2)
    assert st.point_query(42) == 6 and st.range_sum(42, 42) == 6


def test_point_assign():
    st = SparseSegmentTree(100)
    st.update(7, 100); st.point_assign(7, 5)
    assert st.point_query(7) == 5 and st.range_sum(0, 99) == 5
    st.point_assign(7, -3)
    assert st.point_query(7) == -3


def test_boundaries():
    st = SparseSegmentTree(2 ** 40)
    st.update(0, 1); st.update(2 ** 40 - 1, 2)
    assert st.range_sum(0, 2 ** 40 - 1) == 3 and st.point_query(0) == 1 and st.point_query(2 ** 40 - 1) == 2


def test_empty():
    st = SparseSegmentTree(100)
    assert st.range_sum(0, 99) == 0 and st.point_query(5) == 0 and st.is_empty()


def test_single_index_range():
    st = SparseSegmentTree(100)
    st.update(5, 7)
    assert st.range_sum(5, 5) == 7 and st.range_sum(6, 6) == 0


def test_floats_and_negatives():
    st = SparseSegmentTree(100)
    st.update(1, 1.5); st.update(2, -0.5)
    assert abs(st.range_sum(0, 99) - 1.0) < 1e-9


def test_range_sum_full():
    st = SparseSegmentTree(50)
    for i in range(50):
        st.update(i, i)
    assert st.range_sum(0, 49) == sum(range(50))


def test_total():
    st = SparseSegmentTree(100)
    st.update(1, 5); st.update(2, 10)
    assert st.total() == 15


def test_large_assign():
    st = SparseSegmentTree(10 ** 12)
    st.point_assign(10 ** 11, 42)
    assert st.point_query(10 ** 11) == 42 and st.range_sum(0, 10 ** 12 - 1) == 42


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_universe_too_small_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(0)


def test_universe_negative_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(-5)


def test_update_out_of_range_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).update(20, 1)


def test_update_non_num_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).update(0, "x")


def test_range_out_of_range_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).range_sum(0, 99)


def test_range_inverted_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).range_sum(5, 1)


def test_point_query_out_of_range_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).point_query(99)


def test_assign_non_num_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).point_assign(0, "x")


def test_index_non_int_raises():
    with pytest.raises(SparseSegmentTreeError):
        SparseSegmentTree(10).update(0.5, 1)


def test_error_stores_detail():
    err = SparseSegmentTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    st = SparseSegmentTree(100)
    st.update(1, 5); st.update(2, 10)
    st.reset()
    assert st.is_empty() and st.num_nodes == 0 and st.total() == 0


def test_universe_property():
    assert SparseSegmentTree(2 ** 50).universe == 2 ** 50


def test_default_universe():
    assert SparseSegmentTree().universe == 1 << 62


def test_stats_keys():
    assert set(SparseSegmentTree(100).stats()) == {"universe", "num_nodes", "total"}


def test_stats_values():
    st = SparseSegmentTree(100)
    st.update(1, 5); st.update(2, 10)
    s = st.stats()
    assert s["universe"] == 100 and s["total"] == 15 and s["num_nodes"] > 0


def test_deterministic():
    def build():
        x = SparseSegmentTree(10 ** 9)
        for i, v in [(5, 1), (500000, 2), (10 ** 9 - 2, 3)]:
            x.update(i, v)
        return x.range_sum(0, 10 ** 9 - 1)
    assert build() == build() == 6


def test_universe_one():
    st = SparseSegmentTree(1)
    st.update(0, 5)
    assert st.point_query(0) == 5 and st.range_sum(0, 0) == 5 and st.total() == 5


def test_adjacent_indices():
    st = SparseSegmentTree(10 ** 9)
    st.update(100, 1); st.update(101, 2); st.update(102, 4)
    assert st.range_sum(100, 101) == 3 and st.range_sum(101, 102) == 6 and st.range_sum(100, 102) == 7


def test_assign_zero_then_query():
    st = SparseSegmentTree(1000)
    st.update(7, 9); st.point_assign(7, 0)
    assert st.point_query(7) == 0 and st.total() == 0


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_updates():
    st = SparseSegmentTree(10 ** 9)
    errors = []
    idxs = [i * 1000 for i in range(400)]

    def worker(chunk):
        try:
            for i in chunk:
                st.update(i, 1)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(idxs[k::4],)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and st.total() == 400
    assert all(st.point_query(i) == 1 for i in idxs)
