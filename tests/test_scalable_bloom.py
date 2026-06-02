"""Phase 118 — unit tests for ScalableBloomFilter (pradyos/core/scalable_bloom.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.scalable_bloom import ScalableBloomFilter, ScalableBloomError


# ── basic correctness ──────────────────────────────────────────────────────────

def test_empty_contains_false():
    assert ScalableBloomFilter(seed=0).contains("x") is False


def test_add_then_contains():
    f = ScalableBloomFilter(initial_capacity=1000, seed=0)
    f.add("a")
    assert "a" in f and f.contains("a")


def test_add_returns_true_then_false():
    f = ScalableBloomFilter(initial_capacity=1000, seed=0)
    assert f.add("x") is True
    assert f.add("x") is False           # duplicate
    assert len(f) == 1


def test_len_tracks_distinct():
    f = ScalableBloomFilter(initial_capacity=1000, seed=0)
    for i in range(50):
        f.add(f"k{i}")
    assert len(f) == 50


def test_starts_with_one_layer():
    assert ScalableBloomFilter(initial_capacity=1000, seed=0).num_layers == 1


# ── growth ───────────────────────────────────────────────────────────────────────

def test_grows_past_initial_capacity():
    f = ScalableBloomFilter(initial_capacity=500, error_rate=0.01, growth=2, seed=0)
    for i in range(8000):
        f.add(f"item-{i}")
    assert f.num_layers >= 3


def test_no_false_negatives_after_growth():
    f = ScalableBloomFilter(initial_capacity=500, error_rate=0.01, seed=0)
    added = [f"item-{i}" for i in range(8000)]
    for k in added:
        f.add(k)
    assert all(f.contains(k) for k in added)


def test_low_load_no_growth():
    f = ScalableBloomFilter(initial_capacity=1000, seed=0)
    for i in range(100):                 # well under capacity, no FP-skips expected
        f.add(f"k{i}")
    assert f.num_layers == 1 and len(f) == 100


# ── bounded false-positive rate (the headline guarantee) ──────────────────────────

def test_fp_bounded_after_growth():
    f = ScalableBloomFilter(initial_capacity=1000, error_rate=0.01, seed=0)
    for i in range(10000):
        f.add(f"present-{i}")
    fp = sum(1 for i in range(20000) if f.contains(f"absent-{i}")) / 20000
    assert fp <= 0.015                   # bounded near the 0.01 target despite growth


def test_fp_bounded_at_large_scale():
    f = ScalableBloomFilter(initial_capacity=500, error_rate=0.02, seed=1)
    for i in range(20000):               # 40x initial capacity
        f.add(f"k-{i}")
    fp = sum(1 for i in range(20000) if f.contains(f"miss-{i}")) / 20000
    assert fp <= 0.03


def test_design_fp_bound_within_target():
    f = ScalableBloomFilter(initial_capacity=1000, error_rate=0.01, ratio=0.9, seed=0)
    for i in range(10000):
        f.add(f"k{i}")
    assert f.false_positive_rate() <= 0.01


def test_tighter_ratio_bounds_fp():
    f = ScalableBloomFilter(initial_capacity=1000, error_rate=0.01, ratio=0.5, seed=0)
    for i in range(8000):
        f.add(f"k{i}")
    fp = sum(1 for i in range(10000) if f.contains(f"absent-{i}")) / 10000
    assert fp <= 0.015


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic_layers_and_bits():
    a = ScalableBloomFilter(initial_capacity=500, error_rate=0.01, seed=5)
    b = ScalableBloomFilter(initial_capacity=500, error_rate=0.01, seed=5)
    for i in range(3000):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a.num_layers == b.num_layers
    assert all(a._layers[i].bits == b._layers[i].bits for i in range(a.num_layers))


def test_different_seed_diverges():
    a = ScalableBloomFilter(initial_capacity=500, seed=1)
    b = ScalableBloomFilter(initial_capacity=500, seed=2)
    for i in range(2000):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a._layers[0].bits != b._layers[0].bits


# ── configuration & validation ──────────────────────────────────────────────────

def test_invalid_initial_capacity_raises():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(initial_capacity=0)


def test_invalid_error_rate_zero_raises():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(error_rate=0.0)


def test_invalid_error_rate_one_raises():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(error_rate=1.0)


def test_invalid_ratio_raises():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(ratio=1.0)


def test_invalid_growth_raises():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(growth=1)


def test_invalid_seed_raises():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(seed="nope")


def test_bool_initial_capacity_rejected():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(initial_capacity=True)


def test_bool_growth_rejected():
    with pytest.raises(ScalableBloomError):
        ScalableBloomFilter(growth=True)


def test_error_stores_detail():
    err = ScalableBloomError(-7)
    assert err.detail == -7 and "-7" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    f = ScalableBloomFilter(initial_capacity=2000, error_rate=0.05, ratio=0.8, growth=4, seed=7)
    assert f.initial_capacity == 2000 and f.error_rate == 0.05
    assert f.ratio == 0.8 and f.growth == 4 and f.seed == 7


def test_stats_keys():
    assert set(ScalableBloomFilter(seed=0).stats()) == {
        "count", "num_layers", "initial_capacity", "error_rate", "ratio",
        "growth", "total_bits", "false_positive_rate", "seed"}


def test_stats_values():
    f = ScalableBloomFilter(initial_capacity=1000, error_rate=0.01, seed=3)
    for i in range(50):
        f.add(f"k{i}")
    s = f.stats()
    assert s["count"] == 50 and s["num_layers"] == 1 and s["initial_capacity"] == 1000
    assert s["total_bits"] > 0 and s["seed"] == 3


def test_stats_total_bits_grows_with_layers():
    f = ScalableBloomFilter(initial_capacity=500, error_rate=0.01, seed=0)
    bits_one = f.stats()["total_bits"]
    for i in range(5000):
        f.add(f"k{i}")
    assert f.stats()["total_bits"] > bits_one and f.num_layers > 1


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    f = ScalableBloomFilter(initial_capacity=500, seed=0)
    for i in range(5000):
        f.add(f"k{i}")
    f.reset()
    assert len(f) == 0 and f.num_layers == 1 and not f.contains("k0")


def test_reset_reconfigures():
    f = ScalableBloomFilter(initial_capacity=1000, error_rate=0.01, seed=0)
    f.reset(initial_capacity=2000, error_rate=0.05, ratio=0.8, growth=3, seed=9)
    assert f.initial_capacity == 2000 and f.error_rate == 0.05
    assert f.ratio == 0.8 and f.growth == 3 and f.seed == 9


def test_reset_invalid_raises():
    f = ScalableBloomFilter(seed=0)
    with pytest.raises(ScalableBloomError):
        f.reset(error_rate=2.0)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    f = ScalableBloomFilter(initial_capacity=2000, error_rate=0.01, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(300):
                f.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert all(f.contains(f"t{b}-{i}") for b in range(10) for i in range(300))
