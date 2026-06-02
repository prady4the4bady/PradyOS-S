"""Phase 111 — unit tests for MorrisCounter (pradyos/core/morris_counter.py)."""
from __future__ import annotations

import math
import threading

import pytest

from pradyos.core.morris_counter import MorrisCounter, MorrisCounterError


# ── basic correctness ──────────────────────────────────────────────────────────

def test_empty_estimate_is_zero():
    m = MorrisCounter()
    assert m.estimate() == 0.0 and m.register == 0


def test_increment_returns_register():
    m = MorrisCounter(seed=0)
    c = m.increment()
    assert isinstance(c, int) and c == m.register


def test_increments_tally_exact():
    m = MorrisCounter(seed=0)
    m.increment(3)
    m.increment(4)
    assert m.increments == 7


def test_estimate_grows_with_increments():
    m = MorrisCounter(base=2.0, seed=1)
    m.increment(5000)
    assert m.estimate() > 0.0


def test_register_monotonic_non_decreasing():
    m = MorrisCounter(base=2.0, seed=7)
    prev = 0
    for _ in range(2000):
        cur = m.increment(1)
        assert cur >= prev
        prev = cur


def test_increment_default_is_one():
    m = MorrisCounter(seed=0)
    m.increment()
    assert m.increments == 1


# ── unbiasedness (the defining statistical property) ─────────────────────────────

def test_base2_estimate_unbiased():
    n = 10000
    ests = []
    for s in range(400):
        m = MorrisCounter(base=2.0, seed=s)
        m.increment(n)
        ests.append(m.estimate())
    mean_est = sum(ests) / len(ests)
    assert abs(mean_est - n) / n < 0.10        # E[2^c - 1] = n


def test_base_1_5_estimate_unbiased():
    n = 10000
    ests = []
    for s in range(400):
        m = MorrisCounter(base=1.5, seed=s)
        m.increment(n)
        ests.append(m.estimate())
    mean_est = sum(ests) / len(ests)
    assert abs(mean_est - n) / n < 0.08


def test_smaller_base_lowers_variance():
    def mean_rel_error(base, n=5000, trials=150):
        errs = []
        for s in range(trials):
            m = MorrisCounter(base=base, seed=s)
            m.increment(n)
            errs.append(abs(m.estimate() - n) / n)
        return sum(errs) / len(errs)
    assert mean_rel_error(1.1) < mean_rel_error(2.0)


# ── compact register (log-log space) ─────────────────────────────────────────────

def test_register_is_log_log_small():
    m = MorrisCounter(base=2.0, seed=1)
    m.increment(100000)
    # exact counting would need ~17 bits; the register is far smaller.
    assert m.register < 30
    assert m.register < math.ceil(math.log2(100000)) + 12


def test_small_base_register_still_small():
    m = MorrisCounter(base=1.1, seed=3)
    m.increment(10000)
    assert m.register < 200            # still « n = 10000


# ── estimate formula ─────────────────────────────────────────────────────────────

def test_base2_estimate_formula():
    m = MorrisCounter(base=2.0, seed=2)
    m.increment(5000)
    assert m.estimate() == pytest.approx(2 ** m.register - 1)


def test_general_base_estimate_formula():
    m = MorrisCounter(base=1.5, seed=2)
    m.increment(3000)
    expected = (1.5 ** m.register - 1.0) / (1.5 - 1.0)
    assert m.estimate() == pytest.approx(expected)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_same_seed_reproducible():
    a = MorrisCounter(base=2.0, seed=5)
    b = MorrisCounter(base=2.0, seed=5)
    a.increment(8000)
    b.increment(8000)
    assert a.register == b.register and a.estimate() == b.estimate()


def test_different_seed_diverges():
    a = MorrisCounter(base=2.0, seed=5)
    c = MorrisCounter(base=2.0, seed=6)
    a.increment(8000)
    c.increment(8000)
    assert a.register != c.register or a.estimate() != c.estimate()


def test_batched_increment_advances_rng_like_singles_are_deterministic():
    # A single increment(n) is deterministic for a given seed (not claiming equality
    # with n× increment(1) — they consume the RNG identically here since both call
    # random() once per event).
    a = MorrisCounter(base=2.0, seed=9)
    b = MorrisCounter(base=2.0, seed=9)
    a.increment(1000)
    for _ in range(1000):
        b.increment(1)
    assert a.register == b.register


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_base_one_raises():
    with pytest.raises(MorrisCounterError):
        MorrisCounter(base=1.0)


