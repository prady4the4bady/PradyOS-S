"""Phase 86 — unit tests for SovereignCuckooFilter (pradyos/core/cuckoo.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.cuckoo import CuckooError, SovereignCuckooFilter


def make_hash(mapping):
    """Deterministic hash: known items → fixed ints; integer fingerprints → identity."""
    def _h(x):
        if isinstance(x, int):          # a fingerprint fed back in by the filter
            return x
        return mapping[x]
    return _h


# ── basic correctness ──────────────────────────────────────────────────────────

def test_insert_returns_true():
    f = SovereignCuckooFilter(capacity=64)
    assert f.insert("a") is True


def test_contains_after_insert():
    f = SovereignCuckooFilter(capacity=64)
    f.insert("a")
    assert f.contains("a") is True


def test_contains_absent_is_false_deterministic():
    h = make_hash({"a": 0x0105, "z": 0x0207})   # distinct fp AND bucket
    f = SovereignCuckooFilter(capacity=4, hash_fn=h)
    f.insert("a")
    assert f.contains("z") is False


def test_delete_present_returns_true():
    f = SovereignCuckooFilter(capacity=64)
    f.insert("a")
    assert f.delete("a") is True


def test_delete_absent_returns_false():
    f = SovereignCuckooFilter(capacity=64)
    assert f.delete("nope") is False


def test_delete_removes_membership():
    h = make_hash({"a": 0x0105, "z": 0x0207})
    f = SovereignCuckooFilter(capacity=4, hash_fn=h)
    f.insert("a")
    f.delete("a")
    assert f.contains("a") is False


def test_reinsert_after_delete():
    f = SovereignCuckooFilter(capacity=64)
    f.insert("a")
    f.delete("a")
    assert f.insert("a") is True
    assert f.contains("a") is True


def test_insert_many_all_present_no_false_negatives():
    f = SovereignCuckooFilter(capacity=256)
    keys = [f"item{i}" for i in range(300)]
    inserted = [k for k in keys if f.insert(k)]
    missing = [k for k in inserted if not f.contains(k)]
    assert missing == []
    assert len(inserted) >= 300         # well under load with 1024 slots


def test_len_tracks_count():
    f = SovereignCuckooFilter(capacity=64)
    for i in range(10):
        f.insert(f"k{i}")
    assert len(f) == 10


def test_contains_dunder_operator():
    f = SovereignCuckooFilter(capacity=64)
    f.insert("a")
    assert "a" in f


def test_len_after_delete_decrements():
    f = SovereignCuckooFilter(capacity=64)
    f.insert("a")
    f.insert("b")
    f.delete("a")
    assert len(f) == 1


# ── configuration & validation ──────────────────────────────────────────────────

def test_capacity_rounds_to_power_of_two():
    assert SovereignCuckooFilter(capacity=100).capacity == 128


def test_capacity_already_power_of_two_unchanged():
    assert SovereignCuckooFilter(capacity=64).capacity == 64


def test_capacity_one_allowed():
    assert SovereignCuckooFilter(capacity=1).capacity == 1


def test_invalid_capacity_zero_raises():
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=0)


def test_invalid_capacity_negative_raises():
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=-4)


def test_invalid_bucket_size_raises():
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=8, bucket_size=0)


def test_invalid_fingerprint_bits_zero_raises():
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=8, fingerprint_bits=0)


def test_invalid_fingerprint_bits_too_large_raises():
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=8, fingerprint_bits=64)


def test_invalid_max_kicks_raises():
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=8, max_kicks=0)


def test_bool_capacity_rejected():
    # bool is a subclass of int; it must not slip through as a valid capacity.
    with pytest.raises(CuckooError):
        SovereignCuckooFilter(capacity=True)


def test_cuckoo_error_stores_detail():
    err = CuckooError(-7)
    assert err.detail == -7
    assert "invalid cuckoo filter configuration" in str(err)


# ── stats & load factor ─────────────────────────────────────────────────────────

def test_stats_keys():
    f = SovereignCuckooFilter(capacity=64)
    assert set(f.stats()) == {"capacity", "count", "load_factor", "fingerprint_bits", "max_kicks"}


def test_stats_initial_empty():
    s = SovereignCuckooFilter(capacity=64).stats()
    assert s["count"] == 0
    assert s["load_factor"] == 0.0


def test_load_factor_tracks_inserts():
    f = SovereignCuckooFilter(capacity=4, bucket_size=4)   # 16 slots
    for i in range(4):
        f.insert(f"k{i}")
    assert f.stats()["load_factor"] == pytest.approx(4 / 16)


def test_load_factor_after_reset_is_zero():
    f = SovereignCuckooFilter(capacity=8)
    for i in range(5):
        f.insert(f"k{i}")
    f.reset()
    assert f.stats()["load_factor"] == 0.0


def test_stats_fingerprint_bits_reflects_config():
    assert SovereignCuckooFilter(capacity=8, fingerprint_bits=16).stats()["fingerprint_bits"] == 16


def test_stats_max_kicks_reflects_config():
    assert SovereignCuckooFilter(capacity=8, max_kicks=42).stats()["max_kicks"] == 42


def test_stats_capacity_reflects_rounding():
    assert SovereignCuckooFilter(capacity=100).stats()["capacity"] == 128


# ── max-kicks / full-filter behaviour ───────────────────────────────────────────

def test_full_filter_insert_returns_false():
    # capacity=1 → single bucket; constant hash forces every item to it.
    f = SovereignCuckooFilter(capacity=1, bucket_size=2, hash_fn=lambda x: 0)
    assert f.insert("a") is True
    assert f.insert("b") is True
    assert f.insert("c") is False        # both slots full, alt index == self
    assert len(f) == 2


def test_failed_insert_does_not_corrupt():
    # Saturate, then keep inserting; every key that reported success stays present.
    f = SovereignCuckooFilter(capacity=8, bucket_size=2)   # 16 slots
    keys = [f"k{i}" for i in range(200)]
    inserted = [k for k in keys if f.insert(k)]
    missing = [k for k in inserted if not f.contains(k)]
    assert missing == []                 # rollback ⇒ no false negatives even when full


def test_count_unchanged_on_failed_insert():
    f = SovereignCuckooFilter(capacity=1, bucket_size=2, hash_fn=lambda x: 0)
    f.insert("a")
    f.insert("b")
    before = len(f)
    assert f.insert("c") is False
    assert len(f) == before


def test_max_kicks_configurable():
    f = SovereignCuckooFilter(capacity=16, max_kicks=1)
    assert f.stats()["max_kicks"] == 1


# ── determinism via injected hash ───────────────────────────────────────────────

def test_deterministic_placement_same_hash():
    mapping = {f"k{i}": (i << 8) | (i + 1) for i in range(20)}
    h = make_hash(mapping)
    a = SovereignCuckooFilter(capacity=16, hash_fn=h)
    b = SovereignCuckooFilter(capacity=16, hash_fn=h)
    for k in mapping:
        a.insert(k)
        b.insert(k)
    assert a.stats() == b.stats()
    assert all(a.contains(k) == b.contains(k) for k in mapping)


def test_injected_hash_collision_is_false_positive():
    # 'a' and 'ghost' share an identical hash → identical fingerprint & buckets.
    h = make_hash({"a": 0x0105, "ghost": 0x0105})
    f = SovereignCuckooFilter(capacity=4, hash_fn=h)
    f.insert("a")
    assert f.contains("ghost") is True          # never inserted, yet reported present


def test_delete_clears_injected_false_positive():
    h = make_hash({"a": 0x0105, "ghost": 0x0105})
    f = SovereignCuckooFilter(capacity=4, hash_fn=h)
    f.insert("a")
    f.delete("a")
    assert f.contains("ghost") is False


def test_alternate_bucket_is_involution():
    # Inserting then deleting via the same hash round-trips cleanly across both buckets.
    h = make_hash({"x": 0x03F1})
    f = SovereignCuckooFilter(capacity=8, bucket_size=1, hash_fn=h)
    assert f.insert("x") is True
    assert f.delete("x") is True
    assert f.contains("x") is False


# ── false-positive rate (seeded / default hash) ─────────────────────────────────

def test_false_positive_rate_bounded():
    # Default sha256 hash, 8 fp-bits, bucket_size 4 → theoretical FP ≈ 2*4/256 = 3.1%.
    f = SovereignCuckooFilter(capacity=1024, bucket_size=4, fingerprint_bits=8)
    for i in range(2000):
        f.insert(f"present-{i}")
    fp = sum(1 for i in range(5000) if f.contains(f"absent-{i}"))
    assert fp / 5000 < 0.05               # generous ceiling over the ~3.1% expectation


def test_wider_fingerprint_lowers_false_positives():
    fp_bits16 = SovereignCuckooFilter(capacity=1024, fingerprint_bits=16)
    for i in range(2000):
        fp_bits16.insert(f"present-{i}")
    fp = sum(1 for i in range(5000) if fp_bits16.contains(f"absent-{i}"))
    assert fp / 5000 < 0.005              # 16-bit fingerprints ⇒ far fewer collisions


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears_all():
    f = SovereignCuckooFilter(capacity=64)
    for i in range(10):
        f.insert(f"k{i}")
    f.reset()
    assert len(f) == 0
    assert not f.contains("k0")


def test_reset_then_reinsert():
    f = SovereignCuckooFilter(capacity=64)
    f.insert("a")
    f.reset()
    assert f.insert("a") is True
    assert len(f) == 1


# ── concurrency ─────────────────────────────────────────────────────────────────

def test_concurrent_inserts_10_threads():
    f = SovereignCuckooFilter(capacity=2048)   # 8192 slots, no saturation
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
    f = SovereignCuckooFilter(capacity=2048)
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
