"""Phase 167 — unit tests for ConvexHull (pradyos/core/convex_hull.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.convex_hull import ConvexHull, ConvexHullError, _cross


def _giftwrap_set(pts):
    pts = sorted(set(pts)); n = len(pts)
    if n <= 2:
        return set(pts)
    hull = set(); start = pts[0]; point = start; guard = 0
    while True:
        hull.add(point); nxt = None
        for cand in pts:
            if cand == point:
                continue
            if nxt is None:
                nxt = cand; continue
            c = _cross(point, nxt, cand)
            if c < 0 or (c == 0 and ((cand[0] - point[0]) ** 2 + (cand[1] - point[1]) ** 2)
                         > ((nxt[0] - point[0]) ** 2 + (nxt[1] - point[1]) ** 2)):
                nxt = cand
        point = nxt; guard += 1
        if point == start or guard > n + 1:
            break
    return hull


def _strictly_convex(h):
    if len(h) < 3:
        return True
    return all(_cross(h[i], h[(i + 1) % len(h)], h[(i + 2) % len(h)]) > 0 for i in range(len(h)))


# ── differential vs independent gift-wrapping (centerpieces) ──────────────────────────────

def test_hull_vs_giftwrap_and_invariants():
    rng = random.Random(1)
    for _ in range(60):
        n = rng.randint(1, 40)
        pts = [(rng.randint(-30, 30), rng.randint(-30, 30)) for _ in range(n)]
        ch = ConvexHull(pts); h = ch.hull()
        assert set(h) == _giftwrap_set(pts)
        assert all(ch.contains(x, y) for (x, y) in pts)         # every input inside-or-on
        assert _strictly_convex(h)
        assert set(h).issubset(set(pts))


def test_large_differential():
    rng = random.Random(2)
    pts = [(rng.randint(-1000, 1000), rng.randint(-1000, 1000)) for _ in range(500)]
    ch = ConvexHull(pts)
    assert set(ch.hull()) == _giftwrap_set(pts) and all(ch.contains(x, y) for x, y in pts)


# ── known shapes ─────────────────────────────────────────────────────────────────────────

def test_square():
    ch = ConvexHull([(0, 0), (0, 10), (10, 10), (10, 0), (5, 5), (3, 7), (9, 1)])
    assert set(ch.hull()) == {(0, 0), (0, 10), (10, 10), (10, 0)} and ch.num_hull_points == 4


def test_square_area_perimeter():
    ch = ConvexHull([(0, 0), (0, 10), (10, 10), (10, 0)])
    assert ch.area() == 100.0 and abs(ch.perimeter() - 40.0) < 1e-9


def test_square_contains():
    ch = ConvexHull([(0, 0), (0, 10), (10, 10), (10, 0)])
    assert ch.contains(5, 5) and ch.contains(0, 5) and ch.contains(0, 0)
    assert not ch.contains(11, 5) and not ch.contains(-1, 5) and not ch.contains(5, 11)


def test_triangle():
    ch = ConvexHull([(0, 0), (4, 0), (0, 3)])
    assert ch.area() == 6.0 and ch.num_hull_points == 3 and abs(ch.perimeter() - 12.0) < 1e-9


def test_pentagon_contains():
    ch = ConvexHull([(0, 0), (4, 0), (5, 3), (2, 5), (-1, 3)])
    assert ch.num_hull_points == 5 and ch.contains(2, 2) and not ch.contains(10, 10)


# ── degeneracies ─────────────────────────────────────────────────────────────────────────

def test_collinear():
    ch = ConvexHull([(0, 0), (1, 1), (2, 2), (3, 3), (5, 5)])
    assert set(ch.hull()) == {(0, 0), (5, 5)} and ch.area() == 0.0
    assert ch.contains(2, 2) and not ch.contains(2, 3)


def test_duplicates():
    ch = ConvexHull([(0, 0), (0, 0), (10, 0), (10, 0), (5, 10), (5, 10)])
    assert ch.num_points == 3 and ch.num_hull_points == 3 and ch.area() == 50.0


def test_empty():
    ch = ConvexHull([])
    assert ch.is_empty() and ch.hull() == [] and ch.area() == 0.0 and ch.perimeter() == 0.0
    assert not ch.contains(0, 0)


def test_single_point():
    ch = ConvexHull([(3, 4)])
    assert ch.hull() == [(3, 4)] and ch.contains(3, 4) and not ch.contains(0, 0) and ch.area() == 0.0


def test_two_points():
    ch = ConvexHull([(0, 0), (4, 0)])
    assert set(ch.hull()) == {(0, 0), (4, 0)} and abs(ch.perimeter() - 4.0) < 1e-9
    assert ch.contains(2, 0) and not ch.contains(2, 1)


def test_all_same_point():
    ch = ConvexHull([(5, 5), (5, 5), (5, 5)])
    assert ch.num_hull_points == 1 and ch.contains(5, 5) and not ch.contains(5, 6)


def test_floats():
    ch = ConvexHull([(0.0, 0.0), (2.0, 0.0), (1.0, 2.0)])
    assert abs(ch.area() - 2.0) < 1e-9


# ── introspection ──────────────────────────────────────────────────────────────────────────

def test_num_points_and_len():
    ch = ConvexHull([(0, 0), (1, 1), (2, 0)])
    assert ch.num_points == 3 and len(ch) == 3


def test_hull_is_ccw():
    ch = ConvexHull([(0, 0), (10, 0), (10, 10), (0, 10)])
    h = ch.hull()
    assert _strictly_convex(h)                              # CCW orientation


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_build_bad_point_raises():
    with pytest.raises(ConvexHullError):
        ConvexHull([(1, 2), (3,)])


def test_build_non_num_raises():
    with pytest.raises(ConvexHullError):
        ConvexHull([(1, "x")])


def test_build_non_iterable_raises():
    with pytest.raises(ConvexHullError):
        ConvexHull(5)


def test_contains_non_num_raises():
    with pytest.raises(ConvexHullError):
        ConvexHull([(0, 0), (1, 0), (0, 1)]).contains("x", 1)


def test_error_stores_detail():
    err = ConvexHullError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / determinism ────────────────────────────────────────────────────────────

def test_reset_clears():
    ch = ConvexHull([(0, 0), (10, 0), (5, 5)])
    ch.reset()
    assert ch.is_empty() and ch.hull() == []


def test_build_replaces():
    ch = ConvexHull([(0, 0), (10, 0), (5, 5)])
    ch.build([(0, 0), (0, 2), (2, 2), (2, 0)])
    assert ch.area() == 4.0 and ch.num_hull_points == 4


def test_stats_keys():
    assert set(ConvexHull([(0, 0), (1, 0), (0, 1)]).stats()) == {
        "num_points", "num_hull_points", "area", "perimeter"}


def test_stats_values():
    ch = ConvexHull([(0, 0), (4, 0), (4, 3), (0, 3)])
    s = ch.stats()
    assert s["num_points"] == 4 and s["num_hull_points"] == 4 and s["area"] == 12.0


def test_deterministic():
    def build():
        return ConvexHull([(0, 0), (4, 0), (4, 3), (0, 3), (2, 1)]).hull()
    assert build() == build()


# ── concurrency (read-only queries on a built hull) ───────────────────────────────────────

def test_concurrent_queries():
    rng = random.Random(3)
    pts = [(rng.randint(-500, 500), rng.randint(-500, 500)) for _ in range(400)]
    ch = ConvexHull(pts)
    errors = []
    results = []

    def worker():
        try:
            ok = all(ch.contains(x, y) for x, y in pts) and ch.area() >= 0
            results.append(ok)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10


# ── extra shapes / invariants ─────────────────────────────────────────────────────────────

def test_perimeter_two_point_hull():
    ch = ConvexHull([(0, 0), (3, 4)])                 # 3-4-5 → single segment of length 5
    assert abs(ch.perimeter() - 5.0) < 1e-9 and ch.area() == 0.0


def test_area_order_invariant():
    pts = [(0, 0), (4, 0), (4, 3), (0, 3), (2, 1), (1, 2)]
    rng = random.Random(7)
    base = ConvexHull(pts).area()
    for _ in range(5):
        shuffled = pts[:]
        rng.shuffle(shuffled)
        assert ConvexHull(shuffled).area() == base == 12.0


def test_negative_coords_hull():
    ch = ConvexHull([(-5, -5), (-1, -5), (-1, -1), (-5, -1), (-3, -3)])
    assert set(ch.hull()) == {(-5, -5), (-1, -5), (-1, -1), (-5, -1)}
    assert ch.area() == 16.0 and ch.contains(-3, -3) and not ch.contains(0, 0)


def test_hexagon():
    pts = [(0, 2), (2, 0), (4, 0), (6, 2), (4, 4), (2, 4), (3, 2)]   # last point interior
    ch = ConvexHull(pts)
    assert ch.num_hull_points == 6 and ch.contains(3, 2) and set(ch.hull()) == _giftwrap_set(pts)
    assert _strictly_convex(ch.hull())


def test_rebuild_after_reset():
    ch = ConvexHull([(0, 0), (4, 0), (2, 3)])
    ch.reset()
    assert ch.is_empty()
    ch.build([(0, 0), (0, 5), (5, 5), (5, 0)])
    assert ch.num_hull_points == 4 and ch.area() == 25.0


def test_contains_below_square():
    ch = ConvexHull([(0, 0), (4, 0), (4, 4), (0, 4)])
    assert not ch.contains(2, -1) and not ch.contains(2, 5)
    assert ch.contains(2, 0) and ch.contains(2, 4)


def test_concave_dent_excluded():
    # (2, 1) sits inside the square and must NOT become a hull vertex.
    ch = ConvexHull([(0, 0), (4, 0), (2, 1), (4, 4), (0, 4)])
    assert set(ch.hull()) == {(0, 0), (4, 0), (4, 4), (0, 4)}
    assert ch.num_hull_points == 4 and ch.contains(2, 1)
