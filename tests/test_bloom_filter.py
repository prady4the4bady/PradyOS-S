"""Phase 72 — unit tests for BloomFilter (probabilistic set membership)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.bloom_filter import BloomFilter


# ── construction / sizing ─────────────────────────────────────────────────────

def test_default_sizing_is_positive():
    bf = BloomFilter()
    assert bf.bits > 0
    assert bf.hashes > 0
    assert bf.capacity == 1000
    assert bf.error_rate == 0.01


def test_smaller_error_rate_needs_more_bits():
    loose = BloomFilter(capacity=1000, error_rate=0.1)
    tight = BloomFilter(capacity=1000, error_rate=0.001)
    assert tight.bits > loose.bits


def test_larger_capacity_needs_more_bits():
    small = BloomFilter(capacity=100, error_rate=0.01)
    big = BloomFilter(capacity=10000, error_rate=0.01)
    assert big.bits > small.bits


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        BloomFilter(capacity=0)
    with pytest.raises(ValueError):
        BloomFilter(capacity=-5)


def test_invalid_error_rate_raises():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            BloomFilter(error_rate=bad)


# ── add / contains ────────────────────────────────────────────────────────────

def test_add_returns_true_for_new_item():
    bf = BloomFilter()
    assert bf.add("alpha") is True


def test_add_returns_false_for_duplicate():
    bf = BloomFilter()
    bf.add("alpha")
    assert bf.add("alpha") is False


def test_contains_true_after_add():
    bf = BloomFilter()
    bf.add("alpha")
    assert bf.contains("alpha") is True


def test_contains_false_for_absent_item():
    bf = BloomFilter()
    bf.add("alpha")
    bf.add("beta")
    assert bf.contains("gamma-never-added") is False


def test_contains_operator():
    bf = BloomFilter()
    bf.add("alpha")
    assert "alpha" in bf
    assert "omega-absent" not in bf


# ── add_many / len ────────────────────────────────────────────────────────────

def test_add_many_counts_new_items():
    bf = BloomFilter()
    assert bf.add_many(["a", "b", "c"]) == 3


def test_add_many_ignores_duplicates_in_count():
    bf = BloomFilter()
    assert bf.add_many(["a", "a", "b"]) == 2


def test_len_reflects_distinct_added():
    bf = BloomFilter()
    bf.add_many(["a", "b", "c", "a"])
    assert len(bf) == 3


# ── the core Bloom guarantee ──────────────────────────────────────────────────

def test_no_false_negatives():
    bf = BloomFilter(capacity=1000, error_rate=0.01)
    items = [f"item-{i}" for i in range(500)]
    bf.add_many(items)
    assert all(bf.contains(x) for x in items)


def test_false_positive_rate_within_bound():
    bf = BloomFilter(capacity=1000, error_rate=0.01)
    bf.add_many([f"present-{i}" for i in range(1000)])
    absent = [f"absent-{i}" for i in range(2000)]
    false_positives = sum(1 for x in absent if bf.contains(x))
    # generous bound (5x the target) — hashing is deterministic so this is stable
    assert false_positives / len(absent) <= 0.05


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_resets_everything():
    bf = BloomFilter()
    bf.add_many(["a", "b", "c"])
    bf.clear()
    assert len(bf) == 0
    assert bf.fill_ratio() == 0.0
    assert bf.contains("a") is False


# ── stats / metrics ───────────────────────────────────────────────────────────

def test_stats_has_expected_keys():
    bf = BloomFilter()
    stats = bf.stats()
    for key in ("capacity", "error_rate", "bits", "hashes", "count",
                "fill_ratio", "est_false_positive_rate"):
        assert key in stats, f"missing key: {key}"


def test_stats_count_tracks_adds():
    bf = BloomFilter()
    bf.add_many(["a", "b"])
    assert bf.stats()["count"] == 2


def test_fill_ratio_zero_when_empty():
    assert BloomFilter().fill_ratio() == 0.0


def test_fill_ratio_increases_after_add():
    bf = BloomFilter()
    before = bf.fill_ratio()
    bf.add("alpha")
    assert bf.fill_ratio() > before


def test_estimated_fpp_zero_when_empty():
    assert BloomFilter().estimated_false_positive_rate() == 0.0


def test_estimated_fpp_increases_with_load():
    bf = BloomFilter(capacity=100, error_rate=0.01)
    bf.add_many([f"x{i}" for i in range(50)])
    low = bf.estimated_false_positive_rate()
    bf.add_many([f"y{i}" for i in range(50)])
    assert bf.estimated_false_positive_rate() > low


# ── property accessors ────────────────────────────────────────────────────────

def test_property_accessors():
    bf = BloomFilter(capacity=500, error_rate=0.02)
    assert bf.capacity == 500
    assert bf.error_rate == 0.02
    assert isinstance(bf.bits, int) and bf.bits > 0
    assert isinstance(bf.hashes, int) and bf.hashes > 0


# ── heterogeneous keys ────────────────────────────────────────────────────────

def test_non_string_items():
    bf = BloomFilter()
    bf.add(42)
    bf.add((1, 2, 3))
    assert 42 in bf
    assert (1, 2, 3) in bf


def test_unicode_items():
    bf = BloomFilter()
    bf.add("naïve—Ω")
    assert bf.contains("naïve—Ω")
    assert not bf.contains("plain")


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_adds_are_thread_safe():
    bf = BloomFilter(capacity=5000, error_rate=0.01)
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(100):
                bf.add(f"k-{base}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # no false negatives, regardless of interleaving
    assert all(bf.contains(f"k-{b}-{i}") for b in range(10) for i in range(100))
    assert 0 < len(bf) <= 1000
