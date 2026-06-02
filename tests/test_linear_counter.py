"""Phase 112 — unit tests for LinearCounter (pradyos/core/linear_counter.py)."""
from __future__ import annotations

import math
import threading

import pytest

from pradyos.core.linear_counter import LinearCounter, LinearCounterError


# ── basic correctness ──────────────────────────────────────────────────────────

def test_empty_estimate_is_zero():
    assert LinearCounter(num_bits=4096).estimate() == 0.0


def test_add_sets_a_bit():
    c = LinearCounter(num_bits=4096, seed=0)
    c.add("x")
    assert c.bits_set == 1


def test_len_tracks_bits_set():
    c = LinearCounter(num_bits=65536, seed=0)
    for i in range(100):
        c.add(f"k{i}")
    assert len(c) == c.bits_set


def test_duplicate_add_is_idempotent():
    c = LinearCounter(num_bits=65536, seed=2)
    for _ in range(1000):
        c.add("same")
    assert c.bits_set == 1
    assert round(c.estimate()) == 1


def test_add_many():
    c = LinearCounter(num_bits=65536, seed=0)
    c.add_many(f"k{i}" for i in range(500))
    assert 490 <= c.bits_set <= 500          # ~no collisions at this low load


def test_add_many_non_iterable_raises():
    c = LinearCounter(num_bits=4096)
    with pytest.raises(LinearCounterError):
        c.add_many(12345)


# ── accuracy (the defining property) ─────────────────────────────────────────────

def test_accurate_at_moderate_load():
    c = LinearCounter(num_bits=65536, seed=1)
    for i in range(20000):
        c.add(f"item-{i}")
    assert abs(c.estimate() - 20000) / 20000 < 0.03


def test_accurate_near_one_load():
    c = LinearCounter(num_bits=65536, seed=1)
    for i in range(50000):
        c.add(f"item-{i}")
    assert abs(c.estimate() - 50000) / 50000 < 0.03


def test_distinct_count_ignores_multiplicity():
    c = LinearCounter(num_bits=65536, seed=2)
    for i in range(3000):
        for _ in range(5):
            c.add(f"d-{i}")
    assert abs(c.estimate() - 3000) / 3000 < 0.03


def test_zero_bit_law_matches_theory():
    m, n = 65536, 40000
    c = LinearCounter(num_bits=m, seed=3)
    for i in range(n):
        c.add(f"z-{i}")
    expected_zero = m * math.exp(-n / m)
    actual_zero = m - c.bits_set
    assert abs(actual_zero - expected_zero) / expected_zero < 0.02


def test_larger_m_lowers_error():
    def mean_rel_err(m, n=20000, trials=8):
        errs = []
        for s in range(trials):
            c = LinearCounter(num_bits=m, seed=s)
            for i in range(n):
                c.add(f"x-{i}")
            errs.append(abs(c.estimate() - n) / n)
        return sum(errs) / len(errs)
    assert mean_rel_err(131072) < mean_rel_err(32768)


# ── saturation ─────────────────────────────────────────────────────────────────

def test_saturation_raises_on_estimate():
    c = LinearCounter(num_bits=512, seed=4)
    for i in range(20000):
        c.add(f"s-{i}")
    assert c.saturated is True
    with pytest.raises(LinearCounterError):
        c.estimate()


def test_not_saturated_when_room_remains():
    c = LinearCounter(num_bits=65536, seed=0)
    for i in range(100):
        c.add(f"k{i}")
    assert c.saturated is False


def test_stats_estimate_none_when_saturated():
    c = LinearCounter(num_bits=256, seed=4)
    for i in range(20000):
        c.add(f"s-{i}")
    assert c.stats()["estimate"] is None


# ── determinism ──────────────────────────────────────────────────────────────────

def test_same_seed_reproducible():
    a = LinearCounter(num_bits=16384, seed=5)
    b = LinearCounter(num_bits=16384, seed=5)
    for i in range(5000):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a.bits_set == b.bits_set and a.estimate() == b.estimate()


