"""Phase 148 — unit tests for LiChaoTree (pradyos/core/li_chao_tree.py)."""
from __future__ import annotations

import itertools
import random
import threading

import pytest

from pradyos.core.li_chao_tree import LiChaoTree, LiChaoTreeError


def _brute(lines, x, mode):
    vals = [m * x + b for m, b in lines]
    return min(vals) if mode == "min" else max(vals)


# ── differential vs brute (centerpieces) ─────────────────────────────────────────────────

def test_min_mode_differential():
    rng = random.Random(1)
    for _ in range(40):
        lo, hi = -1000, 1000
        t = LiChaoTree(lo, hi, "min")
        ref = []
        for _ in range(rng.randint(1, 30)):
            m, b = rng.randint(-50, 50), rng.randint(-500, 500)
            t.add_line(m, b); ref.append((m, b))
            for _ in range(5):
                x = rng.randint(lo, hi)
                assert t.query(x) == _brute(ref, x, "min")


def test_max_mode_differential():
    rng = random.Random(2)
    for _ in range(40):
        lo, hi = -1000, 1000
        t = LiChaoTree(lo, hi, "max")
        ref = []
        for _ in range(rng.randint(1, 30)):
            m, b = rng.randint(-50, 50), rng.randint(-500, 500)
            t.add_line(m, b); ref.append((m, b))
            for _ in range(5):
                x = rng.randint(lo, hi)
                assert t.query(x) == _brute(ref, x, "max")


def test_float_lines_differential():
    rng = random.Random(3)
    t = LiChaoTree(0, 1000, "min")
    ref = []
    for _ in range(20):
        m, b = rng.uniform(-5, 5), rng.uniform(-50, 50)
        t.add_line(m, b); ref.append((m, b))
    for _ in range(200):
        x = rng.randint(0, 1000)
        assert abs(t.query(x) - _brute(ref, x, "min")) < 1e-9


def test_order_independent():
    lines = [(2, 3), (-1, 5), (4, -2), (0, 1), (-3, 10)]
    results = set()
    for perm in itertools.permutations(lines):
        t = LiChaoTree(-50, 50)
        for m, b in perm:
            t.add_line(m, b)
        results.add(tuple(t.query(x) for x in range(-50, 51, 10)))
    assert len(results) == 1


def test_many_lines_min():
    rng = random.Random(4)
    t = LiChaoTree(-500, 500)
    ref = [(rng.randint(-20, 20), rng.randint(-200, 200)) for _ in range(50)]
    for m, b in ref:
        t.add_line(m, b)
    assert all(t.query(x) == _brute(ref, x, "min") for x in range(-500, 501, 25))


def test_large_domain():
    t = LiChaoTree(0, 10 ** 9, "min")
    ref = [(3, 5), (-2, 1_000_000), (0, 42), (7, -100)]
    for m, b in ref:
        t.add_line(m, b)
    for x in (0, 1, 1000, 500_000, 10 ** 9):
        assert t.query(x) == _brute(ref, x, "min")


def test_negative_domain():
    t = LiChaoTree(-1000, -1, "max")
    ref = [(1, 0), (-1, -10), (2, 50)]
    for m, b in ref:
        t.add_line(m, b)
    assert all(t.query(x) == _brute(ref, x, "max") for x in range(-1000, 0, 37))


# ── specific behaviour ───────────────────────────────────────────────────────────────────

def test_single_line():
    t = LiChaoTree(0, 100)
    t.add_line(2, 3)
    assert all(t.query(x) == 2 * x + 3 for x in (0, 50, 100))


def test_parallel_lines_min():
    t = LiChaoTree(0, 100)
    for b in (10, 5, 20):
        t.add_line(3, b)
    assert t.query(0) == 5 and t.query(100) == 305


def test_parallel_lines_max():
    t = LiChaoTree(0, 100, "max")
    for b in (10, 5, 20):
        t.add_line(3, b)
    assert t.query(0) == 20 and t.query(100) == 320


def test_crossing_lines():
    t = LiChaoTree(-100, 100)
    t.add_line(5, 0); t.add_line(-5, 0)
    assert t.query(-100) == -500 and t.query(100) == -500 and t.query(0) == 0


def test_domain_edges():
    t = LiChaoTree(-7, 7)
    t.add_line(1, 0); t.add_line(-1, 0)
    assert t.query(-7) == -7 and t.query(7) == -7


def test_query_min_basic():
    t = LiChaoTree(0, 10)
    t.add_line(1, 0); t.add_line(-1, 10)
    assert t.query(0) == 0 and t.query(10) == 0 and t.query(5) == 5


def test_query_max_basic():
    t = LiChaoTree(0, 10, "max")
    t.add_line(1, 0); t.add_line(-1, 10)
    assert t.query(5) == 5 and t.query(0) == 10 and t.query(10) == 10


def test_single_point_domain():
    t = LiChaoTree(5, 5)
    t.add_line(2, 1)
    assert t.query(5) == 11


def test_empty_query_none():
    assert LiChaoTree(0, 10).query(5) is None


def test_duplicate_lines():
    t = LiChaoTree(0, 100)
    t.add_line(2, 3); t.add_line(2, 3)
    assert t.query(10) == 23 and t.num_lines == 2


def test_add_line_increments_count():
    t = LiChaoTree(0, 100)
    t.add_line(1, 1); t.add_line(2, 2)
    assert t.num_lines == 2 and len(t) == 2


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_x_min_gt_x_max_raises():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(10, 0)


def test_bad_mode_raises():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(0, 10, "median")


def test_add_line_non_num_raises():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(0, 10).add_line("x", 1)


def test_query_out_of_domain_raises():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(0, 10).query(99)


def test_query_non_int_raises():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(0, 10).query(0.5)


def test_non_int_domain_raises():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(0.5, 10)


def test_bool_rejected():
    with pytest.raises(LiChaoTreeError):
        LiChaoTree(0, 10).add_line(True, 1)


def test_error_stores_detail():
    err = LiChaoTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset ─────────────────────────────────────────────────────────────────

def test_reset_clears():
    t = LiChaoTree(0, 100)
    t.add_line(1, 2)
    t.reset()
    assert t.num_lines == 0 and t.query(5) is None


def test_reset_reconfigure():
    t = LiChaoTree(0, 100, "min")
    t.reset(x_min=-5, x_max=5, mode="max")
    t.add_line(1, 0)
    assert t.x_min == -5 and t.x_max == 5 and t.mode == "max" and t.query(5) == 5


def test_x_min_max_properties():
    t = LiChaoTree(-3, 9)
    assert t.x_min == -3 and t.x_max == 9


def test_mode_property():
    assert LiChaoTree(0, 1).mode == "min" and LiChaoTree(0, 1, "max").mode == "max"


def test_stats_keys():
    assert set(LiChaoTree(0, 10).stats()) == {"num_lines", "x_min", "x_max", "mode", "nodes"}


def test_stats_values():
    t = LiChaoTree(0, 100, "max")
    t.add_line(1, 2)
    s = t.stats()
    assert s["num_lines"] == 1 and s["x_min"] == 0 and s["x_max"] == 100 and s["mode"] == "max"


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_add_lines():
    t = LiChaoTree(-500, 500)
    errors = []
    ref = [(m, m * 2 - 7) for m in range(-20, 20)]

    def worker(chunk):
        try:
            for m, b in chunk:
                t.add_line(m, b)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(ref[i::4],)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and t.num_lines == len(ref)
    assert all(t.query(x) == _brute(ref, x, "min") for x in range(-500, 501, 50))
