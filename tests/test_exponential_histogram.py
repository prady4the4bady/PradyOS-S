"""Phase 97 — unit tests for ExponentialHistogram (pradyos/core/exponential_histogram.py)."""
from __future__ import annotations

import math
import threading
from collections import Counter

import pytest

from pradyos.core.exponential_histogram import (
    ExponentialHistogram,
    ExponentialHistogramError,
)


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_grows_buckets():
    eh = ExponentialHistogram(window=1000)
    eh.update()
    assert len(eh) >= 1


def test_count_empty_is_zero():
    assert ExponentialHistogram(window=100).count() == 0


def test_oldest_empty_is_none():
    assert ExponentialHistogram(window=100).oldest() is None


def test_now_starts_negative():
    assert ExponentialHistogram(window=100).now == -1


# ── count accuracy (within ε/2) ──────────────────────────────────────────────────

def test_dense_count_within_epsilon_half():
    eh = ExponentialHistogram(window=500, epsilon=0.5)   # the directive's scenario
    for _ in range(1000):
        eh.update()
    assert abs(eh.count() - 500) / 500 <= eh.epsilon / 2


def test_tighter_epsilon_more_accurate():
    eh = ExponentialHistogram(window=500, epsilon=0.1)
    for _ in range(1000):
        eh.update()
    assert abs(eh.count() - 500) / 500 <= eh.epsilon / 2


def test_count_below_window_within_epsilon_half():
    eh = ExponentialHistogram(window=100_000, epsilon=0.5)   # window huge → nothing expires
    for _ in range(200):
        eh.update()
    assert abs(eh.count() - 200) / 200 <= eh.epsilon / 2


def test_count_grows_then_saturates():
    eh = ExponentialHistogram(window=200, epsilon=0.2)
    for _ in range(100):
        eh.update()
    mid = eh.count()
    for _ in range(400):                       # well past the window
        eh.update()
    full = eh.count()
    assert full > mid                          # count rises toward the window size
    assert abs(full - 200) / 200 <= eh.epsilon / 2


# ── sliding / expiry ─────────────────────────────────────────────────────────────

def test_sliding_expiry():
    eh = ExponentialHistogram(window=500, epsilon=0.2)
    for i in range(200):
        eh.update(timestamp=i)                 # ticks 0..199
    for i in range(100):
        eh.update(timestamp=800 + i)           # ticks 800..899 (gap 200..799)
    assert abs(eh.count() - 100) / 100 <= eh.epsilon / 2 + 0.05


def test_old_buckets_expire():
    eh = ExponentialHistogram(window=100, epsilon=0.2)
    for _ in range(1000):
        eh.update()
    assert abs(eh.count() - 100) / 100 <= eh.epsilon / 2


def test_expiry_invariant():
    eh = ExponentialHistogram(window=300, epsilon=0.5)
    for _ in range(2000):
        eh.update()
    cutoff = eh.now - eh.window
    assert all(b[0] > cutoff for b in eh._buckets)


def test_oldest_advances_as_window_slides():
    eh = ExponentialHistogram(window=100, epsilon=0.5)
    for _ in range(150):
        eh.update()
    o1 = eh.oldest()
    for _ in range(150):
        eh.update()
    assert eh.oldest() > o1                     # the oldest surviving bucket moves forward


# ── merge invariant / structure / space ──────────────────────────────────────────

def test_merge_invariant_buckets_per_size():
    eh = ExponentialHistogram(window=100_000, epsilon=0.3)   # k=4
    worst = 0
    for _ in range(5000):
        eh.update()
        worst = max(worst, max(Counter(b[1] for b in eh._buckets).values()))
    assert worst <= eh.k + 1


def test_bucket_sizes_are_powers_of_two():
    eh = ExponentialHistogram(window=100_000, epsilon=0.3)
    for _ in range(3000):
        eh.update()
    for _ts, size in eh._buckets:
        assert size & (size - 1) == 0          # power of two


def test_space_is_polylog():
    eh = ExponentialHistogram(window=10_000, epsilon=0.1)
    for _ in range(5000):
        eh.update()
    bound = (1 / 0.1) * (math.log2(10_000) ** 2)
    assert eh.num_buckets < bound and eh.num_buckets < 200


# ── oldest / now / timestamps ────────────────────────────────────────────────────

def test_oldest_returns_earliest_bucket():
    eh = ExponentialHistogram(window=1000)
    for _ in range(50):
        eh.update()
    assert eh.oldest() == min(b[0] for b in eh._buckets)


