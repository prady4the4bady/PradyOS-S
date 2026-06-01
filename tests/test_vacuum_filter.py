"""Phase 109 — unit tests for VacuumFilter (pradyos/core/vacuum_filter.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.vacuum_filter import (
    VacuumFilter,
    VacuumFilterError,
    _auto_alt_range,
    _next_pow2,
    _prev_pow2,
)


def make_hash(mapping):
    """Deterministic hash: known items → fixed ints; integer fingerprints → identity."""
    def _h(x):
        if isinstance(x, int):          # a fingerprint fed back in by the filter
            return x
        return mapping[x]
    return _h


# ── basic correctness ──────────────────────────────────────────────────────────

def test_insert_returns_true():
    assert VacuumFilter(capacity=64).insert("a") is True


def test_contains_after_insert():
    f = VacuumFilter(capacity=64)
    f.insert("a")
    assert f.contains("a") is True


def test_contains_absent_is_false_deterministic():
    h = make_hash({"a": 0x0105, "z": 0x9207})   # distinct fp AND chunk
    f = VacuumFilter(capacity=64, hash_fn=h)
    f.insert("a")
    assert f.contains("z") is False


def test_delete_present_returns_true():
    f = VacuumFilter(capacity=64)
    f.insert("a")
    assert f.delete("a") is True


def test_delete_absent_returns_false():
    assert VacuumFilter(capacity=64).delete("nope") is False


def test_delete_removes_membership():
    h = make_hash({"a": 0x0105, "z": 0x9207})
    f = VacuumFilter(capacity=64, hash_fn=h)
    f.insert("a")
    f.delete("a")
    assert f.contains("a") is False


def test_reinsert_after_delete():
    f = VacuumFilter(capacity=64)
    f.insert("a")
    f.delete("a")
    assert f.insert("a") is True
    assert f.contains("a") is True


def test_insert_many_all_present_no_false_negatives():
    f = VacuumFilter(capacity=256)
    keys = [f"item{i}" for i in range(300)]
    inserted = [k for k in keys if f.insert(k)]
    missing = [k for k in inserted if not f.contains(k)]
    assert missing == []
    assert len(inserted) == 300            # well under load with 256*4 slots


def test_len_tracks_count():
    f = VacuumFilter(capacity=64)
    for i in range(10):
        f.insert(f"k{i}")
    assert len(f) == 10


def test_contains_dunder_operator():
    f = VacuumFilter(capacity=64)
    f.insert("a")
    assert "a" in f


def test_len_after_delete_decrements():
    f = VacuumFilter(capacity=64)
    f.insert("a")
    f.insert("b")
    f.delete("a")
    assert len(f) == 1


# ── configuration & validation ──────────────────────────────────────────────────

def test_invalid_capacity_zero_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=0)


def test_invalid_capacity_negative_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=-4)


def test_invalid_bucket_size_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=8, bucket_size=0)


def test_invalid_fingerprint_bits_zero_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=8, fingerprint_bits=0)


def test_invalid_fingerprint_bits_too_large_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=8, fingerprint_bits=64)


def test_invalid_max_kicks_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=8, max_kicks=0)


def test_invalid_alt_range_not_power_of_two_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=1024, alt_range=100)


def test_invalid_alt_range_zero_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=1024, alt_range=0)


def test_invalid_seed_raises():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=8, seed="nope")


def test_bool_capacity_rejected():
    # bool is a subclass of int; it must not slip through as a valid capacity.
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=True)


def test_bool_seed_rejected():
    with pytest.raises(VacuumFilterError):
        VacuumFilter(capacity=8, seed=True)


def test_vacuum_error_stores_detail():
    err = VacuumFilterError(-7)
    assert err.detail == -7
    assert "invalid vacuum filter configuration" in str(err)


# ── alternate-range layout (the vacuum-filter distinctive) ───────────────────────

def test_bucket_count_is_multiple_of_alt_range():
    f = VacuumFilter(capacity=3000)
    assert f.capacity % f.alt_range == 0


def test_bucket_count_equals_chunks_times_range():
    f = VacuumFilter(capacity=3000)
    assert f.capacity == f.num_chunks * f.alt_range


def test_auto_alt_range_is_power_of_two():
    L = VacuumFilter(capacity=10000).alt_range
    assert L >= 1 and (L & (L - 1)) == 0


def test_auto_layout_known_values():
    f = VacuumFilter(capacity=3000)
    assert f.alt_range == 256 and f.num_chunks == 12 and f.capacity == 3072


def test_auto_layout_power_of_two_capacity():
    # capacity 4096 → L = prev_pow2(512) = 512, 8 chunks, m = 4096
    f = VacuumFilter(capacity=4096)
    assert f.alt_range == 512 and f.num_chunks == 8 and f.capacity == 4096


def test_explicit_alt_range_respected():
    f = VacuumFilter(capacity=1000, alt_range=128)
    assert f.alt_range == 128 and f.num_chunks == 8 and f.capacity == 1024


def test_alt_range_capped_at_capacity():
    # An alt_range larger than the capacity is clamped so it always fits.
    f = VacuumFilter(capacity=100, alt_range=256)
    assert f.alt_range <= f.capacity and (f.alt_range & (f.alt_range - 1)) == 0


def test_capacity_rounds_up_to_multiple_of_range():
    f = VacuumFilter(capacity=1100, alt_range=256)
    assert f.capacity == 1280 and f.capacity >= 1100


# ── space efficiency vs the cuckoo filter (no power-of-two rounding) ─────────────

def test_never_worse_than_cuckoo_power_of_two():
    for cap in (1100, 3000, 5000, 10000, 100000):
        assert VacuumFilter(capacity=cap).capacity <= _next_pow2(cap)


def test_strict_space_win_for_non_power_of_two_chunks():
    f = VacuumFilter(capacity=3000)
    assert f.capacity == 3072
    assert f.capacity < _next_pow2(3000)          # 3072 < 4096


def test_prev_pow2_helper():
    assert _prev_pow2(375) == 256 and _prev_pow2(256) == 256 and _prev_pow2(255) == 128


def test_auto_alt_range_helper_small():
    assert _auto_alt_range(4) == 1                # tiny filters degrade gracefully


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(VacuumFilter(capacity=64).stats()) == {
        "capacity", "num_chunks", "alt_range", "count", "load_factor",
        "fingerprint_bits", "max_kicks"}


def test_stats_initial_empty():
    s = VacuumFilter(capacity=64).stats()
    assert s["count"] == 0 and s["load_factor"] == 0.0


def test_load_factor_tracks_inserts():
    f = VacuumFilter(capacity=8, bucket_size=4, alt_range=8)   # 1 chunk, 32 slots
    for i in range(8):
        f.insert(f"k{i}")
    assert f.stats()["load_factor"] == pytest.approx(8 / 32)


def test_stats_fingerprint_bits_reflects_config():
    assert VacuumFilter(capacity=8, fingerprint_bits=16).stats()["fingerprint_bits"] == 16


def test_stats_max_kicks_reflects_config():
    assert VacuumFilter(capacity=8, max_kicks=42).stats()["max_kicks"] == 42


def test_stats_alt_range_and_chunks():
    s = VacuumFilter(capacity=3000).stats()
    assert s["alt_range"] == 256 and s["num_chunks"] == 12 and s["capacity"] == 3072


# ── max-kicks / full-filter behaviour ───────────────────────────────────────────

def test_full_filter_insert_returns_false():
    # alt_range=1 → both candidate buckets coincide; constant hash forces one bucket.
    f = VacuumFilter(capacity=1, bucket_size=2, alt_range=1, hash_fn=lambda x: 0)
    assert f.insert("a") is True
    assert f.insert("b") is True
    assert f.insert("c") is False        # both slots full, alt index == self
    assert len(f) == 2


def test_failed_insert_does_not_corrupt():
    # Saturate a single small chunk; every key that reported success stays present.
    f = VacuumFilter(capacity=8, bucket_size=2, alt_range=8)   # 1 chunk, 16 slots
    keys = [f"k{i}" for i in range(200)]
    inserted = [k for k in keys if f.insert(k)]
    missing = [k for k in inserted if not f.contains(k)]
    assert missing == []                 # rollback ⇒ no false negatives even when full


def test_count_unchanged_on_failed_insert():
    f = VacuumFilter(capacity=1, bucket_size=2, alt_range=1, hash_fn=lambda x: 0)
    f.insert("a")
    f.insert("b")
    before = len(f)
    assert f.insert("c") is False
    assert len(f) == before


# ── alternate-range involution & confinement ─────────────────────────────────────

def test_alt_index_is_involution_default_hash():
    f = VacuumFilter(capacity=4096)
    for i in range(2000):
        fp, i1, i2 = f._candidates(f"key-{i}")
        assert f._alt_index(i2, fp) == i1


def test_candidates_share_chunk_and_in_range():
    f = VacuumFilter(capacity=4096)
    L, m = f.alt_range, f.capacity
    for i in range(2000):
        _fp, i1, i2 = f._candidates(f"k-{i}")
        assert (i1 // L) == (i2 // L)        # same L-aligned chunk
        assert 0 <= i1 < m and 0 <= i2 < m


def test_alternate_bucket_round_trip():
    h = make_hash({"x": 0x03F1})
    f = VacuumFilter(capacity=8, bucket_size=1, alt_range=8, hash_fn=h)
    assert f.insert("x") is True
    assert f.delete("x") is True
    assert f.contains("x") is False


# ── determinism via injected hash / seed ──────────────────────────────────────────

def test_deterministic_placement_same_hash():
    mapping = {f"k{i}": (i << 8) | (i + 1) for i in range(20)}
    h = make_hash(mapping)
    a = VacuumFilter(capacity=64, hash_fn=h)
    b = VacuumFilter(capacity=64, hash_fn=h)
    for k in mapping:
        a.insert(k)
        b.insert(k)
    assert a.stats() == b.stats()
    assert all(a.contains(k) == b.contains(k) for k in mapping)


def test_same_seed_reproducible():
    a = VacuumFilter(capacity=512, seed=7)
    b = VacuumFilter(capacity=512, seed=7)
    for i in range(200):
        a.insert(f"k{i}")
        b.insert(f"k{i}")
    assert a.stats() == b.stats()
    assert all(a.contains(f"k{i}") == b.contains(f"k{i}") for i in range(200))


def test_different_seed_diverges_placement():
    a = VacuumFilter(capacity=512, seed=1)
    b = VacuumFilter(capacity=512, seed=2)
    for i in range(200):
        a.insert(f"k{i}")
        b.insert(f"k{i}")
    # Different salt ⇒ different bucket occupancy snapshots (overwhelmingly likely).
    assert a._buckets != b._buckets


def test_seed_property():
    assert VacuumFilter(capacity=64, seed=99).seed == 99


def test_injected_hash_collision_is_false_positive():
    # 'a' and 'ghost' share an identical hash → identical fingerprint & buckets.
    h = make_hash({"a": 0x0105, "ghost": 0x0105})
    f = VacuumFilter(capacity=64, hash_fn=h)
    f.insert("a")
    assert f.contains("ghost") is True          # never inserted, yet reported present


def test_delete_clears_injected_false_positive():
    h = make_hash({"a": 0x0105, "ghost": 0x0105})
    f = VacuumFilter(capacity=64, hash_fn=h)
    f.insert("a")
    f.delete("a")
    assert f.contains("ghost") is False


# ── false-positive rate (seeded / default hash) ─────────────────────────────────

def test_false_positive_rate_bounded():
    # Default hash, 8 fp-bits, bucket_size 4 → theoretical FP ≈ 2*4/256 = 3.1%.
    f = VacuumFilter(capacity=1024, bucket_size=4, fingerprint_bits=8)
    for i in range(2000):
        f.insert(f"present-{i}")
    fp = sum(1 for i in range(5000) if f.contains(f"absent-{i}"))
    assert fp / 5000 < 0.05               # generous ceiling over the ~3.1% expectation


def test_wider_fingerprint_lowers_false_positives():
    f = VacuumFilter(capacity=1024, fingerprint_bits=16)
    for i in range(2000):
        f.insert(f"present-{i}")
    fp = sum(1 for i in range(5000) if f.contains(f"absent-{i}"))
    assert fp / 5000 < 0.005              # 16-bit fingerprints ⇒ far fewer collisions


def test_high_occupancy_no_false_negatives():
    # Fill until the first insert fails; the default hash is deterministic so the
    # achieved load is reproducible run-to-run.
    f = VacuumFilter(capacity=8192, bucket_size=4)
    slots = f.capacity * 4
    inserted = []
    for i in range(slots):
        if f.insert(f"x-{i}"):
            inserted.append(f"x-{i}")
        else:
            break
    load = len(inserted) / slots
    assert load >= 0.90                    # reaches high occupancy (≈0.95)
    assert all(f.contains(k) for k in inserted)   # …with zero false negatives


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears_all():
    f = VacuumFilter(capacity=64)
    for i in range(10):
        f.insert(f"k{i}")
    f.reset()
    assert len(f) == 0
    assert not f.contains("k0")


def test_reset_then_reinsert():
    f = VacuumFilter(capacity=64)
    f.insert("a")
    f.reset()
    assert f.insert("a") is True
    assert len(f) == 1


def test_reset_preserves_layout():
    f = VacuumFilter(capacity=3000)
    f.insert("a")
    f.reset()
    assert f.alt_range == 256 and f.num_chunks == 12 and f.capacity == 3072


# ── concurrency ─────────────────────────────────────────────────────────────────

def test_concurrent_inserts_10_threads():
    f = VacuumFilter(capacity=2048)   # 8192 slots, no saturation
    errors = []

    def worker(base):
        try:
            for i in range(50):
                f.insert(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(f) == 500
    assert all(f.contains(f"t{b}-{i}") for b in range(10) for i in range(50))


def test_concurrent_insert_delete_consistent():
    f = VacuumFilter(capacity=2048)
    errors = []

    def inserter(base):
        try:
            for i in range(100):
                f.insert(f"x{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    def deleter(base):
        try:
            for i in range(100):
                f.delete(f"x{base}-{i}")        # may or may not be present yet
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = (
        [threading.Thread(target=inserter, args=(b,)) for b in range(5)]
        + [threading.Thread(target=deleter, args=(b,)) for b in range(5)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(f) >= 0                          # count never goes negative under the lock
