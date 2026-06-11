"""Phase 139 — unit tests for KDTree / Bentley (pradyos/core/kd_tree.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.kd_tree import KDTree, KDTreeError


def d2(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(len(a)))


# ── differential vs brute force (centerpieces) ───────────────────────────────────────────

def test_nearest_differential_2d():
    rng = random.Random(1)
    checks = 0
    for _ in range(40):
        n = rng.randint(1, 300)
        pts = [(rng.randint(-1000, 1000), rng.randint(-1000, 1000)) for _ in range(n)]
        kd = KDTree(pts, dim=2)
        for _ in range(20):
            q = (rng.randint(-1100, 1100), rng.randint(-1100, 1100))
            got = kd.nearest(q)
            assert got is not None and d2(q, got) == min(d2(q, p) for p in pts)
            checks += 1
    assert checks >= 700


def test_nearest_differential_3d():
    rng = random.Random(2)
    for _ in range(30):
        n = rng.randint(1, 200)
        pts = [tuple(rng.randint(-500, 500) for _ in range(3)) for _ in range(n)]
        kd = KDTree(pts, dim=3)
        for _ in range(15):
            q = tuple(rng.randint(-600, 600) for _ in range(3))
            assert d2(q, kd.nearest(q)) == min(d2(q, p) for p in pts)


def test_range_differential_2d():
    rng = random.Random(3)
    for _ in range(40):
        n = rng.randint(1, 300)
        pts = [(rng.randint(0, 500), rng.randint(0, 500)) for _ in range(n)]
        kd = KDTree(pts, dim=2)
        for _ in range(15):
            lo = (rng.randint(0, 500), rng.randint(0, 500))
            hi = (lo[0] + rng.randint(0, 200), lo[1] + rng.randint(0, 200))
            exp = sorted(p for p in pts if lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1])
            assert kd.range(lo, hi) == exp


def test_range_differential_3d():
    rng = random.Random(4)
    for _ in range(25):
        n = rng.randint(1, 200)
        pts = [tuple(rng.randint(0, 100) for _ in range(3)) for _ in range(n)]
        kd = KDTree(pts, dim=3)
        for _ in range(12):
            lo = tuple(rng.randint(0, 100) for _ in range(3))
            hi = tuple(lo[i] + rng.randint(0, 50) for i in range(3))
            exp = sorted(p for p in pts if all(lo[i] <= p[i] <= hi[i] for i in range(3)))
            assert kd.range(lo, hi) == exp


# ── specific / edges ──────────────────────────────────────────────────────────────────────

def test_nearest_point_specific():
    kd = KDTree([(0, 0), (3, 4), (10, 10)], dim=2)
    assert kd.nearest((3, 3)) == (3, 4)


def test_nearest_dist():
    kd = KDTree([(0, 0), (3, 4)], dim=2)
    assert math.isclose(kd.nearest_dist((0, 1)), 1.0)


def test_empty_nearest_none():
    assert KDTree([], dim=2).nearest((1, 2)) is None and KDTree([], dim=2).nearest_dist((1, 2)) is None


def test_empty_range_empty():
    assert KDTree([], dim=2).range((0, 0), (9, 9)) == []


def test_single_point():
    assert KDTree([(5, 5)], dim=2).nearest((0, 0)) == (5, 5)


def test_duplicate_points():
    kd = KDTree([(1, 1), (1, 1), (1, 1)], dim=2)
    assert kd.nearest((1, 1)) == (1, 1) and len(kd) == 3
    assert kd.range((1, 1), (1, 1)) == [(1, 1), (1, 1), (1, 1)]


def test_k1():
    assert KDTree([(3,), (1,), (7,), (2,)], dim=1).nearest((6,)) == (7,)


def test_k4_nearest():
    rng = random.Random(7)
    pts = [tuple(rng.randint(0, 9) for _ in range(4)) for _ in range(80)]
    kd = KDTree(pts, dim=4)
    q = (5, 5, 5, 5)
    assert d2(q, kd.nearest(q)) == min(d2(q, p) for p in pts)


def test_range_inclusive_and_full_and_empty():
    kd = KDTree([(1, 1), (5, 5), (9, 9)], dim=2)
    assert kd.range((1, 1), (5, 5)) == [(1, 1), (5, 5)]   # inclusive endpoints
    assert kd.range((-100, -100), (100, 100)) == [(1, 1), (5, 5), (9, 9)]
    assert kd.range((2, 2), (4, 4)) == []


def test_float_coords():
    kd = KDTree([(1.5, 2.5), (0.0, 0.0)], dim=2)
    assert kd.nearest((1.4, 2.4)) == (1.5, 2.5)


def test_negative_coords():
    kd = KDTree([(-10, -10), (0, 0), (10, 10)], dim=2)
    assert kd.nearest((-8, -8)) == (-10, -10)


def test_range_degenerate_box_single_point():
    kd = KDTree([(2, 3), (2, 3), (5, 5)], dim=2)
    assert kd.range((2, 3), (2, 3)) == [(2, 3), (2, 3)]   # zero-volume box hits exact points


def test_two_points_nearest_each_side():
    kd = KDTree([(0, 0), (100, 100)], dim=2)
    assert kd.nearest((1, 1)) == (0, 0) and kd.nearest((99, 99)) == (100, 100)


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_dim_zero_raises():
    with pytest.raises(KDTreeError):
        KDTree(dim=0)


def test_wrong_dim_point_raises():
    with pytest.raises(KDTreeError):
        KDTree([(1, 2, 3)], dim=2)


def test_non_numeric_coord_raises():
    with pytest.raises(KDTreeError):
        KDTree([(1, "x")], dim=2)


def test_nearest_wrong_dim_raises():
    with pytest.raises(KDTreeError):
        KDTree([(1, 2)], dim=2).nearest((1,))


def test_range_lo_gt_hi_raises():
    with pytest.raises(KDTreeError):
        KDTree([(1, 2)], dim=2).range((5, 5), (1, 1))


def test_non_iterable_points_raises():
    with pytest.raises(KDTreeError):
        KDTree(12345, dim=2)


def test_error_stores_detail():
    err = KDTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / introspection ───────────────────────────────────────────────────────────

def test_build_replaces():
    kd = KDTree([(1, 1)], dim=2)
    kd.build([(9, 9), (8, 8)])
    assert kd.nearest((9, 9)) == (9, 9) and len(kd) == 2


def test_reset_clears():
    kd = KDTree([(1, 1)], dim=2)
    kd.reset()
    assert len(kd) == 0 and kd.nearest((0, 0)) is None


def test_dim_property():
    assert KDTree([], dim=3).dim == 3


def test_size_len():
    kd = KDTree([(1, 1), (2, 2), (3, 3)], dim=2)
    assert len(kd) == 3 and kd.size == 3


def test_height_balanced():
    kd = KDTree([(i, i) for i in range(1000)], dim=2)
    assert 1 <= kd.height() <= (1000).bit_length() + 1   # median split keeps it balanced


def test_stats_keys():
    assert set(KDTree([(1, 2)], dim=2).stats()) == {"size", "dim", "height"}


def test_deterministic():
    rng = random.Random(9)
    pts = [(rng.randint(0, 100), rng.randint(0, 100)) for _ in range(200)]
    assert KDTree(pts, dim=2).nearest((50, 50)) == KDTree(pts, dim=2).nearest((50, 50))


# ── concurrency (read-only queries on a static tree) ──────────────────────────────────────────

def test_concurrent_queries():
    rng = random.Random(5)
    pts = [(rng.randint(-1000, 1000), rng.randint(-1000, 1000)) for _ in range(2000)]
    kd = KDTree(pts, dim=2)
    errors = []
    results = []

    def worker():
        try:
            ok = all(d2(q, kd.nearest(q)) == min(d2(q, p) for p in pts)
                     for q in [(rng.randint(-1000, 1000), rng.randint(-1000, 1000)) for _ in range(20)])
            results.append(ok)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
