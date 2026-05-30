"""Phase 91 — unit tests for GKSummary (pradyos/core/gk_quantile.py)."""
from __future__ import annotations

import bisect
import math
import random
import threading

import pytest

from pradyos.core.gk_quantile import GKError, GKSummary


def uniform(n, seed=0):
    rnd = random.Random(seed)
    return [rnd.random() for _ in range(n)]


def rank_error(gk, data_sorted, phi):
    est = gk.query(phi)
    true_rank = bisect.bisect_right(data_sorted, est)
    return abs(true_rank - phi * len(data_sorted))


# ── basic ────────────────────────────────────────────────────────────────────────

def test_insert_and_count():
    gk = GKSummary()
    for x in [1, 2, 3]:
        gk.insert(x)
    assert gk.count() == 3


def test_insert_many_returns_count():
    gk = GKSummary()
    assert gk.insert_many([1, 2, 3, 4]) == 4


def test_query_returns_value():
    gk = GKSummary()
    gk.insert_many(range(100))
    assert gk.query(0.5) is not None


def test_query_empty_returns_none():
    assert GKSummary().query(0.5) is None


def test_len_tracks_n():
    gk = GKSummary()
    gk.insert_many(range(50))
    assert len(gk) == 50


# ── quantile correctness ─────────────────────────────────────────────────────────

def test_median_accuracy_uniform():
    gk = GKSummary(epsilon=0.01)
    data = uniform(10_000)
    gk.insert_many(data)
    assert abs(gk.query(0.5) - 0.5) <= 0.01 + 2 / 10_000


def test_min_is_exact():
    gk = GKSummary(epsilon=0.01)
    data = uniform(5000)
    gk.insert_many(data)
    assert gk.query(0.0) == min(data)


def test_max_is_exact():
    gk = GKSummary(epsilon=0.01)
    data = uniform(5000)
    gk.insert_many(data)
    assert gk.query(1.0) == max(data)


def test_all_quantiles_within_rank_error():
    eps, n = 0.01, 10_000
    gk = GKSummary(epsilon=eps)
    data = uniform(n, seed=3)
    gk.insert_many(data)
    sd = sorted(data)
    for phi in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99):
        assert rank_error(gk, sd, phi) <= eps * n + 1


def test_rank_error_holds_on_sorted_input():
    eps, n = 0.02, 5000
    gk = GKSummary(epsilon=eps)
    gk.insert_many(range(n))                 # adversarial ascending stream
    sd = list(range(n))
    for phi in (0.2, 0.5, 0.8, 0.95):
        assert rank_error(gk, sd, phi) <= eps * n + 1


def test_monotonicity():
    gk = GKSummary(epsilon=0.01)
    gk.insert_many(uniform(8000, seed=5))
    ests = [gk.query(p / 100) for p in range(101)]
    assert all(ests[i] <= ests[i + 1] + 1e-12 for i in range(len(ests) - 1))


def test_single_value():
    gk = GKSummary()
    gk.insert(42.0)
    assert gk.query(0.0) == 42.0 and gk.query(0.5) == 42.0 and gk.query(1.0) == 42.0


def test_known_sequence_median():
    gk = GKSummary(epsilon=0.01)
    gk.insert_many(range(1, 1001))           # 1..1000
    assert abs(gk.query(0.5) - 500) <= 0.01 * 1000 + 1


# ── order independence (of estimates) ────────────────────────────────────────────

def test_order_independent_estimates():
    vals = [i / 1000 for i in range(5000)]
    asc = GKSummary(epsilon=0.01)
    desc = GKSummary(epsilon=0.01)
    asc.insert_many(vals)
    desc.insert_many(reversed(vals))
    span = vals[-1] - vals[0]
    for p in (0.1, 0.25, 0.5, 0.75, 0.9):
        assert abs(asc.query(p) - desc.query(p)) <= 2 * 0.01 * span + 0.01


def test_shuffled_input_consistent():
    data = uniform(6000, seed=11)
    a = GKSummary(epsilon=0.01)
    b = GKSummary(epsilon=0.01)
    a.insert_many(data)
    shuffled = data[:]
    random.Random(9).shuffle(shuffled)
    b.insert_many(shuffled)
    assert abs(a.query(0.5) - b.query(0.5)) <= 0.02


# ── compression / size bound ─────────────────────────────────────────────────────

def test_summary_size_bounded():
    eps, n = 0.01, 10_000
    gk = GKSummary(epsilon=eps)
    gk.insert_many(uniform(n, seed=2))
    size = gk.summary_size
    bound = (1.0 / eps) * math.log2(max(eps * n, 2))
    assert size < bound and size < n // 10


def test_compress_keeps_size_sublinear():
    gk = GKSummary(epsilon=0.05)
    gk.insert_many(uniform(20_000, seed=4))
    assert gk.summary_size < 2000              # vastly smaller than n


