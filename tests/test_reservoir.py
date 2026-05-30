"""Phase 85 — unit tests for SovereignReservoir (Algorithm R)."""
from __future__ import annotations

import random
import threading
from collections import Counter

import pytest

from pradyos.core.reservoir import ReservoirError, SovereignReservoir


# ── construction ──────────────────────────────────────────────────────────────

def test_construction_capacity():
    assert SovereignReservoir(10).capacity == 10


def test_invalid_capacity_raises():
    for bad in (0, -1, 2.5, "x"):
        with pytest.raises(ReservoirError):
            SovereignReservoir(bad)


def test_reservoir_error_carries_capacity():
    try:
        SovereignReservoir(0)
    except ReservoirError as exc:
        assert exc.capacity == 0
        assert "0" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected ReservoirError")


# ── fill behaviour ────────────────────────────────────────────────────────────

def test_fewer_than_k_holds_all():
    r = SovereignReservoir(10)
    for i in range(4):
        r.feed(i)
    assert sorted(r.sample()) == [0, 1, 2, 3]


def test_exactly_k_holds_all():
    r = SovereignReservoir(5)
    for i in range(5):
        r.feed(i)
    assert sorted(r.sample()) == [0, 1, 2, 3, 4]
    assert len(r) == 5


def test_more_than_k_holds_exactly_k():
    r = SovereignReservoir(3)
    for i in range(100):
        r.feed(i)
    assert len(r) == 3
    assert r.seen == 100


def test_seen_counter():
    r = SovereignReservoir(2)
    for _ in range(7):
        r.feed("x")
    assert r.seen == 7


# ── sample / stats ────────────────────────────────────────────────────────────

def test_sample_is_a_copy():
    r = SovereignReservoir(3)
    r.feed(1)
    snap = r.sample()
    snap.append(999)
    assert r.sample() == [1]


def test_sample_size_never_exceeds_k():
    r = SovereignReservoir(5)
    for i in range(50):
        r.feed(i)
    assert len(r.sample()) <= 5


def test_empty_sample():
    assert SovereignReservoir(5).sample() == []


def test_stats_keys_and_values():
    r = SovereignReservoir(4)
    for i in range(10):
        r.feed(i)
    stats = r.stats()
    assert set(stats) == {"capacity", "seen", "filled"}
    assert stats["capacity"] == 4
    assert stats["seen"] == 10
    assert stats["filled"] == 4


def test_len_and_properties():
    r = SovereignReservoir(8)
    for i in range(3):
        r.feed(i)
    assert len(r) == 3
    assert r.capacity == 8
    assert r.seen == 3


# ── deterministic Algorithm R (injected RNG) ──────────────────────────────────

def test_deterministic_replacement():
    seq = iter([0.0, 0.99, 0.0])    # decisions for items at i=3,4,5
    r = SovereignReservoir(3, random_fn=lambda: next(seq))
    for i in range(3):
        r.feed(i)                    # reservoir = [0, 1, 2]
    r.feed(3)                        # j=int(0.0*4)=0 < 3 → [3,1,2]
    r.feed(4)                        # j=int(0.99*5)=4 ≥ 3 → unchanged
    r.feed(5)                        # j=int(0.0*6)=0 < 3 → [5,1,2]
    assert r.sample() == [5, 1, 2]


def test_k1_always_replace():
    r = SovereignReservoir(1, random_fn=lambda: 0.0)   # j always 0 → last wins
    for i in range(10):
        r.feed(i)
    assert r.sample() == [9]


def test_k1_never_replace():
    r = SovereignReservoir(1, random_fn=lambda: 0.999)  # j always out of bounds
    for i in range(10):
        r.feed(i)
    assert r.sample() == [0]


# ── statistical uniformity ────────────────────────────────────────────────────

def test_uniformity_over_many_trials():
    n, k, trials = 100, 10, 3000
    rng = random.Random(12345)
    counts: Counter = Counter()
    for _ in range(trials):
        r = SovereignReservoir(k, random_fn=rng.random)
        for i in range(n):
            r.feed(i)
        counts.update(r.sample())
    expected = trials * k / n        # 300
    assert len(counts) == n          # every item selected at least once
    assert all(0.6 * expected <= c <= 1.4 * expected for c in counts.values())


