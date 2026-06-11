"""Phase 96 — unit tests for DDSketch (pradyos/core/ddsketch.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.ddsketch import DDSketch, DDSketchError


def uniform(n, lo=1.0, hi=1000.0, seed=0):
    rnd = random.Random(seed)
    return [rnd.uniform(lo, hi) for _ in range(n)]


def true_quantile(sorted_data, q):
    idx = min(len(sorted_data) - 1, max(0, math.ceil(q * len(sorted_data)) - 1))
    return sorted_data[idx]


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_and_count():
    s = DDSketch()
    for v in [1, 2, 3]:
        s.update(v)
    assert s.count() == 3


def test_quantile_empty_is_none():
    assert DDSketch().quantile(0.5) is None


def test_len_tracks_n():
    s = DDSketch()
    s.update(5, 4)
    assert len(s) == 4


def test_num_buckets_grows():
    s = DDSketch(alpha=0.01)
    s.update(1)
    s.update(1000)
    assert s.num_buckets == 2


# ── quantile accuracy / relative error ───────────────────────────────────────────

def test_uniform_median_within_alpha():
    alpha = 0.01
    s = DDSketch(alpha=alpha)
    data = uniform(10_000)
    for v in data:
        s.update(v)
    sd = sorted(data)
    est, tru = s.quantile(0.5), true_quantile(sd, 0.5)
    assert abs(est - tru) / tru <= alpha


def test_uniform_p99_within_alpha():
    alpha = 0.01
    s = DDSketch(alpha=alpha)
    data = uniform(10_000)
    for v in data:
        s.update(v)
    sd = sorted(data)
    est, tru = s.quantile(0.99), true_quantile(sd, 0.99)
    assert abs(est - tru) / tru <= alpha


def test_all_quantile_levels_within_alpha():
    alpha = 0.01
    s = DDSketch(alpha=alpha)
    data = uniform(10_000, seed=3)
    for v in data:
        s.update(v)
    sd = sorted(data)
    for q in (0.1, 0.25, 0.5, 0.75, 0.99):
        est, tru = s.quantile(q), true_quantile(sd, q)
        assert abs(est - tru) / tru <= alpha


def test_exponential_range_median():
    alpha = 0.01
    s = DDSketch(alpha=alpha)
    for v in range(1, 10_001):
        s.update(v)
    est = s.quantile(0.5)
    assert abs(est - 5000) / 5000 <= alpha


def test_single_value_within_alpha():
    s = DDSketch(alpha=0.01)
    s.update(42.0)
    assert abs(s.quantile(0.5) - 42.0) / 42.0 <= 0.01


def test_quantile_with_count():
    s = DDSketch(alpha=0.01)
    s.update(100.0, 5000)
    assert abs(s.quantile(0.5) - 100.0) / 100.0 <= 0.01


def test_monotonicity():
    s = DDSketch(alpha=0.01)
    for v in uniform(8000, seed=4):
        s.update(v)
    ests = [s.quantile(q / 100) for q in range(101)]
    assert all(ests[i] <= ests[i + 1] * (1 + 1e-9) for i in range(len(ests) - 1))


def test_quantile_extremes_within_alpha():
    alpha = 0.01
    s = DDSketch(alpha=alpha)
    data = uniform(5000, seed=5)
    for v in data:
        s.update(v)
    assert abs(s.quantile(0.0) - min(data)) / min(data) <= alpha
    assert abs(s.quantile(1.0) - max(data)) / max(data) <= alpha


# ── merge (the key differentiator) ───────────────────────────────────────────────

def test_merge_combines_counts():
    a = DDSketch(alpha=0.01)
    b = DDSketch(alpha=0.01)
    for v in range(1, 3001):
        a.update(v)
    for v in range(3001, 7001):
        b.update(v)
    a.merge(b)
    assert a.count() == 7000


def test_merge_is_exact_vs_single_sketch():
    alpha = 0.01
    data = uniform(10_000, seed=6)
    a = DDSketch(alpha=alpha)
    b = DDSketch(alpha=alpha)
    whole = DDSketch(alpha=alpha)
    for v in data[:5000]:
        a.update(v)
    for v in data[5000:]:
        b.update(v)
    for v in data:
        whole.update(v)
    a.merge(b)
    # exact bucket-count union → identical quantiles to the single sketch
    for q in (0.25, 0.5, 0.75, 0.99):
        assert a.quantile(q) == whole.quantile(q)


def test_merge_preserves_relative_error():
    alpha = 0.01
    data = uniform(10_000, seed=7)
    a = DDSketch(alpha=alpha)
    b = DDSketch(alpha=alpha)
    for v in data[:5000]:
        a.update(v)
    for v in data[5000:]:
        b.update(v)
    a.merge(b)
    sd = sorted(data)
    for q in (0.25, 0.5, 0.75):
        assert abs(a.quantile(q) - true_quantile(sd, q)) / true_quantile(sd, q) <= alpha


def test_merge_alpha_mismatch_raises():
    with pytest.raises(DDSketchError):
        DDSketch(alpha=0.01).merge(DDSketch(alpha=0.02))


def test_merge_non_ddsketch_raises():
    with pytest.raises(DDSketchError):
        DDSketch().merge("not a sketch")


def test_merge_empty_into_populated():
    a = DDSketch(alpha=0.01)
    for v in uniform(2000):
        a.update(v)
    before = a.quantile(0.5)
    a.merge(DDSketch(alpha=0.01))
    assert a.count() == 2000 and a.quantile(0.5) == before


def test_merge_updates_min_max():
    a = DDSketch(alpha=0.01)
    b = DDSketch(alpha=0.01)
    a.update(50.0)
    b.update(5.0)
    b.update(500.0)
    a.merge(b)
    assert a.stats()["min"] == 5.0 and a.stats()["max"] == 500.0


# ── non-positive value guard ─────────────────────────────────────────────────────

def test_update_zero_raises():
    with pytest.raises(DDSketchError):
        DDSketch().update(0)


def test_update_negative_raises():
    with pytest.raises(DDSketchError):
        DDSketch().update(-1)


def test_positive_required_message():
    with pytest.raises(DDSketchError, match="positive"):
        DDSketch().update(-0.5)


def test_update_invalid_count_raises():
    with pytest.raises(DDSketchError):
        DDSketch().update(10, 0)
    with pytest.raises(DDSketchError):
        DDSketch().update(10, 1.5)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_seed_ignored():
    a = DDSketch(alpha=0.01, seed=1)
    b = DDSketch(alpha=0.01, seed=999)
    for v in uniform(3000, seed=2):
        a.update(v)
        b.update(v)
    assert a._buckets == b._buckets


def test_deterministic_quantiles():
    a = DDSketch(alpha=0.01)
    b = DDSketch(alpha=0.01)
    data = uniform(4000, seed=8)
    for v in data:
        a.update(v)
        b.update(v)
    assert all(a.quantile(q / 10) == b.quantile(q / 10) for q in range(11))


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_alpha():
    assert DDSketch().alpha == 0.01


def test_configurable_alpha():
    assert DDSketch(alpha=0.05).alpha == 0.05


def test_gamma_formula():
    s = DDSketch(alpha=0.01)
    assert s.gamma == pytest.approx((1 + 0.01) / (1 - 0.01))


def test_invalid_alpha_zero_raises():
    with pytest.raises(DDSketchError):
        DDSketch(alpha=0.0)


def test_invalid_alpha_one_raises():
    with pytest.raises(DDSketchError):
        DDSketch(alpha=1.0)


def test_invalid_alpha_negative_raises():
    with pytest.raises(DDSketchError):
        DDSketch(alpha=-0.1)


def test_invalid_alpha_bool_raises():
    with pytest.raises(DDSketchError):
        DDSketch(alpha=True)


def test_quantile_invalid_q_low_raises():
    s = DDSketch()
    s.update(1)
    with pytest.raises(DDSketchError):
        s.quantile(-0.1)


def test_quantile_invalid_q_high_raises():
    s = DDSketch()
    s.update(1)
    with pytest.raises(DDSketchError):
        s.quantile(1.1)


def test_ddsketch_error_stores_detail():
    err = DDSketchError(-3)
    assert err.detail == -3
    assert "invalid ddsketch operation" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(DDSketch().stats()) == {"alpha", "gamma", "n", "num_buckets", "min", "max"}


def test_stats_initial():
    s = DDSketch(alpha=0.02).stats()
    assert s["n"] == 0 and s["num_buckets"] == 0 and s["min"] is None and s["max"] is None


def test_stats_tracks_min_max():
    s = DDSketch(alpha=0.01)
    s.update(7.0)
    s.update(700.0)
    s.update(70.0)
    st = s.stats()
    assert st["min"] == 7.0 and st["max"] == 700.0 and st["n"] == 3


def test_num_buckets_sublinear():
    s = DDSketch(alpha=0.01)
    for v in uniform(10_000, seed=9):
        s.update(v)
    assert s.num_buckets < 1000          # logarithmic bucketing ⇒ ≪ n


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = DDSketch(alpha=0.01)
    for v in uniform(1000):
        s.update(v)
    s.reset()
    assert s.count() == 0 and s.quantile(0.5) is None and s.num_buckets == 0


def test_reset_reconfigures_alpha():
    s = DDSketch(alpha=0.01)
    s.reset(alpha=0.05)
    assert s.alpha == 0.05


def test_reset_then_reuse():
    s = DDSketch(alpha=0.01)
    s.update(5.0)
    s.reset()
    for v in range(1, 1001):
        s.update(v)
    assert abs(s.quantile(0.5) - 500) / 500 <= 0.01


# ── value range & concurrency ────────────────────────────────────────────────────

def test_float_values():
    s = DDSketch(alpha=0.01)
    for v in [0.5, 1.5, 2.5, 3.5]:           # positive floats below and above 1
        s.update(v)
    assert s.quantile(0.5) > 0


def test_wide_value_range():
    alpha = 0.01
    s = DDSketch(alpha=alpha)
    data = [float(10 ** e) for e in range(7) for _ in range(100)]   # 1 .. 1e6
    for v in data:
        s.update(v)
    sd = sorted(data)
    est, tru = s.quantile(0.5), true_quantile(sd, 0.5)
    assert abs(est - tru) / tru <= alpha


def test_concurrent_updates_10_threads():
    s = DDSketch(alpha=0.01)
    errors = []

    def worker(tag):
        try:
            for _ in range(300):
                s.update(100.0)
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert s.count() == 3000
    assert abs(s.quantile(0.5) - 100.0) / 100.0 <= 0.01