def test_now_tracks_latest_timestamp():
    eh = ExponentialHistogram(window=1000)
    eh.update(timestamp=42)
    assert eh.now == 42


def test_explicit_timestamps():
    eh = ExponentialHistogram(window=10, epsilon=0.5)
    for t in (0, 5, 9, 20):
        eh.update(timestamp=t)
    assert eh.now == 20 and eh.oldest() is not None


# ── value (bits per tick) ────────────────────────────────────────────────────────

def test_value_adds_multiple_bits():
    eh = ExponentialHistogram(window=1000, epsilon=0.1)
    eh.update(value=10)
    assert abs(eh.count() - 10) / 10 <= 0.2     # 10 one-bits at one tick


def test_default_value_is_one():
    eh = ExponentialHistogram(window=1000)
    eh.update()
    # one 1-bit at tick 0; DGIM's end-correction estimates a lone bucket as size/2.
    assert eh.now == 0 and eh.count() == 0.5


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_seed_ignored():
    a = ExponentialHistogram(window=500, epsilon=0.3, seed=1)
    b = ExponentialHistogram(window=500, epsilon=0.3, seed=999)
    for _ in range(2000):
        a.update()
        b.update()
    assert a._buckets == b._buckets and a.count() == b.count()


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_epsilon():
    assert ExponentialHistogram(window=100).epsilon == 0.5


def test_configurable():
    eh = ExponentialHistogram(window=256, epsilon=0.1)
    assert eh.window == 256 and eh.epsilon == 0.1


def test_k_is_ceil_inverse_epsilon():
    assert ExponentialHistogram(window=10, epsilon=0.1).k == 10
    assert ExponentialHistogram(window=10, epsilon=0.3).k == math.ceil(1 / 0.3)


def test_invalid_window_zero_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=0)


def test_invalid_window_negative_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=-10)


def test_invalid_window_bool_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=True)


def test_invalid_epsilon_zero_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=100, epsilon=0.0)


def test_invalid_epsilon_above_one_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=100, epsilon=1.5)


def test_epsilon_one_allowed():
    assert ExponentialHistogram(window=100, epsilon=1.0).k == 1


def test_invalid_value_zero_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=100).update(value=0)


def test_invalid_value_negative_raises():
    with pytest.raises(ExponentialHistogramError):
        ExponentialHistogram(window=100).update(value=-1)


def test_non_monotone_timestamp_raises():
    eh = ExponentialHistogram(window=100)
    eh.update(timestamp=10)
    with pytest.raises(ExponentialHistogramError):
        eh.update(timestamp=5)


def test_error_stores_detail():
    err = ExponentialHistogramError(-3)
    assert err.detail == -3
    assert "invalid exponential histogram operation" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(ExponentialHistogram(window=100).stats()) == {
        "window", "epsilon", "k", "num_buckets", "count", "oldest", "now",
    }


def test_stats_initial():
    s = ExponentialHistogram(window=256, epsilon=0.5).stats()
    assert s == {"window": 256, "epsilon": 0.5, "k": 2, "num_buckets": 0,
                 "count": 0, "oldest": None, "now": -1}


def test_stats_tracks():
    eh = ExponentialHistogram(window=1000, epsilon=0.1)
    for _ in range(500):
        eh.update()
    s = eh.stats()
    assert s["now"] == 499 and s["num_buckets"] > 0 and s["count"] > 0


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    eh = ExponentialHistogram(window=1000)
    for _ in range(500):
        eh.update()
    eh.reset()
    assert eh.count() == 0 and eh.oldest() is None and eh.now == -1


def test_reset_reconfigures_window():
    eh = ExponentialHistogram(window=1000)
    eh.reset(window=200)
    assert eh.window == 200


def test_reset_reconfigures_epsilon():
    eh = ExponentialHistogram(window=1000, epsilon=0.5)
    eh.reset(epsilon=0.1)
    assert eh.epsilon == 0.1 and eh.k == 10


def test_reset_then_reuse():
    eh = ExponentialHistogram(window=1000, epsilon=0.1)
    for _ in range(100):
        eh.update()
    eh.reset()
    for _ in range(800):
        eh.update()
    assert abs(eh.count() - 800) / 800 <= eh.epsilon / 2


# ── concurrency ──────────────────────────────────────────────────────────────────

def test_concurrent_updates_10_threads():
    eh = ExponentialHistogram(window=100_000, epsilon=0.1)
    errors = []

    def worker(tag):
        try:
            for _ in range(200):
                eh.update()
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert eh.now == 1999                      # 2000 updates → ticks 0..1999
    assert abs(eh.count() - 2000) / 2000 <= eh.epsilon / 2
