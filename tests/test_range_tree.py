"""Phase 157 — unit tests for RangeTree (pradyos/core/range_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.range_tree import RangeTree, RangeTreeError


def _brute(pts, x0, y0, x1, y1):
    return sorted((x, y) for (x, y) in pts if x0 <= x <= x1 and y0 <= y <= y1)


# ── differential vs brute (centerpieces) ─────────────────────────────────────────────────

def test_range_query_and_count_differential():
    rng = random.Random(1)
    for _ in range(40):
        n = rng.randint(1, 200)
        pts = [(rng.randint(-100, 100), rng.randint(-100, 100)) for _ in range(n)]
        rt = RangeTree(pts)
        for _ in range(10):
            x0 = rng.randint(-110, 110); x1 = rng.randint(x0, 110)
            y0 = rng.randint(-110, 110); y1 = rng.randint(y0, 110)
            b = _brute(pts, x0, y0, x1, y1)
            assert rt.range_query(x0, y0, x1, y1) == b
            assert rt.range_count(x0, y0, x1, y1) == len(b)


def test_grid_subrectangle():
    rng = random.Random(2)
    pts = [(gx, gy) for gx in range(50) for gy in range(50)]
    rt = RangeTree(pts)
    for _ in range(30):
        x0 = rng.randint(0, 49); x1 = rng.randint(x0, 49)
        y0 = rng.randint(0, 49); y1 = rng.randint(y0, 49)
        assert rt.range_count(x0, y0, x1, y1) == (x1 - x0 + 1) * (y1 - y0 + 1)
        assert rt.range_query(x0, y0, x1, y1) == _brute(pts, x0, y0, x1, y1)


def test_large_differential():
    rng = random.Random(3)
    big = [(rng.randint(-5000, 5000), rng.randint(-5000, 5000)) for _ in range(3000)]
    rt = RangeTree(big)
    for _ in range(50):
        x0 = rng.randint(-5000, 5000); x1 = rng.randint(x0, 5000)
        y0 = rng.randint(-5000, 5000); y1 = rng.randint(y0, 5000)
        assert rt.range_count(x0, y0, x1, y1) == len(_brute(big, x0, y0, x1, y1))


def test_full_bounds_all():
    rng = random.Random(4)
    pts = [(rng.uniform(0, 1000), rng.uniform(0, 1000)) for _ in range(500)]
    rt = RangeTree(pts)
    assert rt.range_count(0, 0, 1000, 1000) == 500 and len(rt.range_query(0, 0, 1000, 1000)) == 500


# ── specific ─────────────────────────────────────────────────────────────────────────────

def test_no_match():
    rt = RangeTree([(5, 5), (10, 10)])
    assert rt.range_query(0, 0, 1, 1) == [] and rt.range_count(0, 0, 1, 1) == 0


def test_single_point():
    rt = RangeTree([(3, 4)])
    assert rt.range_query(0, 0, 10, 10) == [(3, 4)] and rt.range_count(3, 4, 3, 4) == 1
    assert rt.range_query(5, 5, 9, 9) == []


def test_duplicate_points():
    rt = RangeTree([(2, 2), (2, 2), (2, 2), (5, 5)])
    assert rt.range_count(0, 0, 3, 3) == 3 and len(rt.range_query(0, 0, 10, 10)) == 4


def test_boundary_inclusive():
    rt = RangeTree([(5, 5), (5, 10), (10, 5), (10, 10)])
    assert rt.range_count(5, 5, 10, 10) == 4 and rt.range_count(5, 5, 5, 5) == 1


def test_negative_and_float():
    rt = RangeTree([(-5.5, -5.5), (0.0, 0.0), (5.5, 5.5)])
    assert rt.range_query(-10, -10, 0, 0) == [(-5.5, -5.5), (0.0, 0.0)] and rt.range_count(-1, -1, 10, 10) == 2


def test_collinear_same_x():
    pts = [(7, i) for i in range(100)]
    rt = RangeTree(pts)
    assert rt.range_count(7, 20, 7, 40) == 21 and rt.range_count(0, 0, 6, 1000) == 0
    assert rt.range_query(7, 98, 7, 99) == [(7, 98), (7, 99)]


def test_collinear_same_y():
    pts = [(i, 7) for i in range(100)]
    rt = RangeTree(pts)
    assert rt.range_count(20, 7, 40, 7) == 21


def test_thin_x_strip():
    rng = random.Random(5)
    pts = [(rng.randint(0, 100), rng.randint(0, 100)) for _ in range(300)]
    rt = RangeTree(pts)
    assert rt.range_count(50, 0, 50, 100) == len(_brute(pts, 50, 0, 50, 100))


def test_range_query_returns_sorted():
    rt = RangeTree([(9, 9), (1, 1), (5, 5), (3, 7)])
    assert rt.range_query(0, 0, 10, 10) == [(1, 1), (3, 7), (5, 5), (9, 9)]


def test_count_matches_query_len():
    rng = random.Random(6)
    pts = [(rng.randint(0, 50), rng.randint(0, 50)) for _ in range(100)]
    rt = RangeTree(pts)
    for _ in range(10):
        x0 = rng.randint(0, 50); x1 = rng.randint(x0, 50); y0 = rng.randint(0, 50); y1 = rng.randint(y0, 50)
        assert rt.range_count(x0, y0, x1, y1) == len(rt.range_query(x0, y0, x1, y1))


# ── empty / build / reset ─────────────────────────────────────────────────────────────────

def test_empty_tree():
    e = RangeTree([])
    assert e.size == 0 and e.range_query(0, 0, 10, 10) == [] and e.range_count(0, 0, 10, 10) == 0 and e.height() == 0


def test_empty_no_arg():
    e = RangeTree()
    assert e.is_empty() and e.range_count(0, 0, 5, 5) == 0


def test_rebuild_replaces():
    rt = RangeTree([(1, 1), (2, 2)])
    rt.build([(9, 9), (8, 8), (7, 7)])
    assert rt.size == 3 and rt.range_count(0, 0, 10, 10) == 3 and rt.range_count(0, 0, 5, 5) == 0


def test_reset():
    rt = RangeTree([(1, 1), (2, 2)])
    rt.reset()
    assert rt.is_empty() and rt.size == 0


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_build_bad_point_raises():
    with pytest.raises(RangeTreeError):
        RangeTree([(1, 2), (3,)])


def test_build_non_num_raises():
    with pytest.raises(RangeTreeError):
        RangeTree([(1, "x")])


def test_build_non_iterable_raises():
    with pytest.raises(RangeTreeError):
        RangeTree(5)


def test_range_inverted_raises():
    with pytest.raises(RangeTreeError):
        RangeTree([(1, 2)]).range_query(5, 5, 1, 1)


def test_range_non_num_raises():
    with pytest.raises(RangeTreeError):
        RangeTree([(1, 2)]).range_count(0, 0, "x", 1)


def test_error_stores_detail():
    err = RangeTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / determinism ────────────────────────────────────────────────────────────

def test_size_len():
    rt = RangeTree([(1, 1), (2, 2), (3, 3)])
    assert rt.size == 3 and len(rt) == 3


def test_height_bounded():
    pts = [(i, i) for i in range(1000)]
    rt = RangeTree(pts)
    assert 1 <= rt.height() <= 12          # balanced: ~log2(1000) ≈ 10


def test_stats_keys():
    assert set(RangeTree([(1, 2)]).stats()) == {"size", "height", "x_min", "x_max"}


def test_stats_values():
    rt = RangeTree([(1, 5), (9, 2), (4, 4)])
    s = rt.stats()
    assert s["size"] == 3 and s["x_min"] == 1 and s["x_max"] == 9


def test_deterministic():
    def build():
        return RangeTree([(3, 1), (1, 4), (1, 5), (9, 2), (6, 5)]).range_query(0, 0, 10, 10)
    assert build() == build()


def test_two_points():
    rt = RangeTree([(1, 1), (9, 9)])
    assert rt.range_count(0, 0, 5, 5) == 1 and rt.range_query(0, 0, 10, 10) == [(1, 1), (9, 9)]


def test_thin_y_strip():
    rng = random.Random(8)
    pts = [(rng.randint(0, 100), rng.randint(0, 100)) for _ in range(300)]
    rt = RangeTree(pts)
    assert rt.range_count(0, 50, 100, 50) == len(_brute(pts, 0, 50, 100, 50))


def test_point_query_via_rect():
    rt = RangeTree([(4, 8), (4, 9), (5, 8)])
    assert rt.range_count(4, 8, 4, 8) == 1 and rt.range_query(4, 8, 4, 9) == [(4, 8), (4, 9)]


# ── concurrency (read-only queries on a built tree) ────────────────────────────────────────

def test_concurrent_queries():
    rng = random.Random(7)
    pts = [(rng.randint(0, 1000), rng.randint(0, 1000)) for _ in range(2000)]
    rt = RangeTree(pts)
    errors = []
    results = []

    def worker():
        try:
            ok = all(rt.range_count(lo, lo, lo + 100, lo + 100) ==
                     len(_brute(pts, lo, lo, lo + 100, lo + 100)) for lo in range(0, 900, 100))
            results.append(ok)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
