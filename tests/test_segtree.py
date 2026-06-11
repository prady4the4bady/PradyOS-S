"""Phase 81 — unit tests for SegmentTree (range sum/min/max with point updates)."""
from __future__ import annotations

import random
import time

import pytest

from pradyos.core.segtree import SegmentTree


# ── construction ──────────────────────────────────────────────────────────────

def test_construction_size_and_mode():
    t = SegmentTree(10, "min")
    assert t.size == 10
    assert t.mode == "min"


def test_default_mode_is_sum():
    assert SegmentTree(5).mode == "sum"


def test_invalid_size_raises():
    for bad in (0, -1, 2.5):
        with pytest.raises(ValueError):
            SegmentTree(bad)


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        SegmentTree(5, "median")


# ── correctness vs a reference array ──────────────────────────────────────────

@pytest.mark.parametrize("mode, agg", [("sum", sum), ("min", min), ("max", max)])
def test_range_correctness_vs_reference(mode, agg):
    n = 50
    reference = [0] * (n + 1)   # 1-indexed; leaves start at 0
    tree = SegmentTree(n, mode)
    rng = random.Random(13)
    for _ in range(200):
        i = rng.randint(1, n)
        v = rng.randint(-100, 100)
        reference[i] = v       # set semantics
        tree.update(i, v)
    for lo in (1, 5, 20, 50):
        for hi in range(lo, n + 1):
            assert tree.query(lo, hi) == agg(reference[lo:hi + 1])


def test_point_query_matches_reference():
    n = 30
    reference = [0] * (n + 1)
    tree = SegmentTree(n, "max")
    rng = random.Random(99)
    for _ in range(100):
        i = rng.randint(1, n)
        v = rng.randint(-50, 50)
        reference[i] = v
        tree.update(i, v)
    assert all(tree.point_query(i) == reference[i] for i in range(1, n + 1))


# ── update is set-semantics ───────────────────────────────────────────────────

def test_update_overwrites():
    t = SegmentTree(5, "sum")
    t.update(2, 10)
    t.update(2, 3)
    assert t.point_query(2) == 3
    assert t.query(1, 5) == 3


# ── boundaries ────────────────────────────────────────────────────────────────

def test_boundary_first_and_last():
    t = SegmentTree(5, "sum")
    for i in range(1, 6):
        t.update(i, i)
    assert t.query(1, 1) == 1
    assert t.query(5, 5) == 5


def test_single_element_query():
    t = SegmentTree(5, "max")
    t.update(3, 42)
    assert t.query(3, 3) == 42


def test_full_range_query():
    t = SegmentTree(5, "sum")
    for i in range(1, 6):
        t.update(i, i)
    assert t.query(1, 5) == 15


# ── negatives / floats ────────────────────────────────────────────────────────

def test_negative_values_min():
    t = SegmentTree(5, "min")
    for i, v in zip(range(1, 6), [3, -2, 5, -7, 1]):
        t.update(i, v)
    assert t.query(1, 5) == -7
    assert t.query(1, 3) == -2


def test_negative_values_max():
    t = SegmentTree(5, "max")
    for i, v in zip(range(1, 6), [-3, -2, -5, -7, -1]):
        t.update(i, v)
    assert t.query(1, 5) == -1


def test_negative_values_sum():
    t = SegmentTree(3, "sum")
    t.update(1, -5); t.update(2, 2); t.update(3, -1)
    assert t.query(1, 3) == -4


def test_float_values():
    t = SegmentTree(3, "sum")
    t.update(1, 1.5); t.update(2, 2.25)
    assert abs(t.query(1, 3) - 3.75) < 1e-9


# ── resize ────────────────────────────────────────────────────────────────────

def test_resize_grow_preserves_and_clears_extension():
    t = SegmentTree(4, "sum")
    for i in range(1, 5):
        t.update(i, i * 10)
    t.resize(6)
    assert t.size == 6
    assert [t.point_query(i) for i in range(1, 7)] == [10, 20, 30, 40, 0, 0]
    assert t.query(1, 6) == 100


def test_resize_shrink_truncates():
    t = SegmentTree(6, "sum")
    for i in range(1, 7):
        t.update(i, i)
    t.resize(3)
    assert t.size == 3
    assert t.query(1, 3) == 6


def test_resize_preserves_mode():
    t = SegmentTree(4, "max")
    for i in range(1, 5):
        t.update(i, i)
    t.resize(6)
    assert t.mode == "max"
    assert t.query(1, 6) == 4


def test_resize_invalid_raises():
    with pytest.raises(ValueError):
        SegmentTree(5).resize(0)


# ── mode isolation ────────────────────────────────────────────────────────────

def test_mode_isolation():
    s, mn, mx = SegmentTree(3, "sum"), SegmentTree(3, "min"), SegmentTree(3, "max")
    for tree in (s, mn, mx):
        for i, v in zip(range(1, 4), [1, 2, 3]):
            tree.update(i, v)
    assert s.query(1, 3) == 6
    assert mn.query(1, 3) == 1
    assert mx.query(1, 3) == 3


# ── clear / stats ─────────────────────────────────────────────────────────────

def test_clear_resets():
    t = SegmentTree(5, "sum")
    for i in range(1, 6):
        t.update(i, i)
    t.clear()
    assert t.query(1, 5) == 0


def test_stats_keys():
    assert set(SegmentTree(5).stats()) == {"size", "mode", "aggregate"}


def test_stats_aggregate_matches_full_query():
    t = SegmentTree(5, "max")
    for i, v in zip(range(1, 6), [4, 9, 2, 7, 1]):
        t.update(i, v)
    assert t.stats()["aggregate"] == t.query(1, 5) == 9


# ── error handling ────────────────────────────────────────────────────────────

def test_update_out_of_bounds_raises():
    t = SegmentTree(10)
    for bad in (0, 11):
        with pytest.raises(ValueError):
            t.update(bad, 1)


def test_query_out_of_bounds_raises():
    t = SegmentTree(10)
    with pytest.raises(ValueError):
        t.query(0, 5)
    with pytest.raises(ValueError):
        t.query(5, 11)


def test_query_lo_gt_hi_raises():
    with pytest.raises(ValueError):
        SegmentTree(10).query(7, 3)


def test_point_query_out_of_bounds_raises():
    with pytest.raises(ValueError):
        SegmentTree(10).point_query(0)


def test_update_bad_value_raises():
    with pytest.raises(ValueError):
        SegmentTree(10).update(1, "x")


# ── O(log n) performance ──────────────────────────────────────────────────────

def test_log_n_performance():
    t = SegmentTree(1_000_000, "sum")
    start = time.monotonic()
    for i in range(1, 20_001):          # distinct indices → exact sum
        t.update(i, 1)
    elapsed = time.monotonic() - start
    # O(log n): 20k ops on a million-element tree finish near-instantly.
    # Generous bound avoids load-dependent flakiness while ruling out O(n)/op.
    assert elapsed < 0.5
    assert t.query(1, 1_000_000) == 20_000
    assert t.query(1, 20_000) == 20_000


def test_large_range_query_correct():
    t = SegmentTree(1000, "max")
    t.update(617, 999)
    assert t.query(1, 1000) == 999
    assert t.query(1, 616) == 0
    assert t.query(618, 1000) == 0
