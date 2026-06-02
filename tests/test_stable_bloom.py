"""Phase 110 — unit tests for StableBloomFilter (pradyos/core/stable_bloom.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.stable_bloom import StableBloomError, StableBloomFilter


# ── basic correctness ──────────────────────────────────────────────────────────

def test_fresh_add_is_contained():
    f = StableBloomFilter(num_cells=10000, num_hashes=5, max_value=3)
    f.add("hello")
    assert f.contains("hello") is True


def test_contains_absent_on_empty_is_false():
    f = StableBloomFilter(num_cells=10000, num_hashes=5)
    assert f.contains("never-added") is False


def test_contains_dunder_operator():
    f = StableBloomFilter(num_cells=10000)
    f.add("x")
    assert "x" in f


def test_len_tracks_add_count():
    f = StableBloomFilter(num_cells=10000)
    for i in range(25):
        f.add(f"k{i}")
    assert len(f) == 25


def test_count_property_counts_adds():
    f = StableBloomFilter(num_cells=10000)
    f.add("a")
    f.add("a")                      # repeated adds still bump count
    assert f.count == 2


def test_add_accepts_non_string():
    f = StableBloomFilter(num_cells=1000)
    f.add(12345)
    f.add(("tuple", "key"))
    assert len(f) == 2


# ── configuration & validation ──────────────────────────────────────────────────

def test_invalid_num_cells_zero_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=0)


def test_invalid_num_cells_negative_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=-10)


def test_invalid_num_hashes_zero_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=1000, num_hashes=0)


def test_invalid_max_value_zero_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=1000, max_value=0)


def test_invalid_max_value_too_large_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=1000, max_value=256)   # one byte per cell


def test_max_value_255_allowed():
    assert StableBloomFilter(num_cells=1000, max_value=255).max_value == 255


def test_invalid_decrement_zero_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=1000, decrement=0)


def test_invalid_decrement_exceeds_cells_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=100, decrement=101)


def test_invalid_seed_raises():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=1000, seed="nope")


def test_bool_num_cells_rejected():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=True)


def test_bool_seed_rejected():
    with pytest.raises(StableBloomError):
        StableBloomFilter(num_cells=1000, seed=True)


def test_error_stores_detail():
    err = StableBloomError(-7)
    assert err.detail == -7
    assert "-7" in str(err)


# ── decrement (P) configuration ───────────────────────────────────────────────────

def test_default_decrement_is_k_times_max():
    f = StableBloomFilter(num_cells=10000, num_hashes=5, max_value=3)
    assert f.decrement == 15          # k * Max


def test_default_decrement_capped_at_num_cells():
    f = StableBloomFilter(num_cells=8, num_hashes=5, max_value=3)
    assert f.decrement == 8           # k*Max=15 capped to num_cells


def test_explicit_decrement_respected():
    assert StableBloomFilter(num_cells=10000, decrement=42).decrement == 42


# ── streaming behaviour: stability, recall, forgetting ────────────────────────────

def test_fill_ratio_starts_zero():
    assert StableBloomFilter(num_cells=1000).fill_ratio() == 0.0


def test_fill_ratio_stabilises_not_saturating():
    f = StableBloomFilter(num_cells=20000, num_hashes=5, max_value=3, seed=1)
    fills = {}
    for i in range(40000):
        f.add(f"s-{i}")
        if i in (19999, 39999):
            fills[i + 1] = f.fill_ratio()
    assert fills[20000] < 0.95 and fills[40000] < 0.95            # never saturates
    assert abs(fills[40000] - fills[20000]) < 0.05               # plateaus


def test_recent_items_recalled():
    f = StableBloomFilter(num_cells=20000, num_hashes=5, max_value=3, seed=1)
    for i in range(40000):
        f.add(f"s-{i}")
    recent = [f"s-{i}" for i in range(39900, 40000)]
    recall = sum(1 for e in recent if f.contains(e)) / len(recent)
    assert recall >= 0.95


def test_stale_items_are_forgotten():
    # Insert a victim, flood the stream, and most victims should be evicted.
    f = StableBloomFilter(num_cells=5000, num_hashes=4, max_value=3, seed=7)
    forgotten = 0
    trials = 25
    for t in range(trials):
        f.add(f"victim-{t}")
        for j in range(1500):
            f.add(f"flood-{t}-{j}")
        if not f.contains(f"victim-{t}"):
            forgotten += 1
    assert forgotten / trials >= 0.5         # bounded-FN forgetting (the SBF trade)


def test_false_positive_rate_bounded():
    f = StableBloomFilter(num_cells=20000, num_hashes=5, max_value=3, seed=2)
    for i in range(30000):
        f.add(f"present-{i}")
    fp = sum(1 for i in range(8000) if f.contains(f"absent-{i}")) / 8000
    assert fp < 0.20


def test_no_saturation_under_heavy_stream():
    f = StableBloomFilter(num_cells=4000, num_hashes=4, max_value=3, seed=4)
    for i in range(40000):
        f.add(f"x-{i}")
    assert f.fill_ratio() < 0.95             # forgetting keeps it from filling up


def test_larger_max_value_improves_recall():
    def recall(maxv):
        h = StableBloomFilter(num_cells=8000, num_hashes=4, max_value=maxv,
                              decrement=4, seed=3)
        for i in range(20000):
            h.add(f"s-{i}")
        recent = [f"s-{i}" for i in range(19800, 20000)]
        return sum(1 for e in recent if h.contains(e)) / len(recent)
    assert recall(7) >= recall(1)


# ── determinism ───────────────────────────────────────────────────────────────────

def test_same_seed_reproducible():
    a = StableBloomFilter(num_cells=4096, num_hashes=4, max_value=3, seed=5)
    b = StableBloomFilter(num_cells=4096, num_hashes=4, max_value=3, seed=5)
    for i in range(3000):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a.stats() == b.stats()
    assert all(a.contains(f"k{i}") == b.contains(f"k{i}") for i in range(3000))


def test_different_seed_diverges():
    a = StableBloomFilter(num_cells=4096, num_hashes=4, max_value=3, seed=5)
    c = StableBloomFilter(num_cells=4096, num_hashes=4, max_value=3, seed=6)
    for i in range(3000):
        a.add(f"k{i}")
        c.add(f"k{i}")
    # The eviction RNG and the hash are both salted by seed → divergent state.
    assert a.stats()["fill_ratio"] != c.stats()["fill_ratio"] or \
        any(a.contains(f"z{i}") != c.contains(f"z{i}") for i in range(2000))


def test_seed_property():
    assert StableBloomFilter(num_cells=1000, seed=99).seed == 99


# ── stats & properties ───────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(StableBloomFilter(num_cells=1000).stats()) == {
        "num_cells", "num_hashes", "max_value", "decrement", "count",
        "fill_ratio", "seed"}


def test_stats_initial():
    s = StableBloomFilter(num_cells=1000, num_hashes=4, max_value=3).stats()
    assert s["count"] == 0 and s["fill_ratio"] == 0.0
    assert s["num_cells"] == 1000 and s["num_hashes"] == 4 and s["max_value"] == 3


def test_stats_reflects_config():
    s = StableBloomFilter(num_cells=2048, num_hashes=7, max_value=15,
                          decrement=20, seed=8).stats()
    assert s["num_cells"] == 2048 and s["num_hashes"] == 7
    assert s["max_value"] == 15 and s["decrement"] == 20 and s["seed"] == 8


def test_properties_reflect_config():
    f = StableBloomFilter(num_cells=2048, num_hashes=6, max_value=7, decrement=30, seed=2)
    assert f.num_cells == 2048 and f.num_hashes == 6 and f.max_value == 7
    assert f.decrement == 30 and f.seed == 2


def test_fill_ratio_grows_with_inserts():
    f = StableBloomFilter(num_cells=10000, num_hashes=4, max_value=3, seed=0)
    for i in range(500):
        f.add(f"k{i}")
    assert 0.0 < f.fill_ratio() < 1.0


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    f = StableBloomFilter(num_cells=10000)
    for i in range(100):
        f.add(f"k{i}")
    f.reset()
    assert len(f) == 0 and f.fill_ratio() == 0.0
    assert f.contains("k0") is False


def test_reset_reconfigures():
    f = StableBloomFilter(num_cells=10000, num_hashes=5, max_value=3)
    f.reset(num_cells=2048, num_hashes=7, max_value=7, seed=3)
    assert f.num_cells == 2048 and f.num_hashes == 7 and f.max_value == 7 and f.seed == 3
    assert f.decrement == min(7 * 7, 2048)      # default recomputed for new shape


def test_reset_explicit_decrement():
    f = StableBloomFilter(num_cells=10000)
    f.reset(num_cells=5000, decrement=33)
    assert f.decrement == 33


def test_reset_invalid_config_raises():
    f = StableBloomFilter(num_cells=10000)
    with pytest.raises(StableBloomError):
        f.reset(num_cells=0)


def test_reset_re_seeds_determinism():
    a = StableBloomFilter(num_cells=4096, num_hashes=4, max_value=3, seed=5)
    for i in range(500):
        a.add(f"k{i}")
    a.reset(seed=5)
    b = StableBloomFilter(num_cells=4096, num_hashes=4, max_value=3, seed=5)
    for i in range(500):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a.stats() == b.stats()               # reset restored the RNG sequence


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds_no_error():
    f = StableBloomFilter(num_cells=20000, num_hashes=4, max_value=3)
    errors = []

    def worker(base):
        try:
            for i in range(200):
                f.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(f) == 2000


def test_concurrent_add_contains_consistent():
    f = StableBloomFilter(num_cells=20000, num_hashes=4, max_value=3)
    errors = []

    def adder(base):
        try:
            for i in range(200):
                f.add(f"x{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    def reader(base):
        try:
            for i in range(200):
                f.contains(f"x{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = (
        [threading.Thread(target=adder, args=(b,)) for b in range(5)]
        + [threading.Thread(target=reader, args=(b,)) for b in range(5)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert f.fill_ratio() <= 1.0
