"""Phase 107 — unit tests for the Sovereign Counting Bloom Filter (pradyos.core.counting_bloom)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.counting_bloom import CountingBloom, CountingBloomError


def _loaded(n: int = 1000, capacity: int = 1000, error_rate: float = 0.01, seed: int = 0):
    cb = CountingBloom(capacity=capacity, error_rate=error_rate, seed=seed)
    for i in range(n):
        cb.add(f"member-{i}")
    return cb


# ── construction / params ──────────────────────────────────────────────────────────

def test_default_params():
    cb = CountingBloom()
    assert cb.capacity == 10000 and cb.error_rate == 0.01 and cb.seed == 0


def test_custom_params():
    cb = CountingBloom(capacity=500, error_rate=0.05, seed=7)
    assert (cb.capacity, cb.error_rate, cb.seed) == (500, 0.05, 7)


def test_len_starts_zero():
    assert len(CountingBloom()) == 0


def test_stats_keys():
    assert set(CountingBloom().stats()) == {
        "capacity", "error_rate", "num_hash_functions", "num_counters",
        "count", "false_positive_rate"}


def test_sizing_formulas():
    # m = ceil(-n ln p / (ln2)^2), k = ceil(m/n * ln2)
    import math
    n, p = 1000, 0.01
    cb = CountingBloom(capacity=n, error_rate=p)
    exp_m = math.ceil(-n * math.log(p) / (math.log(2) ** 2))
    exp_k = math.ceil((exp_m / n) * math.log(2))
    assert cb.num_counters == exp_m and cb.num_hash_functions == exp_k


def test_smaller_error_rate_more_counters():
    loose = CountingBloom(capacity=1000, error_rate=0.1)
    tight = CountingBloom(capacity=1000, error_rate=0.001)
    assert tight.num_counters > loose.num_counters


# ── validation ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [0, -5, 1.5, "x", None, True])
def test_bad_capacity_raises(bad):
    with pytest.raises(CountingBloomError):
        CountingBloom(capacity=bad)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5, "x", None, True])
def test_bad_error_rate_raises(bad):
    with pytest.raises(CountingBloomError):
        CountingBloom(error_rate=bad)


@pytest.mark.parametrize("bad", [1.5, "x", None, True])
def test_bad_seed_raises(bad):
    with pytest.raises(CountingBloomError):
        CountingBloom(seed=bad)


def test_error_carries_detail():
    err = CountingBloomError("element not in filter")
    assert err.detail == "element not in filter"


# ── add / contains ───────────────────────────────────────────────────────────────

def test_add_increments_count():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("a")
    cb.add("b")
    assert cb.count == 2 and len(cb) == 2


def test_contains_after_add():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("apple")
    assert cb.contains("apple") is True


def test_contains_absent_is_false():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("apple")
    assert cb.contains("banana") is False


def test_contains_operator():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("x")
    assert "x" in cb and "y" not in cb


def test_no_false_negatives():
    cb = _loaded(1000)
    assert all(cb.contains(f"member-{i}") for i in range(1000))


def test_count_is_add_calls_not_unique():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("same")
    cb.add("same")
    cb.add("same")
    assert cb.count == 3


# ── remove ───────────────────────────────────────────────────────────────────────────

def test_remove_deletes():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("apple")
    assert cb.contains("apple")
    cb.remove("apple")
    assert not cb.contains("apple")


def test_remove_decrements_count():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("a")
    cb.add("b")
    cb.remove("a")
    assert cb.count == 1


def test_remove_absent_raises():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    with pytest.raises(CountingBloomError):
        cb.remove("ghost")


def test_double_add_single_remove_still_present():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("dup")
    cb.add("dup")
    cb.remove("dup")
    assert cb.contains("dup")


def test_double_add_double_remove_gone():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    cb.add("dup")
    cb.add("dup")
    cb.remove("dup")
    cb.remove("dup")
    assert not cb.contains("dup")


def test_remove_does_not_corrupt_neighbors():
    cb = CountingBloom(capacity=1000, error_rate=0.01)
    for i in range(200):
        cb.add(f"keep-{i}")
    cb.add("victim")
    cb.remove("victim")
    # all the other members must still be present (no under-decrement corruption)
    assert all(cb.contains(f"keep-{i}") for i in range(200))


# ── saturation ───────────────────────────────────────────────────────────────────────

def test_saturation_caps_at_15():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    for _ in range(20):
        cb.add("hot")
    idxs = cb._indices("hot")
    assert max(cb._counters[i] for i in idxs) == 15


def test_saturation_no_crash_still_contains():
    cb = CountingBloom(capacity=100, error_rate=0.01)
    for _ in range(50):
        cb.add("hot")
    assert cb.contains("hot")


# ── false positive rate ──────────────────────────────────────────────────────────────

def test_empirical_fpr_within_target():
    cb = _loaded(1000, capacity=1000, error_rate=0.01)
    fp = sum(1 for i in range(10000) if cb.contains(f"nonmember-{i}"))
    assert fp / 10000 <= 0.02


def test_false_positive_rate_zero_when_empty():
    assert CountingBloom(capacity=100, error_rate=0.01).false_positive_rate() == 0.0


def test_false_positive_rate_grows_with_load():
    cb = CountingBloom(capacity=1000, error_rate=0.01)
    f0 = cb.false_positive_rate()
    for i in range(500):
        cb.add(f"e-{i}")
    f1 = cb.false_positive_rate()
    assert f1 > f0


def test_false_positive_rate_formula():
    import math
    cb = _loaded(300, capacity=1000, error_rate=0.01)
    n, k, m = cb.count, cb.num_hash_functions, cb.num_counters
    expected = (1.0 - math.exp(-k * n / m)) ** k
    assert cb.false_positive_rate() == pytest.approx(expected)


# ── determinism ──────────────────────────────────────────────────────────────────────

def test_determinism_same_counter_array():
    def build():
        cb = CountingBloom(capacity=500, error_rate=0.01, seed=7)
        for i in range(300):
            cb.add(f"elem-{i}")
        return cb
    assert build()._counters.tobytes() == build()._counters.tobytes()


def test_different_seed_different_array():
    def build(seed):
        cb = CountingBloom(capacity=500, error_rate=0.01, seed=seed)
        for i in range(300):
            cb.add(f"elem-{i}")
        return cb
    assert build(1)._counters.tobytes() != build(2)._counters.tobytes()


def test_insertion_order_independent():
    a = CountingBloom(capacity=500, error_rate=0.01, seed=0)
    b = CountingBloom(capacity=500, error_rate=0.01, seed=0)
    items = [f"e-{i}" for i in range(200)]
    for x in items:
        a.add(x)
    for x in reversed(items):
        b.add(x)
    assert a._counters.tobytes() == b._counters.tobytes()


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    cb = _loaded(500)
    cb.reset()
    assert cb.count == 0 and not cb.contains("member-0")


def test_reset_reconfigures():
    cb = CountingBloom(capacity=1000, error_rate=0.01)
    cb.reset(capacity=2000, error_rate=0.05, seed=3)
    assert (cb.capacity, cb.error_rate, cb.seed) == (2000, 0.05, 3)


def test_reset_bad_config_raises():
    cb = CountingBloom()
    with pytest.raises(CountingBloomError):
        cb.reset(error_rate=0.0)


def test_reset_then_usable():
    cb = _loaded(100)
    cb.reset(capacity=50, error_rate=0.01)
    cb.add("fresh")
    assert cb.contains("fresh") and cb.count == 1


# ── thread-safety ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    cb = CountingBloom(capacity=20000, error_rate=0.01)

    def worker(base):
        for i in range(500):
            cb.add(f"t{base}-{i}")

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert cb.count == 8 * 500


# ── stats integration ───────────────────────────────────────────────────────────────

def test_stats_after_load():
    cb = _loaded(1000)
    s = cb.stats()
    assert s["count"] == 1000 and s["capacity"] == 1000
    assert s["num_hash_functions"] == cb.num_hash_functions
    assert 0.0 <= s["false_positive_rate"] <= 1.0
