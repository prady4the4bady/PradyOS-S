"""Phase 125 — unit tests for FrugalQuantile (pradyos/core/frugal.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.frugal import FrugalQuantile, FrugalError


def _uniform_stream(n, seed=7, hi=1000.0):
    rng = random.Random(seed)
    return [rng.uniform(0, hi) for _ in range(n)]


# ── convergence ─────────────────────────────────────────────────────────────────

def test_median_converges():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add_many(_uniform_stream(100000))
    assert abs(fq.estimate() - 500) < 80


def test_lower_quartile_converges():
    fq = FrugalQuantile(quantile=0.25, seed=0)
    fq.add_many(_uniform_stream(100000))
    assert abs(fq.estimate() - 250) < 90


def test_upper_quantile_converges():
    fq = FrugalQuantile(quantile=0.9, seed=0)
    fq.add_many(_uniform_stream(100000))
    assert abs(fq.estimate() - 900) < 130


def test_estimates_monotonic_across_quantiles():
    stream = _uniform_stream(100000)
    ests = []
    for q in (0.1, 0.3, 0.5, 0.7, 0.9):
        fq = FrugalQuantile(quantile=q, seed=1)
        fq.add_many(stream)
        ests.append(fq.estimate())
    assert all(ests[i] <= ests[i + 1] + 40 for i in range(len(ests) - 1))


def test_skewed_median_reasonable():
    rng = random.Random(3)
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add_many(rng.expovariate(1 / 100.0) for _ in range(100000))  # true median ~69
    assert 40 < fq.estimate() < 110


def test_tracks_distribution_shift():
    rng = random.Random(5)
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add_many(rng.uniform(0, 100) for _ in range(40000))
    before = fq.estimate()
    fq.add_many(rng.uniform(900, 1000) for _ in range(40000))
    assert before < 120 and fq.estimate() > 600


# ── basic behaviour ─────────────────────────────────────────────────────────────

def test_first_sample_seeds_estimate():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add(42.0)
    assert fq.estimate() == 42.0 and len(fq) == 1


def test_empty_estimate_zero():
    assert FrugalQuantile(quantile=0.5, seed=0).estimate() == 0.0


def test_count_tracks_adds():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add_many(range(100))
    assert fq.count == 100 and len(fq) == 100


def test_accepts_int_and_float():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add(5)
    fq.add(5.5)
    assert fq.count == 2


def test_add_many_non_iterable_raises():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile=0.5, seed=0).add_many(123)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic():
    stream = _uniform_stream(50000)
    a = FrugalQuantile(quantile=0.5, seed=5)
    b = FrugalQuantile(quantile=0.5, seed=5)
    a.add_many(stream)
    b.add_many(stream)
    assert a.estimate() == b.estimate() and a.stats() == b.stats()


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_quantile_zero_raises():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile=0.0)


def test_invalid_quantile_one_raises():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile=1.0)


def test_invalid_quantile_non_number_raises():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile="half")


def test_invalid_seed_raises():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile=0.5, seed="nope")


def test_bool_quantile_rejected():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile=True)


def test_add_non_number_raises():
    with pytest.raises(FrugalError):
        FrugalQuantile(quantile=0.5, seed=0).add("not a number")


def test_error_stores_detail():
    err = FrugalError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    fq = FrugalQuantile(quantile=0.75, seed=7)
    assert fq.quantile == 0.75 and fq.seed == 7


def test_stats_keys():
    assert set(FrugalQuantile(quantile=0.5, seed=0).stats()) == {
        "quantile", "estimate", "step", "count", "seed"}


def test_stats_values():
    fq = FrugalQuantile(quantile=0.5, seed=3)
    fq.add_many(range(100))
    s = fq.stats()
    assert s["quantile"] == 0.5 and s["count"] == 100 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.add_many(range(1000))
    fq.reset()
    assert len(fq) == 0 and fq.estimate() == 0.0


def test_reset_reconfigures():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    fq.reset(quantile=0.9, seed=9)
    assert fq.quantile == 0.9 and fq.seed == 9 and len(fq) == 0


def test_reset_invalid_raises():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    with pytest.raises(FrugalError):
        fq.reset(quantile=2.0)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    errors = []

    def worker():
        try:
            for i in range(500):
                fq.add(float(i % 1000))
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert fq.count == 5000
