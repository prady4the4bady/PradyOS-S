"""Phase 79 — unit tests for TDigest (streaming percentile estimation)."""
from __future__ import annotations

import pytest

from pradyos.core.tdigest import TDigest


def _uniform(n: int) -> TDigest:
    d = TDigest()
    for v in range(1, n + 1):
        d.add(v)
    return d


# ── construction / empty ──────────────────────────────────────────────────────

def test_invalid_max_centroids_raises():
    with pytest.raises(ValueError):
        TDigest(max_centroids=0)


def test_invalid_compression_raises():
    with pytest.raises(ValueError):
        TDigest(compression=0)


def test_empty_count_is_zero():
    assert TDigest().count == 0


def test_empty_percentile_raises():
    with pytest.raises(ValueError):
        TDigest().percentile(50)


def test_empty_quantile_raises():
    with pytest.raises(ValueError):
        TDigest().quantile(0.5)


def test_empty_min_max_raise():
    d = TDigest()
    with pytest.raises(ValueError):
        _ = d.min
    with pytest.raises(ValueError):
        _ = d.max


# ── add / count / extremes ────────────────────────────────────────────────────

def test_count_tracks_adds():
    d = _uniform(100)
    assert d.count == 100


def test_percentile_0_is_min():
    d = _uniform(1000)
    assert d.percentile(0) == d.min == 1


def test_percentile_100_is_max():
    d = _uniform(1000)
    assert d.percentile(100) == d.max == 1000


def test_quantile_0_and_1_are_extremes():
    d = _uniform(500)
    assert d.quantile(0.0) == d.min
    assert d.quantile(1.0) == d.max


# ── accuracy ──────────────────────────────────────────────────────────────────

def test_median_accuracy():
    d = _uniform(1000)
    assert abs(d.percentile(50) - 500.5) <= 20  # within 2% of range


def test_p90_accuracy():
    d = _uniform(1000)
    assert abs(d.percentile(90) - 900) <= 25


def test_percentile_quantile_equivalence():
    d = _uniform(1000)
    assert abs(d.percentile(50) - d.quantile(0.5)) < 1e-9
    assert abs(d.percentile(95) - d.quantile(0.95)) < 1e-9


def test_monotonicity_of_percentiles():
    d = _uniform(1000)
    vals = [d.percentile(p) for p in (1, 10, 25, 50, 75, 90, 99)]
    assert vals == sorted(vals)


def test_single_value_all_percentiles_equal():
    d = TDigest()
    d.add(7)
    assert d.percentile(0) == 7
    assert d.percentile(50) == 7
    assert d.percentile(100) == 7
    assert d.min == d.max == 7


# ── weights ───────────────────────────────────────────────────────────────────

def test_weight_accumulation():
    d = TDigest()
    d.add(5, 10)
    d.add(5, 5)
    assert d.count == 15


def test_weighted_percentile():
    d = TDigest()
    d.add(5, weight=100)
    assert d.percentile(50) == 5


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_count_is_sum():
    a = _uniform(300)
    b = _uniform(200)
    assert a.merge(b).count == 500


def test_merge_is_commutative():
    a = TDigest(); [a.add(v) for v in range(0, 500)]
    b = TDigest(); [b.add(v) for v in range(500, 1000)]
    ab, ba = a.merge(b), b.merge(a)
    for q in (10, 50, 90, 99):
        assert abs(ab.percentile(q) - ba.percentile(q)) < 1e-9


def test_merge_min_max():
    a = TDigest(); a.add(10); a.add(20)
    b = TDigest(); b.add(5); b.add(30)
    m = a.merge(b)
    assert m.min == 5
    assert m.max == 30


def test_merge_with_empty():
    a = _uniform(100)
    m = a.merge(TDigest())
    assert m.count == 100
    assert abs(m.percentile(50) - a.percentile(50)) < 1e-9


def test_merge_returns_new_without_mutating():
    a = TDigest(); a.add(1); a.add(2)
    b = TDigest(); b.add(3)
    a.merge(b)
    assert a.count == 2
    assert b.count == 1


def test_merge_non_tdigest_raises():
    with pytest.raises(ValueError):
        TDigest().merge("nope")


# ── input validation ──────────────────────────────────────────────────────────

def test_add_non_numeric_value_raises():
    with pytest.raises(ValueError):
        TDigest().add("x")


def test_add_non_positive_weight_raises():
    for bad in (0, -1):
        with pytest.raises(ValueError):
            TDigest().add(1, weight=bad)


def test_percentile_out_of_range_raises():
    d = _uniform(10)
    for bad in (-1, 101):
        with pytest.raises(ValueError):
            d.percentile(bad)


def test_quantile_out_of_range_raises():
    d = _uniform(10)
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            d.quantile(bad)


# ── clear / stats ─────────────────────────────────────────────────────────────

def test_clear_resets():
    d = _uniform(100)
    d.clear()
    assert d.count == 0
    with pytest.raises(ValueError):
        d.percentile(50)


def test_stats_keys():
    d = _uniform(50)
    stats = d.stats()
    for key in ("count", "centroids", "min", "max", "max_centroids", "compression"):
        assert key in stats


def test_stats_reflects_extremes():
    d = _uniform(100)
    stats = d.stats()
    assert stats["count"] == 100
    assert stats["min"] == 1
    assert stats["max"] == 100
