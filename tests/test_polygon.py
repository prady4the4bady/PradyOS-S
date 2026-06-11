"""Phase 168 — unit tests for Polygon (pradyos/core/polygon.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.polygon import Polygon, PolygonError, _on_segment


def _winding(verts, x, y):
    """Independent point-in-polygon via the winding number (cross-check for ray casting)."""
    n = len(verts)
    for i in range(n):
        if _on_segment(verts[i], verts[(i + 1) % n], (x, y)):
            return True
    wn = 0
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        is_left = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if y1 <= y:
            if y2 > y and is_left > 0:
                wn += 1
        else:
            if y2 <= y and is_left < 0:
                wn -= 1
    return wn != 0


def _star_polygon(pts):
    """A simple (star-shaped) polygon: sort unique points by angle around the centroid."""
    pts = list(set(pts))
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return sorted(pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))


# ── differential: ray casting vs winding number (centerpieces) ────────────────────────────

def test_contains_vs_winding_differential():
    rng = random.Random(1)
    for _ in range(80):
        pts = [(rng.randint(-20, 20), rng.randint(-20, 20)) for _ in range(rng.randint(5, 14))]
        verts = _star_polygon(pts)
        if len(verts) < 4:
            continue
        poly = Polygon(verts)
        for _ in range(120):
            x = rng.randint(-22, 22) + 0.5         # half-int avoids exact boundary ties
            y = rng.randint(-22, 22) + 0.5
            assert poly.contains(x, y) == _winding(verts, x, y)


def test_L_shape_grid_brute():
    poly = Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])
    for gx in range(-1, 6):
        for gy in range(-1, 6):
            x, y = gx + 0.5, gy + 0.5
            truth = (0 < x < 4 and 0 < y < 2) or (0 < x < 2 and 0 < y < 4)
            assert poly.contains(x, y) == truth


def test_L_shape_is_nonconvex():
    poly = Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])
    assert poly.area() == 12.0 and poly.is_convex() is False


def test_L_dent_is_outside():
    poly = Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])
    assert not poly.contains(3, 3)             # the reflex corner / dent
    assert poly.contains(1, 3) and poly.contains(3, 1)


# ── square ───────────────────────────────────────────────────────────────────────────────

def test_square_area_perimeter():
    sq = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    assert sq.area() == 16.0 and abs(sq.perimeter() - 16.0) < 1e-9


def test_square_convex_ccw():
    sq = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    assert sq.is_convex() is True and sq.orientation() == "CCW"


def test_square_centroid():
    c = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]).centroid()
    assert abs(c[0] - 2) < 1e-9 and abs(c[1] - 2) < 1e-9


def test_square_contains():
    sq = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    assert sq.contains(2, 2) and sq.contains(0, 2) and sq.contains(0, 0)
    assert not sq.contains(5, 2) and not sq.contains(2, -1)


def test_cw_orientation():
    cw = Polygon([(0, 0), (0, 4), (4, 4), (4, 0)])
    assert cw.orientation() == "CW" and cw.area() == 16.0 and cw.is_convex() is True


# ── triangle / pentagon ─────────────────────────────────────────────────────────────────

def test_triangle_area_and_centroid():
    tri = Polygon([(0, 0), (6, 0), (0, 3)])
    c = tri.centroid()
    assert tri.area() == 9.0 and abs(c[0] - 2) < 1e-9 and abs(c[1] - 1) < 1e-9


def test_triangle_convex():
    assert Polygon([(0, 0), (6, 0), (0, 3)]).is_convex() is True


def test_pentagon_convex():
    pent = Polygon([(math.cos(2 * math.pi * k / 5), math.sin(2 * math.pi * k / 5)) for k in range(5)])
    assert pent.is_convex() is True and pent.orientation() == "CCW"


# ── order matters (vs ConvexHull which sorts+dedupes) ─────────────────────────────────────

def test_vertices_preserve_order():
    verts = [(2, 2), (0, 0), (4, 0), (1, 5)]
    assert Polygon(verts).vertices() == verts          # NOT sorted, NOT deduped


def test_duplicate_vertices_preserved():
    verts = [(0, 0), (0, 0), (4, 0), (4, 4), (0, 4)]
    assert Polygon(verts).num_vertices == 5            # duplicates kept (unlike a hull)


def test_order_matters_bowtie():
    square = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    bowtie = Polygon([(0, 0), (4, 4), (4, 0), (0, 4)])  # same point set, self-intersecting order
    assert square.area() == 16.0 and bowtie.area() != square.area()


# ── degeneracies ─────────────────────────────────────────────────────────────────────────

def test_collinear_degenerate():
    deg = Polygon([(0, 0), (1, 1), (2, 2)])
    assert deg.area() == 0.0 and deg.orientation() == "degenerate"


def test_collinear_centroid_mean():
    c = Polygon([(0, 0), (1, 1), (2, 2)]).centroid()
    assert abs(c[0] - 1) < 1e-9 and abs(c[1] - 1) < 1e-9


def test_empty():
    p = Polygon([])
    assert p.is_empty() and p.area() == 0.0 and p.perimeter() == 0.0
    assert p.centroid() is None and not p.contains(0, 0)


def test_single_point():
    p = Polygon([(3, 4)])
    assert p.contains(3, 4) and not p.contains(0, 0) and p.area() == 0.0
    assert p.is_convex() is False and p.centroid() == (3, 4)


def test_two_points():
    p = Polygon([(0, 0), (4, 0)])
    assert p.contains(2, 0) and not p.contains(2, 1)
    assert abs(p.perimeter() - 4.0) < 1e-9 and p.area() == 0.0


def test_floats():
    assert abs(Polygon([(0.0, 0.0), (2.0, 0.0), (1.0, 2.0)]).area() - 2.0) < 1e-9


def test_contains_negative_region():
    sq = Polygon([(-4, -4), (-1, -4), (-1, -1), (-4, -1)])
    assert sq.contains(-2, -2) and not sq.contains(0, 0)


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_build_bad_vertex_raises():
    with pytest.raises(PolygonError):
        Polygon([(0, 0), (1,)])


def test_build_non_num_raises():
    with pytest.raises(PolygonError):
        Polygon([(0, 0), (1, "y")])


def test_build_non_iterable_raises():
    with pytest.raises(PolygonError):
        Polygon(5)


def test_contains_non_num_raises():
    with pytest.raises(PolygonError):
        Polygon([(0, 0), (4, 0), (0, 4)]).contains("x", 1)


def test_error_stores_detail():
    err = PolygonError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_num_vertices_and_len():
    p = Polygon([(0, 0), (4, 0), (0, 4)])
    assert p.num_vertices == 3 and len(p) == 3


def test_reset_clears():
    p = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    p.reset()
    assert p.is_empty() and p.area() == 0.0


def test_build_replaces():
    p = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    p.build([(0, 0), (2, 0), (2, 2)])
    assert p.area() == 2.0 and p.num_vertices == 3


def test_stats_keys():
    assert set(Polygon([(0, 0), (4, 0), (0, 4)]).stats()) == {
        "num_vertices", "area", "perimeter", "is_convex", "orientation"}


def test_stats_values():
    s = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]).stats()
    assert s["num_vertices"] == 4 and s["area"] == 16.0 and s["is_convex"] is True
    assert s["orientation"] == "CCW" and abs(s["perimeter"] - 16.0) < 1e-9


def test_stats_nonconvex():
    s = Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)]).stats()
    assert s["is_convex"] is False and s["area"] == 12.0


def test_deterministic():
    def build():
        return Polygon([(0, 0), (5, 0), (5, 5), (0, 5), (2, 3)]).stats()
    assert build() == build()


def test_perimeter_two_points_single_segment():
    assert abs(Polygon([(0, 0), (3, 4)]).perimeter() - 5.0) < 1e-9


# ── concurrency (read-only queries on a built polygon) ────────────────────────────────────

def test_concurrent_queries():
    rng = random.Random(3)
    verts = _star_polygon([(rng.randint(-50, 50), rng.randint(-50, 50)) for _ in range(40)])
    poly = Polygon(verts)
    errors = []
    results = []

    def worker():
        try:
            ok = poly.area() >= 0 and isinstance(poly.is_convex(), bool)
            for _ in range(50):
                poly.contains(rng.randint(-50, 50) + 0.5, rng.randint(-50, 50) + 0.5)
            results.append(ok)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
