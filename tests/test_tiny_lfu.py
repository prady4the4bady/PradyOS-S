"""Phase 116 — unit tests for TinyLFU (pradyos/core/tiny_lfu.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.tiny_lfu import TinyLFU, TinyLFUError


# ── frequency estimation ─────────────────────────────────────────────────────────

def test_isolated_estimate_exact():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    for _ in range(200):
        t.add("hot")
    assert t.estimate("hot") == 200          # below byte saturation


def test_byte_counter_saturates():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    for _ in range(1000):
        t.add("vhot")
    assert t.estimate("vhot") == 256         # 255 (counter) + 1 (doorkeeper)


def test_estimate_one_sided():
    t = TinyLFU(sample_size=1_000_000, width=2048, depth=4, seed=1)
    truth = {}
    rng = random.Random(3)
    for _ in range(10000):
        k = f"k{rng.randrange(2000)}"
        t.add(k)
        truth[k] = truth.get(k, 0) + 1
    assert all(t.estimate(k) >= c for k, c in truth.items())


def test_estimate_never_added_is_zero():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    assert t.estimate("never") == 0


# ── doorkeeper ───────────────────────────────────────────────────────────────────

def test_one_hit_estimate_is_one():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    t.add("once")
    assert t.estimate("once") == 1


def test_one_hit_leaves_countmin_zero():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    t.add("once")
    assert all(c == 0 for c in t._counters)   # singleton absorbed by doorkeeper


def test_second_access_touches_countmin():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    t.add("k")
    t.add("k")
    assert any(c > 0 for c in t._counters) and t.estimate("k") == 2


# ── admission ────────────────────────────────────────────────────────────────────

def test_hot_beats_cold():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    for _ in range(100):
        t.add("popular")
    for _ in range(3):
        t.add("rare")
    assert t.estimate("popular") > t.estimate("rare")


def test_admit_true_for_more_frequent():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    for _ in range(50):
        t.add("hot")
    t.add("cold")
    t.add("cold")
    assert t.admit("hot", "cold") is True


def test_admit_false_for_less_frequent():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    for _ in range(50):
        t.add("hot")
    t.add("cold")
    assert t.admit("cold", "hot") is False


# ── aging / reset ─────────────────────────────────────────────────────────────────

def test_aging_decays_frequency():
    t = TinyLFU(sample_size=200, width=512, depth=4, seed=0)
    for _ in range(60):
        t.add("x")
    before = t.estimate("x")
    for i in range(800):
        t.add(f"flood-{i}")
    assert t.estimate("x") < before


def test_reset_count_tracks_total():
    t = TinyLFU(sample_size=100, width=256, depth=4, seed=0)
    for i in range(350):
        t.add(f"a{i}")
    assert t.resets == 3 and t.total == 350


def test_age_halves_counters():
    t = TinyLFU(sample_size=100, width=256, depth=4, seed=0)
    for _ in range(50):
        t.add("x")                # estimate ~50
    est_before = t.estimate("x")
    for i in range(50):           # reach sample_size=100 -> one reset
        t.add(f"f{i}")
    assert t.resets == 1
    # x's counter halved; doorkeeper cleared by the reset.
    assert t.estimate("x") <= est_before // 2 + 1


def test_accesses_since_reset_tracked():
    t = TinyLFU(sample_size=1000, width=256, depth=4, seed=0)
    for i in range(40):
        t.add(f"k{i}")
    assert t.stats()["accesses_since_reset"] == 40


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic_estimates():
    a = TinyLFU(sample_size=100000, width=1024, depth=4, seed=5)
    b = TinyLFU(sample_size=100000, width=1024, depth=4, seed=5)
    rng = random.Random(9)
    seq = [f"k{rng.randrange(500)}" for _ in range(5000)]
    for k in seq:
        a.add(k)
        b.add(k)
    assert a._counters == b._counters
    assert all(a.estimate(f"k{i}") == b.estimate(f"k{i}") for i in range(500))


def test_total_counts_accesses():
    t = TinyLFU(sample_size=1_000_000, seed=0)
    for _ in range(123):
        t.add("z")
    assert t.total == 123


# ── configuration & validation ──────────────────────────────────────────────────

def test_width_defaults_to_sample_size():
    assert TinyLFU(sample_size=512).width == 512


def test_explicit_width():
    assert TinyLFU(sample_size=512, width=2048).width == 2048


def test_invalid_sample_size_raises():
    with pytest.raises(TinyLFUError):
        TinyLFU(sample_size=0)


def test_invalid_width_raises():
    with pytest.raises(TinyLFUError):
        TinyLFU(sample_size=100, width=0)


def test_invalid_depth_raises():
    with pytest.raises(TinyLFUError):
        TinyLFU(sample_size=100, depth=0)


def test_invalid_seed_raises():
    with pytest.raises(TinyLFUError):
        TinyLFU(sample_size=100, seed="nope")


def test_bool_sample_size_rejected():
    with pytest.raises(TinyLFUError):
        TinyLFU(sample_size=True)


def test_bool_seed_rejected():
    with pytest.raises(TinyLFUError):
        TinyLFU(sample_size=100, seed=True)


def test_error_stores_detail():
    err = TinyLFUError(-9)
    assert err.detail == -9 and "-9" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    t = TinyLFU(sample_size=500, width=1024, depth=5, seed=7)
    assert t.sample_size == 500 and t.width == 1024 and t.depth == 5 and t.seed == 7


def test_resets_initial_zero():
    assert TinyLFU(sample_size=100, seed=0).resets == 0


def test_stats_keys():
    assert set(TinyLFU(sample_size=100, seed=0).stats()) == {
        "sample_size", "width", "depth", "doorkeeper_bits", "total",
        "accesses_since_reset", "resets", "seed"}


def test_stats_values():
    t = TinyLFU(sample_size=256, width=512, depth=4, seed=3)
    for _ in range(10):
        t.add("k")
    s = t.stats()
    assert s["sample_size"] == 256 and s["width"] == 512 and s["depth"] == 4
    assert s["total"] == 10 and s["doorkeeper_bits"] >= 1 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    t = TinyLFU(sample_size=1_000_000, width=512, depth=4, seed=0)
    for _ in range(50):
        t.add("k")
    t.reset()
    assert t.total == 0 and t.resets == 0 and t.estimate("k") == 0


def test_reset_reconfigures():
    t = TinyLFU(sample_size=500, width=512, depth=4, seed=0)
    t.reset(sample_size=1000, width=2048, depth=5, seed=9)
    assert t.sample_size == 1000 and t.width == 2048 and t.depth == 5 and t.seed == 9


def test_reset_invalid_raises():
    t = TinyLFU(sample_size=100, seed=0)
    with pytest.raises(TinyLFUError):
        t.reset(sample_size=0)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(200):
                t.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == []
    assert t.total == 2000
