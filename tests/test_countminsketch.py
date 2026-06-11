"""Phase 76 — unit tests for CountMinSketch (approximate frequency)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.countminsketch import CountMinSketch


# ── construction ──────────────────────────────────────────────────────────────

def test_default_dimensions():
    c = CountMinSketch()
    assert c.width == 2000
    assert c.depth == 5


def test_custom_dimensions():
    c = CountMinSketch(width=500, depth=3)
    assert c.width == 500
    assert c.depth == 3


def test_invalid_width_raises():
    for bad in (0, -1):
        with pytest.raises(ValueError):
            CountMinSketch(width=bad)


def test_invalid_depth_raises():
    for bad in (0, -3):
        with pytest.raises(ValueError):
            CountMinSketch(depth=bad)


# ── add / estimate ────────────────────────────────────────────────────────────

def test_add_estimate_round_trip():
    c = CountMinSketch()
    c.add("apple")
    assert c.estimate("apple") == 1


def test_frequency_accumulates():
    c = CountMinSketch()
    for _ in range(7):
        c.add("apple")
    assert c.estimate("apple") == 7


def test_add_with_count_param():
    c = CountMinSketch()
    c.add("apple", 5)
    assert c.estimate("apple") == 5


def test_add_count_accumulates_with_singletons():
    c = CountMinSketch()
    c.add("x", 3)
    c.add("x")
    assert c.estimate("x") == 4


def test_estimate_never_undercounts():
    c = CountMinSketch()
    for _ in range(50):
        c.add("hot")
    assert c.estimate("hot") >= 50


def test_estimate_absent_item_is_zero():
    c = CountMinSketch()
    c.add("a")
    c.add("b")
    assert c.estimate("never-added-zzz") == 0


def test_distinct_items_independent():
    c = CountMinSketch()
    c.add("x", 100)
    # a different, unrelated item should not be inflated (large width → no collision)
    assert c.estimate("y") == 0


def test_multiple_items_tracked():
    c = CountMinSketch()
    c.add("a", 2)
    c.add("b", 3)
    c.add("c", 1)
    assert c.estimate("a") == 2
    assert c.estimate("b") == 3
    assert c.estimate("c") == 1


def test_add_invalid_count_raises():
    c = CountMinSketch()
    for bad in (0, -1, 1.5, "3", None):
        with pytest.raises(ValueError):
            c.add("x", bad)


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_returns_new_sketch():
    a = CountMinSketch(width=100, depth=3)
    b = CountMinSketch(width=100, depth=3)
    m = a.merge(b)
    assert m is not a and m is not b
    assert isinstance(m, CountMinSketch)


def test_merge_sums_counts():
    a = CountMinSketch(); a.add("x", 2)
    b = CountMinSketch(); b.add("x", 3)
    assert a.merge(b).estimate("x") == 5


def test_merge_result_at_least_either_source():
    a = CountMinSketch(); a.add("x", 4)
    b = CountMinSketch(); b.add("x", 7)
    m = a.merge(b)
    assert m.estimate("x") >= a.estimate("x")
    assert m.estimate("x") >= b.estimate("x")


def test_merge_is_commutative():
    a = CountMinSketch(); a.add("x", 2); a.add("y", 5)
    b = CountMinSketch(); b.add("x", 3); b.add("z", 1)
    assert a.merge(b).estimate("x") == b.merge(a).estimate("x")
    assert a.merge(b).estimate("y") == b.merge(a).estimate("y")


def test_merge_does_not_mutate_sources():
    a = CountMinSketch(); a.add("x", 2)
    b = CountMinSketch(); b.add("x", 3)
    a.merge(b)
    assert a.estimate("x") == 2
    assert b.estimate("x") == 3


def test_merge_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        CountMinSketch(width=100, depth=3).merge(CountMinSketch(width=200, depth=3))
    with pytest.raises(ValueError):
        CountMinSketch(width=100, depth=3).merge(CountMinSketch(width=100, depth=4))


def test_merge_non_sketch_raises():
    with pytest.raises(ValueError):
        CountMinSketch().merge("not a sketch")


def test_merge_total_is_sum():
    a = CountMinSketch(); a.add("x", 2)
    b = CountMinSketch(); b.add("y", 3)
    assert a.merge(b).stats()["total"] == 5


# ── clear / stats ─────────────────────────────────────────────────────────────

def test_clear_resets():
    c = CountMinSketch()
    c.add("x", 9)
    c.clear()
    assert c.estimate("x") == 0
    assert c.stats()["total"] == 0


def test_stats_keys():
    stats = CountMinSketch().stats()
    for key in ("width", "depth", "cells", "total"):
        assert key in stats


def test_stats_total_accumulates():
    c = CountMinSketch()
    c.add("a", 2)
    c.add("b", 3)
    assert c.stats()["total"] == 5


def test_stats_cells_is_product():
    c = CountMinSketch(width=300, depth=4)
    assert c.stats()["cells"] == 1200


# ── heterogeneous keys ────────────────────────────────────────────────────────

def test_non_string_items():
    c = CountMinSketch()
    c.add(42, 2)
    c.add((1, 2, 3))
    assert c.estimate(42) == 2
    assert c.estimate((1, 2, 3)) == 1


def test_unicode_items():
    c = CountMinSketch()
    c.add("naïve", 3)
    assert c.estimate("naïve") == 3


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_adds_are_exact():
    c = CountMinSketch()
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(1000):
                c.add("shared")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert c.estimate("shared") == 10 * 1000
    assert c.stats()["total"] == 10 * 1000
