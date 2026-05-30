"""Phase 92 — unit tests for KLLSketch (pradyos/core/kll_sketch.py)."""
from __future__ import annotations

import bisect
import random
import threading

import pytest

from pradyos.core.kll_sketch import KLLError, KLLSketch


def uniform(n, seed=0):
    rnd = random.Random(seed)
    return [rnd.random() for _ in range(n)]


def rank_error(sketch, data_sorted, phi):
    est = sketch.query(phi)
    true_rank = bisect.bisect_right(data_sorted, est)
    return abs(true_rank - phi * len(data_sorted))


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_and_count():
    s = KLLSketch()
    for x in [1, 2, 3]:
        s.update(x)
    assert s.count() == 3


def test_update_many_returns_count():
    s = KLLSketch()
    assert s.update_many(range(100)) == 100


def test_query_returns_value():
    s = KLLSketch()
    s.update_many(range(500))
    assert s.query(0.5) is not None


def test_query_empty_returns_none():
    assert KLLSketch().query(0.5) is None


def test_len_tracks_n():
    s = KLLSketch()
    s.update_many(range(300))
    assert len(s) == 300


# ── quantile correctness ─────────────────────────────────────────────────────────

def test_median_accuracy():
    s = KLLSketch(k=200, seed=0)
    data = uniform(10_000)
    s.update_many(data)
    assert abs(s.query(0.5) - 0.5) <= 3 * 0.5 / 200 + 0.02


def test_all_quantiles_within_rank_error():
    k, n = 200, 10_000
    s = KLLSketch(k=k, seed=0)
    data = uniform(n, seed=1)
    s.update_many(data)
    sd = sorted(data)
    for phi in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0):
        assert rank_error(s, sd, phi) <= 3 * n / k


def test_rank_error_on_sorted_input():
    k, n = 200, 10_000
    s = KLLSketch(k=k, seed=2)
    s.update_many(range(n))                  # adversarial ascending stream
    sd = list(range(n))
    for phi in (0.2, 0.5, 0.8):
        assert rank_error(s, sd, phi) <= 3 * n / k


def test_monotonicity():
    s = KLLSketch(k=200, seed=3)
    s.update_many(uniform(8000, seed=4))
    ests = [s.query(p / 100) for p in range(101)]
    assert all(ests[i] <= ests[i + 1] + 1e-12 for i in range(len(ests) - 1))


def test_single_value():
    s = KLLSketch()
    s.update(42.0)
    assert s.query(0.0) == 42.0 and s.query(0.5) == 42.0 and s.query(1.0) == 42.0


def test_known_sequence_median():
    s = KLLSketch(k=200, seed=0)
    s.update_many(range(1, 1001))
    assert abs(s.query(0.5) - 500) <= 3 * 1000 / 200 + 5


def test_rank_function_bounds():
    s = KLLSketch(k=200, seed=0)
    data = uniform(5000)
    s.update_many(data)
    sd = sorted(data)
    assert s.rank(sd[0] - 1) == 0
    assert s.rank(sd[-1]) == 5000              # weighted rank of the max == n


def test_rank_is_monotone():
    s = KLLSketch(k=200, seed=0)
    s.update_many(uniform(5000))
    assert s.rank(0.2) <= s.rank(0.5) <= s.rank(0.8)


# ── merge (the defining feature) ─────────────────────────────────────────────────

def test_merge_median():
    k = 200
    data = uniform(10_000, seed=5)
    a = KLLSketch(k=k, seed=1)
    b = KLLSketch(k=k, seed=2)
    a.update_many(data[:5000])
    b.update_many(data[5000:])
    a.merge(b)
    assert abs(a.query(0.5) - 0.5) <= 3 * 0.5 / k + 0.02


def test_merge_combines_counts():
    a = KLLSketch(k=200)
    b = KLLSketch(k=200)
    a.update_many(range(3000))
    b.update_many(range(3000, 7000))
    a.merge(b)
    assert a.count() == 7000