def test_force_compress_does_not_break_quantiles():
    gk = GKSummary(epsilon=0.01)
    data = uniform(5000, seed=6)
    gk.insert_many(data)
    before = gk.query(0.5)
    gk.compress()
    assert abs(gk.query(0.5) - before) <= 0.02


def test_smaller_epsilon_larger_summary():
    coarse = GKSummary(epsilon=0.1)
    fine = GKSummary(epsilon=0.005)
    data = uniform(10_000, seed=8)
    coarse.insert_many(data)
    fine.insert_many(data)
    assert fine.summary_size >= coarse.summary_size


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_input():
    a = GKSummary(epsilon=0.01, seed=7)
    b = GKSummary(epsilon=0.01, seed=7)
    data = uniform(3000, seed=1)
    a.insert_many(data)
    b.insert_many(data)
    assert a._s == b._s
    assert a.stats() == b.stats()


def test_seed_stored_but_deterministic_regardless():
    # GK has no RNG, so a different seed must not change the summary.
    a = GKSummary(epsilon=0.01, seed=1)
    b = GKSummary(epsilon=0.01, seed=999)
    data = uniform(2000, seed=2)
    a.insert_many(data)
    b.insert_many(data)
    assert a._s == b._s and a.seed == 1 and b.seed == 999


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_epsilon():
    assert GKSummary().epsilon == 0.01


def test_configurable_epsilon():
    assert GKSummary(epsilon=0.05).epsilon == 0.05


def test_invalid_epsilon_zero_raises():
    with pytest.raises(GKError):
        GKSummary(epsilon=0.0)


def test_invalid_epsilon_one_raises():
    with pytest.raises(GKError):
        GKSummary(epsilon=1.0)


def test_invalid_epsilon_negative_raises():
    with pytest.raises(GKError):
        GKSummary(epsilon=-0.1)


def test_invalid_epsilon_bool_raises():
    with pytest.raises(GKError):
        GKSummary(epsilon=True)


def test_invalid_seed_float_raises():
    with pytest.raises(GKError):
        GKSummary(epsilon=0.01, seed=1.5)


def test_insert_non_number_raises():
    with pytest.raises(GKError):
        GKSummary().insert("not a number")


def test_query_invalid_phi_below_zero_raises():
    gk = GKSummary()
    gk.insert(1)
    with pytest.raises(GKError):
        gk.query(-0.1)


def test_query_invalid_phi_above_one_raises():
    gk = GKSummary()
    gk.insert(1)
    with pytest.raises(GKError):
        gk.query(1.1)


def test_query_invalid_phi_type_raises():
    with pytest.raises(GKError):
        GKSummary().query("half")


def test_gk_error_stores_detail():
    err = GKError(-3)
    assert err.detail == -3
    assert "invalid gk quantile configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(GKSummary().stats()) == {"epsilon", "n", "summary_size", "capacity"}


def test_stats_initial():
    s = GKSummary(epsilon=0.02).stats()
    assert s == {"epsilon": 0.02, "n": 0, "summary_size": 0, "capacity": 0.0}


def test_stats_tracks_n():
    gk = GKSummary()
    gk.insert_many(range(123))
    assert gk.stats()["n"] == 123


def test_stats_capacity_positive_when_populated():
    gk = GKSummary(epsilon=0.01)
    gk.insert_many(uniform(5000))
    assert gk.stats()["capacity"] > 0


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    gk = GKSummary()
    gk.insert_many(range(100))
    gk.reset()
    assert gk.count() == 0 and gk.query(0.5) is None


def test_reset_reconfigures_epsilon():
    gk = GKSummary(epsilon=0.01)
    gk.reset(epsilon=0.05)
    assert gk.epsilon == 0.05


def test_reset_invalid_epsilon_raises():
    gk = GKSummary()
    with pytest.raises(GKError):
        gk.reset(epsilon=0.0)


def test_reset_then_reuse():
    gk = GKSummary(epsilon=0.01)
    gk.insert_many(range(100))
    gk.reset()
    gk.insert_many(range(1000))
    assert abs(gk.query(0.5) - 500) <= 0.01 * 1000 + 1


# ── edge cases & concurrency ─────────────────────────────────────────────────────

def test_duplicate_values():
    gk = GKSummary(epsilon=0.05)
    gk.insert_many([7.0] * 500 + [3.0] * 500)
    assert gk.query(0.25) == 3.0 and gk.query(0.75) == 7.0


def test_negative_and_float_values():
    gk = GKSummary(epsilon=0.01)
    gk.insert_many([-100.5, -50.0, 0.0, 50.0, 100.5] * 200)
    assert gk.query(0.0) == -100.5 and gk.query(1.0) == 100.5


def test_concurrent_inserts_10_threads():
    gk = GKSummary(epsilon=0.01)
    errors = []

    def worker(tag):
        try:
            for i in range(200):
                gk.insert(tag * 1000 + i)
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert gk.count() == 2000
    assert gk.query(0.0) is not None and gk.query(1.0) is not None
