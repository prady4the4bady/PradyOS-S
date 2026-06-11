"""Phase 103 — unit tests for the Sovereign Spectral Bloom Filter (pradyos.core.spectral_bloom)."""
from __future__ import annotations

import math
import threading

import pytest

from pradyos.core.spectral_bloom import SpectralBloom, SpectralBloomError


# ── construction / sizing ───────────────────────────────────────────────────────

def test_default_params():
    sb = SpectralBloom()
    assert sb.capacity == 10000 and sb.error_rate == 0.01 and sb.seed == 0


def test_sizing_matches_bloom_formula():
    sb = SpectralBloom(capacity=10000, error_rate=0.01)
    m = math.ceil(-(10000 * math.log(0.01)) / (math.log(2) ** 2))
    k = max(1, round((m / 10000) * math.log(2)))
    assert sb.num_bits == m and sb.num_hashes == k


def test_smaller_error_rate_grows_m():
    assert SpectralBloom(error_rate=0.001).num_bits > SpectralBloom(error_rate=0.01).num_bits


def test_num_hashes_at_least_one():
    assert SpectralBloom(capacity=10, error_rate=0.5).num_hashes >= 1


def test_stats_keys():
    assert set(SpectralBloom().stats()) == {
        "capacity", "error_rate", "num_bits", "num_hashes", "num_added", "estimated_fill_ratio"}


# ── add / query ─────────────────────────────────────────────────────────────────

def test_add_returns_estimate():
    sb = SpectralBloom()
    assert sb.add("x") == 1


def test_query_absent_is_zero():
    assert SpectralBloom().query("never") == 0


def test_multiplicity_exact_at_low_load():
    sb = SpectralBloom(seed=0)
    for _ in range(5):
        sb.add("five")
    assert sb.query("five") == 5


def test_batch_count_add():
    sb = SpectralBloom(seed=0)
    assert sb.add("x", 7) == 7
    assert sb.query("x") == 7


def test_add_accumulates():
    sb = SpectralBloom(seed=0)
    sb.add("x", 3)
    sb.add("x", 4)
    assert sb.query("x") == 7


def test_query_is_min_not_max():
    # The estimate is the MIN counter across positions (HeavyKeeper's counterpoint).
    sb = SpectralBloom(capacity=2000, error_rate=0.02, seed=0)
    for i in range(1500):
        sb.add(f"load{i}")
    sb.add("probe", 10)
    vals = [sb._counters[p] for p in sb._positions("probe")]
    assert sb.query("probe") == min(vals) <= max(vals)


def test_membership_operator():
    sb = SpectralBloom()
    sb.add("yes")
    assert "yes" in sb and "no" not in sb


def test_integer_and_mixed_items():
    sb = SpectralBloom()
    sb.add(7, 2)
    sb.add("7", 1)
    assert sb.query(7) == 2          # 7 and "7" are distinct items


# ── zero false negatives / FPR ──────────────────────────────────────────────────

def test_zero_false_negatives():
    sb = SpectralBloom(capacity=10000, error_rate=0.01, seed=0)
    members = [f"m{i}" for i in range(1000)]
    for x in members:
        sb.add(x)
    assert all(sb.query(x) >= 1 for x in members)


def test_false_positive_rate_within_bound():
    sb = SpectralBloom(capacity=2000, error_rate=0.05, seed=0)
    for i in range(2000):
        sb.add(f"m{i}")
    non = [f"absent-{i}" for i in range(5000)]
    fpr = sum(1 for x in non if sb.query(x) > 0) / len(non)
    assert fpr <= 2 * 0.05          # directive bound: FPR ≤ 2 × error_rate


def test_underloaded_filter_has_near_zero_fpr():
    sb = SpectralBloom(capacity=10000, error_rate=0.01, seed=0)
    for i in range(500):
        sb.add(f"m{i}")
    non = [f"absent-{i}" for i in range(5000)]
    assert sum(1 for x in non if sb.query(x) > 0) / len(non) < 0.01


# ── remove (deletion) ───────────────────────────────────────────────────────────

