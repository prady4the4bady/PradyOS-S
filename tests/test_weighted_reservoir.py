"""Phase 98 — unit tests for WeightedReservoir (pradyos/core/weighted_reservoir.py)."""
from __future__ import annotations

import threading
from collections import Counter

import pytest

from pradyos.core.weighted_reservoir import WeightedReservoir, WeightedReservoirError


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_tracks_n():
    wr = WeightedReservoir(5)
    wr.update("a")
    wr.update("b")
    assert wr.n == 2


def test_sample_empty_is_list():
    assert WeightedReservoir(5).sample() == []


def test_len_tracks_n():
    wr = WeightedReservoir(5)
    for i in range(7):
        wr.update(i)
    assert len(wr) == 7


def test_size_property():
    wr = WeightedReservoir(3)
    for i in range(10):
        wr.update(i)
    assert wr.size == 3


# ── capacity / sampling ──────────────────────────────────────────────────────────

def test_capacity_fills_to_k():
    wr = WeightedReservoir(50, seed=0)
    for i in range(10_000):
        wr.update(f"x{i}")
    assert len(wr.sample()) == 50


def test_under_capacity_keeps_all():
    wr = WeightedReservoir(50, seed=0)
    for i in range(30):
        wr.update(f"y{i}")
    assert len(wr.sample()) == 30


def test_exactly_k_items():
    wr = WeightedReservoir(10, seed=0)
    for i in range(10):
        wr.update(i)
    assert len(wr.sample()) == 10


def test_single_item():
    wr = WeightedReservoir(5)
    wr.update("solo")
    assert wr.sample() == ["solo"]


def test_sample_items_are_from_stream():
    wr = WeightedReservoir(5, seed=0)
    streamed = set(range(100))
    for i in streamed:
        wr.update(i)
    assert set(wr.sample()).issubset(streamed)


# ── weight-proportional bias ─────────────────────────────────────────────────────

def test_high_weight_dominates():
    freq = Counter()
    for trial in range(2000):
        wr = WeightedReservoir(10, seed=trial)
        for i in range(1, 101):
            wr.update(i, weight=i)
        freq.update(wr.sample())
    assert freq[100] > freq[1] * 10            # weight 100 vs weight 1


def test_top_selected_are_high_weight():
    freq = Counter()
    for trial in range(2000):
        wr = WeightedReservoir(10, seed=trial)
        for i in range(1, 101):
            wr.update(i, weight=i)
        freq.update(wr.sample())
    top10 = [it for it, _ in freq.most_common(10)]
    assert all(it >= 81 for it in top10)       # all from the top-20 by weight


def test_uniform_weights_roughly_unbiased():
    freq = Counter()
    for trial in range(3000):
        wr = WeightedReservoir(10, seed=trial)
        for i in range(20):
            wr.update(i, weight=1.0)
        freq.update(wr.sample())
    # equal weights ⇒ comparable selection frequencies (no strong bias)
    assert 0.5 < freq[0] / freq[19] < 2.0


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_seed():
    a = WeightedReservoir(20, seed=42)
    b = WeightedReservoir(20, seed=42)
    for i in range(1000):
        a.update(f"z{i}", weight=(i % 7) + 1)
        b.update(f"z{i}", weight=(i % 7) + 1)
    assert sorted(a.sample()) == sorted(b.sample())


def test_different_seed_differs():
    a = WeightedReservoir(10, seed=1)
    b = WeightedReservoir(10, seed=2)
    for i in range(500):
        a.update(i)
        b.update(i)
    assert sorted(a.sample()) != sorted(b.sample())


def test_default_weight_is_one():
    wr = WeightedReservoir(5)
    wr.update("d")
    assert wr.sample() == ["d"] and wr.n == 1


# ── weight guard ─────────────────────────────────────────────────────────────────

def test_weight_zero_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(5).update("x", weight=0)


def test_weight_negative_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(5).update("x", weight=-1)


def test_weight_positive_message():
    with pytest.raises(WeightedReservoirError, match="weight must be positive"):
        WeightedReservoir(5).update("x", weight=-0.5)


def test_non_number_weight_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(5).update("x", weight="heavy")


# ── k / seed validation ──────────────────────────────────────────────────────────

def test_invalid_k_zero_raises():
    with pytest.raises(WeightedReservoirError, match="k must be at least 1"):
        WeightedReservoir(0)


def test_invalid_k_negative_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(-5)


def test_invalid_k_bool_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(True)


def test_invalid_k_float_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(2.5)


def test_invalid_seed_float_raises():
    with pytest.raises(WeightedReservoirError):
        WeightedReservoir(5, seed=1.5)


def test_k_one_allowed():
    wr = WeightedReservoir(1, seed=0)
    for i in range(100):
        wr.update(i)
    assert len(wr.sample()) == 1


def test_error_stores_detail():
    err = WeightedReservoirError(-3)
    assert err.detail == -3


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    wr = WeightedReservoir(10, seed=0)
    for i in range(50):
        wr.update(i)
    wr.reset()
    assert wr.sample() == [] and wr.n == 0 and wr.size == 0


def test_reset_then_refill():
    wr = WeightedReservoir(10, seed=0)
    for i in range(50):
        wr.update(i)
    wr.reset()
    for i in range(20):
        wr.update(f"new{i}")
    assert len(wr.sample()) == 10 and wr.n == 20


def test_reset_does_not_reseed_rng():
    # After reset the RNG state continues (it is NOT re-seeded), so replaying the
    # same stream yields a different sample than a fresh same-seed reservoir.
    used = WeightedReservoir(5, seed=0)
    for i in range(50):
        used.update(i)
    used.reset()
    for i in range(50):
        used.update(i)

    fresh = WeightedReservoir(5, seed=0)
    for i in range(50):
        fresh.update(i)

    assert sorted(used.sample()) != sorted(fresh.sample())


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(WeightedReservoir(5).stats()) == {"k", "n", "size", "seed"}


def test_stats_initial():
    assert WeightedReservoir(7, seed=3).stats() == {"k": 7, "n": 0, "size": 0, "seed": 3}


def test_stats_tracks():
    wr = WeightedReservoir(5, seed=0)
    for i in range(20):
        wr.update(i)
    s = wr.stats()
    assert s["n"] == 20 and s["size"] == 5 and s["k"] == 5


# ── item types & concurrency ─────────────────────────────────────────────────────

def test_arbitrary_item_types_no_comparison_error():
    # The (key, counter, item) tiebreaker means heapq never compares items, so a
    # mix of non-mutually-comparable types is safe.
    wr = WeightedReservoir(5, seed=0)
    for item in [1, "two", (3, 4), 5.0, "six", (7,), 8]:
        wr.update(item, weight=1.0)
    assert len(wr.sample()) == 5


def test_integer_items():
    wr = WeightedReservoir(3, seed=0)
    for i in range(100):
        wr.update(i)
    assert all(isinstance(x, int) for x in wr.sample())


def test_concurrent_updates_10_threads():
    wr = WeightedReservoir(20, seed=0)
    errors = []

    def worker(tag):
        try:
            for i in range(100):
                wr.update(f"t{tag}-{i}", weight=(i % 5) + 1)
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert wr.n == 1000
    assert len(wr.sample()) == 20