def test_every_item_can_be_sampled():
    # with k == n the whole stream is the reservoir
    r = SovereignReservoir(20)
    for i in range(20):
        r.feed(i)
    assert sorted(r.sample()) == list(range(20))


# ── reset ─────────────────────────────────────────────────────────────────────

def test_reset_clears_stream():
    r = SovereignReservoir(5)
    for i in range(20):
        r.feed(i)
    r.reset()
    assert r.seen == 0
    assert r.sample() == []
    assert r.capacity == 5


def test_reset_mid_stream_then_feed():
    r = SovereignReservoir(3)
    for i in range(10):
        r.feed(i)
    r.reset()
    for i in range(2):
        r.feed(i)
    assert sorted(r.sample()) == [0, 1]
    assert r.seen == 2


def test_reset_resizes_capacity():
    r = SovereignReservoir(5)
    r.reset(k=3)
    assert r.capacity == 3


def test_reset_invalid_capacity_raises():
    with pytest.raises(ReservoirError):
        SovereignReservoir(5).reset(0)


# ── feed_many / heterogeneous items ───────────────────────────────────────────

def test_feed_many_returns_count_and_fills():
    r = SovereignReservoir(50)
    fed = r.feed_many(range(30))
    assert fed == 30
    assert len(r) == 30


def test_feed_many_respects_capacity():
    r = SovereignReservoir(5)
    r.feed_many(range(100))
    assert len(r) == 5
    assert r.seen == 100


def test_arbitrary_item_types():
    r = SovereignReservoir(10)
    r.feed("str"); r.feed({"a": 1}); r.feed((1, 2))
    assert len(r) == 3
    assert {"a": 1} in r.sample()


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_feed_is_thread_safe():
    r = SovereignReservoir(50)
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(1000):
                r.feed((base, i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert r.seen == 10 * 1000          # every feed counted under the lock
    assert len(r.sample()) == 50        # reservoir never exceeds k


# ── extra coverage ────────────────────────────────────────────────────────────

def test_reset_resize_larger_keeps_emptied():
    r = SovereignReservoir(3)
    for i in range(10):
        r.feed(i)
    r.reset(k=20)
    assert r.capacity == 20
    assert r.sample() == []


def test_filled_is_min_seen_capacity():
    r = SovereignReservoir(7)
    for i in range(3):
        r.feed(i)
    assert r.stats()["filled"] == 3      # seen < capacity
    for i in range(3, 20):
        r.feed(i)
    assert r.stats()["filled"] == 7      # seen >= capacity


def test_capacity_one_holds_single_slot():
    r = SovereignReservoir(1)
    for i in range(50):
        r.feed(i)
    assert len(r) == 1


def test_feed_reset_resize_then_feed():
    r = SovereignReservoir(10)
    r.feed_many(range(5))
    r.reset(k=2)
    r.feed_many(range(3))
    assert len(r) == 2
    assert r.seen == 3


def test_repeated_sample_is_consistent():
    r = SovereignReservoir(3)
    r.feed_many(range(3))
    a, b = r.sample(), r.sample()
    assert a == b
    assert a is not b                    # distinct list objects


def test_default_rng_runs_without_error():
    r = SovereignReservoir(20)            # uses random.random
    for i in range(500):
        r.feed(i)
    assert len(r) == 20
    assert r.seen == 500


def test_k1_uniformity():
    n, trials = 50, 2000
    rng = random.Random(99)
    counts: Counter = Counter()
    for _ in range(trials):
        r = SovereignReservoir(1, random_fn=rng.random)
        for i in range(n):
            r.feed(i)
        counts.update(r.sample())
    expected = trials / n                 # 40 per item
    assert len(counts) == n
    assert all(0.5 * expected <= c <= 1.5 * expected for c in counts.values())