def test_remove_decrements():
    sb = SpectralBloom(seed=0)
    sb.add("e", 3)
    assert sb.remove("e") == 1
    assert sb.query("e") == 2


def test_remove_to_zero():
    sb = SpectralBloom(seed=0)
    sb.add("e", 3)
    sb.remove("e", 3)
    assert sb.query("e") == 0 and "e" not in sb


def test_remove_non_member_returns_zero():
    sb = SpectralBloom(seed=0)
    assert sb.remove("ghost") == 0


def test_remove_non_member_does_not_corrupt():
    sb = SpectralBloom(seed=0)
    sb.add("real", 4)
    sb.remove("ghost")              # must not touch shared counters
    assert sb.query("real") == 4


def test_remove_clamped_to_present():
    sb = SpectralBloom(seed=0)
    sb.add("e", 2)
    assert sb.remove("e", 10) == 2  # can't remove more than present
    assert sb.query("e") == 0


def test_remove_updates_num_added():
    sb = SpectralBloom(seed=0)
    sb.add("e", 5)
    sb.remove("e", 2)
    assert sb.stats()["num_added"] == 3


# ── determinism ─────────────────────────────────────────────────────────────────

def test_determinism_same_positions():
    a = SpectralBloom(seed=42)
    b = SpectralBloom(seed=42)
    assert a._positions("xyz") == b._positions("xyz")


def test_different_seed_differs():
    a = SpectralBloom(seed=1)
    b = SpectralBloom(seed=2)
    assert a._positions("xyz") != b._positions("xyz")


def test_determinism_across_reset():
    sb = SpectralBloom(seed=7)
    sb.add("xyz", 4)
    first = sb.query("xyz")
    sb.reset()
    sb.add("xyz", 4)
    assert sb.query("xyz") == first == 4


# ── validation ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {"capacity": 0}, {"capacity": -5}, {"capacity": True},
    {"error_rate": 0}, {"error_rate": 1}, {"error_rate": 1.5}, {"error_rate": -0.1},
    {"seed": "x"}, {"seed": 1.5},
])
def test_invalid_config_raises(kwargs):
    with pytest.raises(SpectralBloomError):
        SpectralBloom(**kwargs)


def test_add_bad_count_raises():
    sb = SpectralBloom()
    for bad in (0, -1, True, "3", 1.5):
        with pytest.raises(SpectralBloomError):
            sb.add("x", bad)


def test_remove_bad_count_raises():
    sb = SpectralBloom()
    with pytest.raises(SpectralBloomError):
        sb.remove("x", 0)


def test_error_detail_attribute():
    try:
        SpectralBloom(capacity=0)
    except SpectralBloomError as exc:
        assert exc.detail == 0
    else:
        pytest.fail("expected SpectralBloomError")


# ── reset / stats ───────────────────────────────────────────────────────────────

def test_reset_clears():
    sb = SpectralBloom(seed=0)
    sb.add("a", 50)
    sb.reset()
    assert sb.query("a") == 0 and sb.stats()["num_added"] == 0


def test_reset_reconfigures_size():
    sb = SpectralBloom(capacity=10000)
    before = sb.num_bits
    sb.reset(capacity=1000)
    assert sb.num_bits < before and sb.capacity == 1000


def test_reset_bad_config_raises():
    sb = SpectralBloom()
    with pytest.raises(SpectralBloomError):
        sb.reset(error_rate=1.0)


def test_num_added_and_fill_ratio():
    sb = SpectralBloom(capacity=1000, error_rate=0.05, seed=0)
    for i in range(100):
        sb.add(f"x{i}")
    s = sb.stats()
    assert s["num_added"] == 100 and 0.0 < s["estimated_fill_ratio"] < 1.0


def test_len_is_num_added():
    sb = SpectralBloom()
    sb.add("a", 4)
    sb.add("b", 6)
    assert len(sb) == 10


# ── concurrency ─────────────────────────────────────────────────────────────────

def test_concurrent_adds_no_lost_updates():
    sb = SpectralBloom(capacity=10000, error_rate=0.01, seed=0)

    def worker():
        for _ in range(125):
            sb.add("shared")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sb.query("shared") == 8 * 125     # lock prevents lost increments