def test_invalid_base_below_one_raises():
    with pytest.raises(MorrisCounterError):
        MorrisCounter(base=0.5)


def test_invalid_base_non_number_raises():
    with pytest.raises(MorrisCounterError):
        MorrisCounter(base="two")


def test_bool_base_rejected():
    with pytest.raises(MorrisCounterError):
        MorrisCounter(base=True)


def test_invalid_seed_raises():
    with pytest.raises(MorrisCounterError):
        MorrisCounter(seed="nope")


def test_bool_seed_rejected():
    with pytest.raises(MorrisCounterError):
        MorrisCounter(seed=True)


def test_increment_zero_times_raises():
    m = MorrisCounter()
    with pytest.raises(MorrisCounterError):
        m.increment(0)


def test_increment_negative_times_raises():
    m = MorrisCounter()
    with pytest.raises(MorrisCounterError):
        m.increment(-5)


def test_increment_non_int_times_raises():
    m = MorrisCounter()
    with pytest.raises(MorrisCounterError):
        m.increment(2.5)


def test_increment_bool_times_rejected():
    m = MorrisCounter()
    with pytest.raises(MorrisCounterError):
        m.increment(True)


def test_error_stores_detail():
    err = MorrisCounterError(0.5)
    assert err.detail == 0.5
    assert "0.5" in str(err)


# ── properties ────────────────────────────────────────────────────────────────────

def test_base_property():
    assert MorrisCounter(base=1.5).base == 1.5


def test_seed_property():
    assert MorrisCounter(seed=42).seed == 42


def test_register_and_increments_properties():
    m = MorrisCounter(seed=0)
    m.increment(10)
    assert m.increments == 10 and isinstance(m.register, int)


def test_int_base_accepted_and_coerced_to_float():
    m = MorrisCounter(base=3)
    assert m.base == 3.0 and isinstance(m.base, float)


# ── relative_error & stats ───────────────────────────────────────────────────────

def test_relative_error_zero_before_increment():
    assert MorrisCounter().relative_error() == 0.0


def test_relative_error_reasonable_on_average():
    # A single counter's error is random; the *mean* over many counters is the
    # meaningful, stable quantity (small base ⇒ low average error).
    errs = []
    for s in range(150):
        m = MorrisCounter(base=1.2, seed=s)
        m.increment(20000)
        errs.append(m.relative_error())
    assert sum(errs) / len(errs) < 0.35        # measured ≈ 0.25


def test_stats_keys():
    assert set(MorrisCounter().stats()) == {
        "register", "estimate", "increments", "base", "relative_error", "seed"}


def test_stats_initial():
    s = MorrisCounter(base=2.0, seed=3).stats()
    assert s["register"] == 0 and s["estimate"] == 0.0 and s["increments"] == 0
    assert s["base"] == 2.0 and s["relative_error"] == 0.0 and s["seed"] == 3


def test_stats_reflects_increments():
    m = MorrisCounter(base=2.0, seed=1)
    m.increment(1000)
    s = m.stats()
    assert s["increments"] == 1000 and s["register"] >= 1 and s["estimate"] > 0


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    m = MorrisCounter(base=2.0, seed=1)
    m.increment(5000)
    m.reset()
    assert m.register == 0 and m.increments == 0 and m.estimate() == 0.0


def test_reset_reconfigures():
    m = MorrisCounter(base=2.0, seed=1)
    m.reset(base=1.5, seed=9)
    assert m.base == 1.5 and m.seed == 9


def test_reset_invalid_base_raises():
    m = MorrisCounter()
    with pytest.raises(MorrisCounterError):
        m.reset(base=1.0)


def test_reset_re_seeds_determinism():
    a = MorrisCounter(base=2.0, seed=5)
    a.increment(500)
    a.reset(seed=5)
    b = MorrisCounter(base=2.0, seed=5)
    a.increment(3000)
    b.increment(3000)
    assert a.register == b.register        # reset restored the RNG sequence


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_increments_tally_exact():
    m = MorrisCounter(base=2.0, seed=0)
    errors = []

    def worker():
        try:
            for _ in range(500):
                m.increment(1)
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert m.increments == 5000               # tally exact under the lock
    assert m.register >= 1
