"""Phase 149 — unit tests for PersistentSegmentTree (pradyos/core/persistent_segment_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.persistent_segment_tree import (
    PersistentSegmentTree, PersistentSegmentTreeError)


# ── persistence vs per-version reference arrays (centerpieces) ───────────────────────────

def test_persistence_all_versions():
    rng = random.Random(1)
    for n in (1, 2, 5, 8, 9, 16, 17, 50, 100):
        pst = PersistentSegmentTree([0] * n)
        refs = [[0] * n]
        for _ in range(n * 2):
            v = rng.randrange(len(refs)); i = rng.randrange(n); x = rng.randint(-100, 100)
            nv = pst.update(v, i, x)
            r = refs[v][:]; r[i] = x; refs.append(r)
            assert nv == len(refs) - 1
        # verify EVERY version (incl. oldest) — proves immutability / no aliasing
        for v in range(len(refs)):
            for _ in range(3):
                lo = rng.randrange(n); hi = rng.randint(lo, n - 1)
                assert pst.range_sum(v, lo, hi) == sum(refs[v][lo:hi + 1])
            assert all(pst.point_query(v, i) == refs[v][i] for i in range(n))


def test_large_differential():
    rng = random.Random(2)
    pst = PersistentSegmentTree(list(range(200)))
    refs = [list(range(200))]
    for _ in range(300):
        v = rng.randrange(len(refs)); i = rng.randrange(200); x = rng.randint(-50, 50)
        pst.update(v, i, x)
        r = refs[v][:]; r[i] = x; refs.append(r)
    for _ in range(200):
        v = rng.randrange(len(refs)); lo = rng.randrange(200); hi = rng.randint(lo, 199)
        assert pst.range_sum(v, lo, hi) == sum(refs[v][lo:hi + 1])


# ── persistence semantics ────────────────────────────────────────────────────────────────

def test_v0_unchanged_after_update():
    pst = PersistentSegmentTree([1, 2, 3, 4])
    v1 = pst.update(0, 0, 100)
    assert pst.point_query(0, 0) == 1 and pst.point_query(v1, 0) == 100
    assert pst.range_sum(0, 0, 3) == 10 and pst.range_sum(v1, 0, 3) == 109


def test_branching_history():
    pst = PersistentSegmentTree([0, 0, 0])
    a = pst.update(0, 1, 5)
    b = pst.update(0, 1, 9)
    assert pst.point_query(a, 1) == 5 and pst.point_query(b, 1) == 9 and pst.point_query(0, 1) == 0


def test_update_returns_new_version():
    pst = PersistentSegmentTree([1, 2, 3])
    assert pst.update(0, 0, 9) == 1 and pst.update(1, 1, 9) == 2 and pst.num_versions == 3


def test_update_chain():
    pst = PersistentSegmentTree([0])
    cur = 0
    for k in range(1, 21):
        cur = pst.update(cur, 0, k)
    assert pst.point_query(cur, 0) == 20 and pst.point_query(0, 0) == 0 and pst.num_versions == 21


def test_old_version_query_after_many_updates():
    pst = PersistentSegmentTree([5, 5, 5, 5])
    for k in range(50):
        pst.update(pst.num_versions - 1, k % 4, k)
    assert pst.range_sum(0, 0, 3) == 20 and all(pst.point_query(0, i) == 5 for i in range(4))


# ── shapes / values ──────────────────────────────────────────────────────────────────────

def test_single_element():
    pst = PersistentSegmentTree([7])
    v = pst.update(0, 0, 42)
    assert pst.range_sum(0, 0, 0) == 7 and pst.range_sum(v, 0, 0) == 42 and pst.point_query(v, 0) == 42


def test_power_of_two_size():
    pst = PersistentSegmentTree(list(range(8)))
    assert pst.range_sum(0, 0, 7) == 28 and pst.range_sum(0, 2, 5) == 2 + 3 + 4 + 5


def test_non_power_of_two_size():
    pst = PersistentSegmentTree([1, 2, 3, 4, 5])
    assert pst.range_sum(0, 0, 4) == 15
    v = pst.update(0, 2, 30)
    assert pst.range_sum(v, 0, 4) == 42 and pst.range_sum(0, 0, 4) == 15


def test_range_sum_single_index():
    pst = PersistentSegmentTree([4, 8, 15, 16, 23])
    assert pst.range_sum(0, 2, 2) == 15


def test_float_values():
    pst = PersistentSegmentTree([1.5, 2.5])
    v = pst.update(0, 0, 0.5)
    assert abs(pst.range_sum(v, 0, 1) - 3.0) < 1e-9


def test_negatives():
    pst = PersistentSegmentTree([10, 10, 10])
    v = pst.update(0, 1, -5)
    assert pst.range_sum(v, 0, 2) == 15


def test_point_query_basic():
    pst = PersistentSegmentTree([9, 8, 7, 6])
    assert all(pst.point_query(0, i) == [9, 8, 7, 6][i] for i in range(4))


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_empty_build_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([])


def test_non_numeric_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, "x"])


def test_update_bad_version_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).update(5, 0, 1)


def test_update_bad_index_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).update(0, 9, 1)


def test_update_non_num_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).update(0, 0, "x")


def test_range_sum_lo_gt_hi_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).range_sum(0, 2, 1)


def test_range_sum_out_of_range_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).range_sum(0, 0, 9)


def test_range_sum_bad_version_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).range_sum(9, 0, 1)


def test_point_query_out_of_range_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).point_query(0, 9)


def test_non_int_index_raises():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, 2, 3]).update(0, 0.5, 1)


def test_bool_rejected():
    with pytest.raises(PersistentSegmentTreeError):
        PersistentSegmentTree([1, True, 3])


def test_error_stores_detail():
    err = PersistentSegmentTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / build / reset / determinism ───────────────────────────────────────────────

def test_reset_clears():
    pst = PersistentSegmentTree([1, 2, 3])
    pst.update(0, 0, 5)
    pst.reset()
    assert pst.num_versions == 0 and pst.size == 0


def test_build_replaces():
    pst = PersistentSegmentTree([1, 2])
    pst.build([5, 5, 5])
    assert pst.range_sum(0, 0, 2) == 15 and pst.size == 3 and pst.num_versions == 1


def test_size_property():
    assert PersistentSegmentTree([1, 2, 3, 4, 5]).size == 5


def test_num_versions_property():
    pst = PersistentSegmentTree([1, 2, 3])
    assert pst.num_versions == 1 and len(pst) == 1
    pst.update(0, 0, 9)
    assert pst.num_versions == 2 and len(pst) == 2


def test_stats_keys():
    assert set(PersistentSegmentTree([1, 2, 3]).stats()) == {"size", "num_versions", "nodes"}


def test_stats_nodes_grow():
    pst = PersistentSegmentTree([1, 2, 3, 4])
    before = pst.stats()["nodes"]
    pst.update(0, 0, 9)
    assert pst.stats()["nodes"] > before          # path-copy added O(log n) nodes


def test_deterministic():
    def build():
        p = PersistentSegmentTree([3, 1, 4, 1, 5])
        p.update(0, 2, 9)
        return p
    assert build().range_sum(1, 0, 4) == build().range_sum(1, 0, 4)


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_updates():
    pst = PersistentSegmentTree([0] * 20)
    results = []
    errors = []
    rlock = threading.Lock()

    def worker(base):
        try:
            for k in range(10):
                i = (base * 10 + k) % 20
                x = base * 100 + k + 1
                nv = pst.update(0, i, x)
                with rlock:
                    results.append((nv, i, x))
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and pst.num_versions == 1 + 50
    # every created version is v0 with exactly one index set (others remain 0)
    assert all(pst.point_query(nv, i) == x for nv, i, x in results)
    assert all(pst.point_query(nv, (i + 1) % 20) == 0 for nv, i, x in results)