def test_merge_preserves_rank_error():
    k, n = 200, 10_000
    data = uniform(n, seed=6)
    a = KLLSketch(k=k, seed=1)
    b = KLLSketch(k=k, seed=2)
    a.update_many(data[: n // 2])
    b.update_many(data[n // 2:])
    a.merge(b)
    sd = sorted(data)
    for phi in (0.25, 0.5, 0.75):
        assert rank_error(a, sd, phi) <= 3 * n / k


def test_merge_empty_into_populated():
    a = KLLSketch(k=200, seed=0)
    a.update_many(uniform(2000))
    before = a.query(0.5)
    a.merge(KLLSketch(k=200))
    assert a.count() == 2000 and a.query(0.5) == before


def test_merge_non_kll_raises():
    with pytest.raises(KLLError):
        KLLSketch().merge("not a sketch")


# ── space / levels / invariants ──────────────────────────────────────────────────

def test_space_ratio_below_threshold():
    s = KLLSketch(k=200, seed=0)
    s.update_many(uniform(10_000, seed=2))
    assert s.stats()["sketch_size_ratio"] < 0.1


def test_num_levels_grows_with_n():
    s = KLLSketch(k=200, seed=0)
    s.update_many(uniform(10_000))
    assert s.stats()["num_levels"] > 1


def test_small_n_stays_single_level():
    s = KLLSketch(k=200)
    s.update_many(range(50))                 # below k → no compaction yet
    assert s.num_levels == 1


def test_weight_invariant_sum_equals_n():
    s = KLLSketch(k=200, seed=0)
    s.update_many(uniform(7000, seed=3))
    total = sum(w for _v, w in s._weighted_items_locked())
    assert total == 7000 == s.count()


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_seed():
    a = KLLSketch(k=200, seed=7)
    b = KLLSketch(k=200, seed=7)
    data = uniform(8000, seed=1)
    a.update_many(data)
    b.update_many(data)
    assert a._levels == b._levels
    assert all(a.query(p / 10) == b.query(p / 10) for p in range(11))


def test_different_seed_still_accurate():
    data = uniform(10_000, seed=8)
    a = KLLSketch(k=200, seed=1)
    b = KLLSketch(k=200, seed=2)
    a.update_many(data)
    b.update_many(data)
    assert abs(a.query(0.5) - 0.5) <= 0.03 and abs(b.query(0.5) - 0.5) <= 0.03


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_k():
    assert KLLSketch().k == 200


def test_configurable_k():
    assert KLLSketch(k=64).k == 64


def test_k_two_edge_works():
    s = KLLSketch(k=2, seed=0)
    s.update_many(range(1000))
    assert s.query(0.5) is not None and s.stats()["num_levels"] > 1


def test_invalid_k_zero_raises():
    with pytest.raises(KLLError):
        KLLSketch(k=0)


def test_invalid_k_one_raises():
    with pytest.raises(KLLError):
        KLLSketch(k=1)


def test_invalid_k_bool_raises():
    with pytest.raises(KLLError):
        KLLSketch(k=True)


def test_invalid_k_float_raises():
    with pytest.raises(KLLError):
        KLLSketch(k=2.5)


def test_invalid_seed_float_raises():
    with pytest.raises(KLLError):
        KLLSketch(k=200, seed=1.5)


def test_update_non_number_raises():
    with pytest.raises(KLLError):
        KLLSketch().update("not a number")


def test_query_invalid_phi_low_raises():
    s = KLLSketch()
    s.update(1)
    with pytest.raises(KLLError):
        s.query(-0.1)


def test_query_invalid_phi_high_raises():
    s = KLLSketch()
    s.update(1)
    with pytest.raises(KLLError):
        s.query(1.1)


def test_kll_error_stores_detail():
    err = KLLError(-3)
    assert err.detail == -3
    assert "invalid kll sketch configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(KLLSketch().stats()) == {
        "k", "n", "num_levels", "num_compactors", "sketch_size_ratio",
    }


def test_stats_initial():
    s = KLLSketch(k=128).stats()
    assert s == {"k": 128, "n": 0, "num_levels": 1, "num_compactors": 0,
                 "sketch_size_ratio": 0.0}


def test_stats_tracks_n():
    s = KLLSketch()
    s.update_many(range(456))
    assert s.stats()["n"] == 456


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = KLLSketch()
    s.update_many(range(1000))
    s.reset()
    assert s.count() == 0 and s.query(0.5) is None and s.num_levels == 1


def test_reset_reconfigures_k():
    s = KLLSketch(k=200)
    s.reset(k=64)
    assert s.k == 64


def test_reset_then_reuse():
    s = KLLSketch(k=200, seed=0)
    s.update_many(range(500))
    s.reset()
    s.update_many(range(1, 1001))
    assert abs(s.query(0.5) - 500) <= 3 * 1000 / 200 + 5


# ── edge cases & concurrency ─────────────────────────────────────────────────────

def test_duplicate_values():
    s = KLLSketch(k=50)
    s.update_many([7.0] * 500 + [3.0] * 500)
    assert s.query(0.25) == 3.0 and s.query(0.75) == 7.0


def test_negative_and_float_values():
    s = KLLSketch(k=200, seed=0)
    s.update_many([-100.5, -50.0, 0.0, 50.0, 100.5] * 400)
    assert s.query(0.5) == 0.0


def test_concurrent_updates_10_threads():
    s = KLLSketch(k=200, seed=0)
    errors = []

    def worker(tag):
        try:
            for i in range(300):
                s.update(tag * 10_000 + i)
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert s.count() == 3000
    assert s.query(0.5) is not None
