"""Phase 153 — unit tests for PRQuadtree (pradyos/core/pr_quadtree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.pr_quadtree import PRQuadtree, PRQuadtreeError


def _brute_rect(d, x0, y0, x1, y1):
    return sorted(k for k, (px, py) in d.items() if x0 <= px <= x1 and y0 <= py <= y1)


def _brute_near(d, x, y):
    best = None; bd = float("inf")
    for k, (px, py) in d.items():
        dd = (px - x) ** 2 + (py - y) ** 2
        if dd < bd or (dd == bd and (best is None or k < best)):
            bd = dd; best = k
    return best


# ── differential vs brute (centerpieces) ─────────────────────────────────────────────────

def test_full_bounds_range_all():
    rng = random.Random(1)
    q = PRQuadtree(0, 0, 1000, 1000, max_depth=12)
    for i in range(1000):
        q.insert(i, rng.uniform(0, 1000), rng.uniform(0, 1000))
    assert q.range_query(0, 0, 1000, 1000) == list(range(1000)) and q.num_points == 1000


def test_grid_subrectangle_brute():
    rng = random.Random(2)
    q = PRQuadtree(0, 0, 100, 100, max_depth=10); g = {}
    pid = 0
    for gx in range(100):
        for gy in range(100):
            q.insert(pid, gx + 0.5, gy + 0.5); g[pid] = (gx + 0.5, gy + 0.5); pid += 1
    for _ in range(30):
        x0 = rng.uniform(0, 100); x1 = rng.uniform(x0, 100)
        y0 = rng.uniform(0, 100); y1 = rng.uniform(y0, 100)
        assert q.range_query(x0, y0, x1, y1) == _brute_rect(g, x0, y0, x1, y1)


def test_nearest_brute():
    rng = random.Random(3)
    q = PRQuadtree(0, 0, 1000, 1000, max_depth=12); r = {}
    for i in range(500):
        x = rng.uniform(0, 1000); y = rng.uniform(0, 1000); q.insert(i, x, y); r[i] = (x, y)
    for _ in range(50):
        x = rng.uniform(0, 1000); y = rng.uniform(0, 1000)
        assert q.nearest(x, y) == _brute_near(r, x, y)


def test_large_nearest_differential():
    rng = random.Random(4)
    q = PRQuadtree(-500, -500, 500, 500, max_depth=12); r = {}
    for i in range(1000):
        x = rng.uniform(-500, 500); y = rng.uniform(-500, 500); q.insert(i, x, y); r[i] = (x, y)
    for _ in range(100):
        x = rng.uniform(-500, 500); y = rng.uniform(-500, 500)
        assert q.nearest(x, y) == _brute_near(r, x, y)


def test_range_after_deletes():
    rng = random.Random(5)
    q = PRQuadtree(0, 0, 64, 64, max_depth=8); r = {}
    for i in range(200):
        x = rng.uniform(0, 64); y = rng.uniform(0, 64); q.insert(i, x, y); r[i] = (x, y)
    for i in range(0, 200, 2):
        q.delete(i); del r[i]
    assert q.range_query(0, 0, 64, 64) == sorted(r) and q.num_points == len(r)


def test_nearest_after_deletes():
    rng = random.Random(6)
    q = PRQuadtree(0, 0, 64, 64, max_depth=8); r = {}
    for i in range(200):
        x = rng.uniform(0, 64); y = rng.uniform(0, 64); q.insert(i, x, y); r[i] = (x, y)
    for i in range(0, 200, 3):
        q.delete(i); del r[i]
    for _ in range(20):
        x = rng.uniform(0, 64); y = rng.uniform(0, 64)
        assert q.nearest(x, y) == _brute_near(r, x, y)


# ── structural / semantic ──────────────────────────────────────────────────────────────────

def test_deterministic():
    def build():
        rr = random.Random(99); q = PRQuadtree(0, 0, 500, 500, max_depth=10)
        for i in range(300):
            q.insert(i, rr.uniform(0, 500), rr.uniform(0, 500))
        return q
    a, b = build(), build()
    assert a.stats() == b.stats() and a.range_query(0, 0, 500, 500) == b.range_query(0, 0, 500, 500)


def test_delete_all_collapse():
    rng = random.Random(7)
    q = PRQuadtree(0, 0, 1000, 1000, max_depth=12)
    for i in range(500):
        q.insert(i, rng.uniform(0, 1000), rng.uniform(0, 1000))
    for i in range(500):
        q.delete(i)
    assert q.num_points == 0 and q.stats()["num_nodes"] == 1


def test_search_exact():
    q = PRQuadtree(0, 0, 16, 16, max_depth=8)
    q.insert("a", 3.0, 4.0); q.insert("b", 10.0, 10.0)
    assert q.search(3.0, 4.0) == "a" and q.search(10.0, 10.0) == "b"


def test_search_miss():
    q = PRQuadtree(0, 0, 16, 16)
    q.insert("a", 3.0, 4.0)
    assert q.search(5.0, 5.0) is None


def test_move_on_duplicate_id():
    q = PRQuadtree(0, 0, 16, 16, max_depth=8)
    q.insert("a", 3.0, 4.0)
    q.insert("a", 12.0, 12.0)
    assert q.search(3.0, 4.0) is None and q.search(12.0, 12.0) == "a" and q.num_points == 1


def test_coincident_points():
    q = PRQuadtree(0, 0, 8, 8, max_depth=4)
    for i in range(5):
        q.insert(i, 4.0, 4.0)
    assert q.num_points == 5 and sorted(q.range_query(3, 3, 5, 5)) == [0, 1, 2, 3, 4]
    assert q.nearest(4, 4) == 0


def test_insert_single():
    q = PRQuadtree(0, 0, 10, 10)
    q.insert("p", 5, 5)
    assert q.num_points == 1 and q.range_query(0, 0, 10, 10) == ["p"]


def test_nearest_single():
    q = PRQuadtree(0, 0, 10, 10)
    q.insert("p", 5, 5)
    assert q.nearest(0, 0) == "p" and q.nearest(9, 9) == "p"


def test_range_point_on_boundary():
    q = PRQuadtree(0, 0, 10, 10)
    q.insert("p", 5, 5)
    assert q.range_query(5, 5, 5, 5) == ["p"]            # inclusive rectangle


def test_float_coords():
    q = PRQuadtree(0.0, 0.0, 1.0, 1.0, max_depth=20)
    q.insert("a", 0.1234, 0.5678); q.insert("b", 0.9, 0.9)
    assert q.nearest(0.12, 0.57) == "a" and q.search(0.9, 0.9) == "b"


def test_negative_bounds():
    q = PRQuadtree(-100, -100, 100, 100, max_depth=10)
    q.insert("a", -50, -50); q.insert("b", 50, 50)
    assert q.range_query(-100, -100, 0, 0) == ["a"] and q.nearest(60, 60) == "b"


def test_delete_returns_bool():
    q = PRQuadtree(0, 0, 10, 10)
    q.insert("p", 1, 1)
    assert q.delete("p") is True


def test_delete_absent_false():
    assert PRQuadtree(0, 0, 10, 10).delete("nope") is False


def test_num_points_and_len():
    q = PRQuadtree(0, 0, 10, 10)
    q.insert("a", 1, 1); q.insert("b", 2, 2)
    assert q.num_points == 2 and len(q) == 2


def test_range_empty():
    q = PRQuadtree(0, 0, 10, 10)
    q.insert("a", 9, 9)
    assert q.range_query(0, 0, 1, 1) == []


def test_nearest_empty_none():
    assert PRQuadtree(0, 0, 10, 10).nearest(5, 5) is None


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_bounds_invalid_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 0, 10)


def test_max_depth_invalid_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10, max_depth=0)


def test_insert_out_of_bounds_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10).insert("p", 20, 5)


def test_insert_non_num_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10).insert("p", "x", 5)


def test_insert_none_id_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10).insert(None, 1, 1)


def test_range_inverted_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10).range_query(5, 5, 1, 1)


def test_search_non_num_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10).search("x", 5)


def test_nearest_non_num_raises():
    with pytest.raises(PRQuadtreeError):
        PRQuadtree(0, 0, 10, 10).nearest("x", 5)


def test_error_stores_detail():
    err = PRQuadtreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset ─────────────────────────────────────────────────────────────────

def test_reset_clears():
    q = PRQuadtree(0, 0, 100, 100)
    for i in range(50):
        q.insert(i, i, i)
    q.reset()
    assert q.num_points == 0 and q.stats()["num_nodes"] == 1


def test_stats_keys():
    assert set(PRQuadtree(0, 0, 10, 10).stats()) == {"num_points", "num_nodes", "max_depth_reached"}


def test_max_depth_reached_bounded():
    q = PRQuadtree(0, 0, 1024, 1024, max_depth=6)
    for i in range(20):
        q.insert(i, 1.0, 1.0)                            # near-coincident → forced to max_depth
    assert q.stats()["max_depth_reached"] <= 6 and q.num_points == 20


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    q = PRQuadtree(0, 0, 1000, 1000, max_depth=12)
    errors = []
    pts = [(i, (i % 100) * 10 + 0.5, (i // 100) * 10 + 0.5) for i in range(400)]

    def worker(chunk):
        try:
            for pid, x, y in chunk:
                q.insert(pid, x, y)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(pts[i::4],)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and q.num_points == 400
    assert q.range_query(0, 0, 1000, 1000) == list(range(400))
