"""Phase 146 — unit tests for Fenwick2D / 2D BIT (pradyos/core/fenwick_2d.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.fenwick_2d import Fenwick2D, Fenwick2DError


def brute_prefix(g, i, j):
    return sum(g[r][c] for r in range(i + 1) for c in range(j + 1))


def brute_range(g, r1, c1, r2, c2):
    return sum(g[r][c] for r in range(r1, r2 + 1) for c in range(c1, c2 + 1))


# ── differential vs brute grid (centerpiece) ─────────────────────────────────────────────

def test_prefix_range_point_differential():
    rng = random.Random(1)
    for (R, C) in [(1, 1), (3, 4), (8, 8), (10, 15), (16, 16), (20, 7)]:
        g = [[0] * C for _ in range(R)]
        ft = Fenwick2D(rows=R, cols=C)
        for _ in range(R * C * 2):
            i, j, d = rng.randrange(R), rng.randrange(C), rng.randint(-50, 50)
            g[i][j] += d
            ft.update(i, j, d)
        for _ in range(60):
            i, j = rng.randrange(R), rng.randrange(C)
            assert ft.prefix_sum(i, j) == brute_prefix(g, i, j)
            assert ft.point_value(i, j) == g[i][j]
            r1 = rng.randrange(R); r2 = rng.randint(r1, R - 1)
            c1 = rng.randrange(C); c2 = rng.randint(c1, C - 1)
            assert ft.range_sum(r1, c1, r2, c2) == brute_range(g, r1, c1, r2, c2)
        assert ft.total() == sum(sum(row) for row in g)


def test_large_grid_differential():
    rng = random.Random(2)
    R = C = 50
    g = [[0] * C for _ in range(R)]
    ft = Fenwick2D(rows=R, cols=C)
    for _ in range(3000):
        i, j, d = rng.randrange(R), rng.randrange(C), rng.randint(-100, 100)
        g[i][j] += d
        ft.update(i, j, d)
    for _ in range(200):
        r1 = rng.randrange(R); r2 = rng.randint(r1, R - 1)
        c1 = rng.randrange(C); c2 = rng.randint(c1, C - 1)
        assert ft.range_sum(r1, c1, r2, c2) == brute_range(g, r1, c1, r2, c2)


# ── basics / edges ────────────────────────────────────────────────────────────────────────

def test_1x1_grid():
    o = Fenwick2D(rows=1, cols=1)
    o.update(0, 0, 7)
    assert o.prefix_sum(0, 0) == 7 and o.range_sum(0, 0, 0, 0) == 7 and o.total() == 7
    assert o.point_value(0, 0) == 7


def test_accumulate_and_negative():
    ft = Fenwick2D(rows=4, cols=4)
    ft.update(1, 1, 10)
    ft.update(1, 1, -3)
    assert ft.point_value(1, 1) == 7 and ft.total() == 7


def test_full_range_equals_total():
    ft = Fenwick2D(rows=5, cols=5)
    for i in range(5):
        for j in range(5):
            ft.update(i, j, i * 5 + j)
    assert ft.range_sum(0, 0, 4, 4) == ft.total() == sum(range(25))


def test_single_cell_update():
    ft = Fenwick2D(rows=3, cols=3)
    ft.update(2, 1, 9)
    assert ft.range_sum(2, 1, 2, 1) == 9 and ft.range_sum(0, 0, 1, 2) == 0


def test_prefix_specific():
    ft = Fenwick2D(rows=3, cols=3)
    ft.update(0, 0, 1); ft.update(0, 1, 2); ft.update(1, 0, 3)
    assert ft.prefix_sum(0, 1) == 3 and ft.prefix_sum(1, 1) == 6


def test_float_deltas():
    ft = Fenwick2D(rows=2, cols=2)
    ft.update(0, 0, 1.5); ft.update(1, 1, 2.25)
    assert ft.total() == 3.75


def test_empty_grid_total_zero():
    assert Fenwick2D(rows=4, cols=4).total() == 0


def test_point_value_after_multiple_updates():
    ft = Fenwick2D(rows=4, cols=4)
    for d in (1, 2, 3, 4):
        ft.update(2, 2, d)
    assert ft.point_value(2, 2) == 10


def test_prefix_sum_corner_origin():
    ft = Fenwick2D(rows=4, cols=4)
    ft.update(0, 0, 5)
    assert ft.prefix_sum(0, 0) == 5


def test_prefix_sum_corner_last_is_total():
    ft = Fenwick2D(rows=3, cols=3)
    ft.update(0, 0, 2); ft.update(2, 2, 4)
    assert ft.prefix_sum(2, 2) == ft.total() == 6


def test_range_single_row():
    ft = Fenwick2D(rows=3, cols=4)
    ft.update(1, 0, 1); ft.update(1, 1, 2); ft.update(1, 3, 4)
    assert ft.range_sum(1, 0, 1, 3) == 7


def test_range_single_column():
    ft = Fenwick2D(rows=4, cols=3)
    ft.update(0, 2, 1); ft.update(2, 2, 3); ft.update(3, 2, 5)
    assert ft.range_sum(0, 2, 3, 2) == 9


def test_total_after_reset_is_zero():
    ft = Fenwick2D(rows=3, cols=3)
    ft.update(1, 1, 99)
    ft.reset()
    assert ft.total() == 0 and ft.point_value(1, 1) == 0


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_update_row_out_of_range_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).update(4, 0, 1)


def test_update_negative_col_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).update(0, -1, 1)


def test_prefix_out_of_range_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).prefix_sum(4, 0)


def test_range_sum_r1_gt_r2_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).range_sum(2, 0, 1, 0)


def test_range_sum_out_of_range_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).range_sum(0, 0, 4, 0)


def test_update_non_int_index_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).update(0.5, 0, 1)


def test_update_non_num_delta_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=4, cols=4).update(0, 0, "x")


def test_bad_dims_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=0, cols=3)


def test_bool_dim_raises():
    with pytest.raises(Fenwick2DError):
        Fenwick2D(rows=True, cols=3)


def test_error_stores_detail():
    err = Fenwick2DError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── reset / introspection / determinism ───────────────────────────────────────────────────────

def test_reset_clears():
    ft = Fenwick2D(rows=3, cols=3)
    ft.update(0, 0, 5)
    ft.reset()
    assert ft.total() == 0


def test_reset_reconfigures():
    ft = Fenwick2D(rows=3, cols=3)
    ft.reset(rows=2, cols=6)
    assert ft.rows == 2 and ft.cols == 6 and ft.total() == 0


def test_rows_cols_properties():
    ft = Fenwick2D(rows=7, cols=9)
    assert ft.rows == 7 and ft.cols == 9


def test_stats_keys_and_values():
    ft = Fenwick2D(rows=4, cols=4)
    for (i, j, d) in [(0, 0, 3), (1, 2, 5), (3, 3, -2), (2, 1, 7)]:
        ft.update(i, j, d)
    s = ft.stats()
    assert set(s) == {"rows", "cols", "cells", "total"}
    assert s["total"] == 13 and s["cells"] == 16


def test_deterministic():
    def build():
        f = Fenwick2D(rows=4, cols=4)
        for (i, j, d) in [(0, 0, 3), (1, 2, 5), (3, 3, -2), (2, 1, 7)]:
            f.update(i, j, d)
        return f
    assert build().range_sum(0, 0, 3, 3) == build().range_sum(0, 0, 3, 3)


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_updates():
    ft = Fenwick2D(rows=10, cols=10)
    errors = []

    def worker(base):
        try:
            for _ in range(500):
                ft.update(base % 10, (base * 7) % 10, 1)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and ft.total() == 5000