def test_different_seed_diverges_bitmap():
    a = LinearCounter(num_bits=16384, seed=5)
    d = LinearCounter(num_bits=16384, seed=6)
    for i in range(5000):
        a.add(f"k{i}")
        d.add(f"k{i}")
    assert a.bits_set != d.bits_set or a.estimate() != d.estimate()


def test_different_seed_similar_estimate():
    a = LinearCounter(num_bits=16384, seed=5)
    d = LinearCounter(num_bits=16384, seed=6)
    for i in range(5000):
        a.add(f"k{i}")
        d.add(f"k{i}")
    assert abs(a.estimate() - d.estimate()) / a.estimate() < 0.05


# ── configuration & validation ──────────────────────────────────────────────────

def test_invalid_num_bits_zero_raises():
    with pytest.raises(LinearCounterError):
        LinearCounter(num_bits=0)


def test_invalid_num_bits_negative_raises():
    with pytest.raises(LinearCounterError):
        LinearCounter(num_bits=-8)


def test_invalid_seed_raises():
    with pytest.raises(LinearCounterError):
        LinearCounter(num_bits=4096, seed="nope")


def test_bool_num_bits_rejected():
    with pytest.raises(LinearCounterError):
        LinearCounter(num_bits=True)


def test_bool_seed_rejected():
    with pytest.raises(LinearCounterError):
        LinearCounter(num_bits=4096, seed=True)


def test_error_stores_detail():
    err = LinearCounterError(-3)
    assert err.detail == -3
    assert "-3" in str(err)


# ── properties ────────────────────────────────────────────────────────────────────

def test_num_bits_property():
    assert LinearCounter(num_bits=8192).num_bits == 8192


def test_seed_property():
    assert LinearCounter(num_bits=4096, seed=42).seed == 42


def test_load_factor_tracks_bits():
    c = LinearCounter(num_bits=1000, seed=0)
    for i in range(100):
        c.add(f"k{i}")
    assert 0.0 < c.load_factor() <= 0.1


def test_load_factor_empty_is_zero():
    assert LinearCounter(num_bits=4096).load_factor() == 0.0


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(LinearCounter(num_bits=4096).stats()) == {
        "num_bits", "bits_set", "zero_bits", "load_factor", "estimate", "seed"}


def test_stats_initial():
    s = LinearCounter(num_bits=4096, seed=3).stats()
    assert s["num_bits"] == 4096 and s["bits_set"] == 0
    assert s["zero_bits"] == 4096 and s["estimate"] == 0.0 and s["seed"] == 3


def test_stats_reflects_adds():
    c = LinearCounter(num_bits=65536, seed=1)
    for i in range(1000):
        c.add(f"k{i}")
    s = c.stats()
    assert s["bits_set"] >= 1 and s["zero_bits"] == s["num_bits"] - s["bits_set"]
    assert s["estimate"] > 0


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    c = LinearCounter(num_bits=65536, seed=1)
    for i in range(1000):
        c.add(f"k{i}")
    c.reset()
    assert c.bits_set == 0 and c.estimate() == 0.0


def test_reset_reconfigures():
    c = LinearCounter(num_bits=65536, seed=1)
    c.reset(num_bits=8192, seed=9)
    assert c.num_bits == 8192 and c.seed == 9


def test_reset_invalid_raises():
    c = LinearCounter(num_bits=4096)
    with pytest.raises(LinearCounterError):
        c.reset(num_bits=0)


def test_reset_then_re_add():
    c = LinearCounter(num_bits=4096, seed=0)
    c.add("a")
    c.reset()
    c.add("a")
    assert c.bits_set == 1


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds_consistent():
    c = LinearCounter(num_bits=131072, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(500):
                c.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # 5000 distinct items, low load ⇒ bits_set close to 5000 and estimate near it.
    assert abs(c.estimate() - 5000) / 5000 < 0.05
