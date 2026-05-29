"""Phase 80 — unit tests for FenwickTree (binary indexed tree / prefix sums)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.fenwick import FenwickTree


def _filled(n: int):
    """A tree of size n with value == index at each position 1..n."""
    f = FenwickTree(n)
    for i in range(1, n + 1):
        f.update(i, i)
    return f


# ── construction ──────────────────────────────────────────────────────────────

def test_construction_size():
    assert FenwickTree(10).size == 10


def test_invalid_size_zero_raises():
    with pytest.raises(ValueError):
        FenwickTree(0)


def test_invalid_size_negative_raises():
    with pytest.raises(ValueError):
        FenwickTree(-5)


def test_invalid_size_non_int_raises():
    with pytest.raises(ValueError):
        FenwickTree(3.5)


# ── update / prefix_sum ───────────────────────────────────────────────────────

def test_update_prefix_sum_round_trip():
    f = FenwickTree(5)
    f.update(1, 7)
    assert f.prefix_sum(1) == 7


def test_prefix_sum_zero_is_empty():
    assert _filled(10).prefix_sum(0) == 0


def test_prefix_sum_cumulative():
    f = _filled(10)
    assert f.prefix_sum(5) == 15   # 1+2+3+4+5
    assert f.prefix_sum(10) == 55


def test_update_accumulates():
    f = FenwickTree(5)
    f.update(3, 4)
    f.update(3, 6)
    assert f.point_query(3) == 10


# ── range_sum ─────────────────────────────────────────────────────────────────

def test_range_sum_inclusive():
    assert _filled(10).range_sum(3, 7) == 3 + 4 + 5 + 6 + 7


def test_range_sum_single():
    assert _filled(10).range_sum(5, 5) == 5


def test_range_sum_full():
    assert _filled(10).range_sum(1, 10) == 55


def test_range_sum_identity():
    f = _filled(20)
    assert f.range_sum(4, 12) == f.prefix_sum(12) - f.prefix_sum(3)


# ── point_query ───────────────────────────────────────────────────────────────

def test_point_query_after_updates():
    f = FenwickTree(5)
    f.update(2, 100)
    f.update(4, 50)
    assert f.point_query(2) == 100
    assert f.point_query(4) == 50
    assert f.point_query(1) == 0


def test_negative_delta():
    f = FenwickTree(5)
    f.update(3, 10)
    f.update(3, -4)
    assert f.point_query(3) == 6


def test_float_values():
    f = FenwickTree(5)
    f.update(1, 1.5)
    f.update(3, 2.25)
    assert abs(f.prefix_sum(3) - 3.75) < 1e-9


# ── resize ────────────────────────────────────────────────────────────────────

def test_resize_grow_preserves_and_zero_fills():
    f = _filled(4)
    f.resize(6)
    assert f.size == 6
    assert [f.point_query(i) for i in range(1, 7)] == [1, 2, 3, 4, 0, 0]


def test_resize_shrink_truncates():
    f = _filled(6)
    f.resize(3)
    assert f.size == 3
    assert f.prefix_sum(3) == 6  # 1+2+3


def test_resize_invalid_raises():
    with pytest.raises(ValueError):
        FenwickTree(5).resize(0)


# ── clear / stats ─────────────────────────────────────────────────────────────

def test_clear_resets():
    f = _filled(10)
    f.clear()
    assert f.prefix_sum(10) == 0
    assert f.size == 10


def test_stats_keys():
    stats = FenwickTree(5).stats()
    assert set(stats) == {"size", "total"}


def test_stats_total_is_grand_sum():
    f = _filled(10)
    assert f.stats()["total"] == 55


# ── error handling ────────────────────────────────────────────────────────────

def test_update_out_of_bounds_raises():
    f = FenwickTree(10)
    for bad in (0, 11, -1):
        with pytest.raises(ValueError):
            f.update(bad, 1)


def test_prefix_sum_out_of_bounds_raises():
    f = FenwickTree(10)
    for bad in (-1, 11):
        with pytest.raises(ValueError):
            f.prefix_sum(bad)


def test_range_sum_out_of_bounds_raises():
    f = FenwickTree(10)
    with pytest.raises(ValueError):
        f.range_sum(0, 5)
    with pytest.raises(ValueError):
        f.range_sum(5, 11)


def test_range_sum_lo_gt_hi_raises():
    with pytest.raises(ValueError):
        FenwickTree(10).range_sum(7, 3)


def test_point_query_out_of_bounds_raises():
    with pytest.raises(ValueError):
        FenwickTree(10).point_query(11)


def test_update_bad_delta_raises():
    with pytest.raises(ValueError):
        FenwickTree(10).update(5, "x")


# ── cumulative correctness vs a reference array ───────────────────────────────

def test_cumulative_correctness_random():
    n = 60
    reference = [0] * (n + 1)
    f = FenwickTree(n)
    rng = random.Random(42)
    for _ in range(100):
        i = rng.randint(1, n)
        d = rng.randint(-100, 100)
        reference[i] += d
        f.update(i, d)
    for i in range(0, n + 1):
        assert f.prefix_sum(i) == sum(reference[1:i + 1])
    for i in range(1, n + 1):
        assert f.point_query(i) == reference[i]


def test_large_n_is_fast():
    # O(log n) path: many ops on a million-element tree must stay cheap
    f = FenwickTree(1_000_000)
    rng = random.Random(1)
    for _ in range(5000):
        f.update(rng.randint(1, 1_000_000), 1)
    assert f.prefix_sum(1_000_000) == 5000


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_updates_are_exact():
    f = FenwickTree(100)
    errors: list[Exception] = []

    def worker() -> None:
        try:
            rng = random.Random()
            for _ in range(1000):
                f.update(rng.randint(1, 100), 1)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert f.prefix_sum(100) == 10 * 1000
