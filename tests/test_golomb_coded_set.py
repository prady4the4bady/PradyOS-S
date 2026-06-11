"""Phase 128 — unit tests for GolombCodedSet (pradyos/core/golomb_coded_set.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.golomb_coded_set import (
    GolombCodedSet,
    GolombCodedSetError,
    _BitReader,
    _BitWriter,
)


def _members(n, tag="m", seed=1):
    rng = random.Random(seed)
    return [f"{tag}-{i}-{rng.random():.9f}" for i in range(n)]


# ── membership correctness ───────────────────────────────────────────────────────────

def test_all_members_present():
    items = _members(2000)
    gcs = GolombCodedSet(items, p=0.01, seed=7)
    assert all(gcs.contains(m) for m in items)          # zero false negatives — exact


def test_false_positive_rate_near_p():
    gcs = GolombCodedSet(_members(1500), p=0.02, seed=7)
    rng = random.Random(99)
    trials = 15000
    fp = sum(1 for _ in range(trials) if gcs.contains(f"absent-{rng.random():.9f}"))
    assert fp / trials <= 1.5 * 0.02                     # measured FP within 1.5×target


def test_empty_set_contains_false():
    gcs = GolombCodedSet([], p=0.01, seed=0)
    assert len(gcs) == 0
    assert not gcs.contains("anything")


def test_single_item():
    gcs = GolombCodedSet(["solo"], p=0.01, seed=0)
    assert gcs.contains("solo") and len(gcs) == 1


def test_contains_dunder():
    gcs = GolombCodedSet(["a", "b", "c"], p=0.01, seed=0)
    assert "a" in gcs


def test_build_replaces_contents():
    gcs = GolombCodedSet(_members(800, tag="A"), p=0.01, seed=3)
    new = _members(800, tag="B")
    gcs.build(new)
    assert all(gcs.contains(m) for m in new)             # all new present (no false negatives)
    assert len(gcs) <= 800                               # distinct fingerprints (collisions only reduce)


def test_duplicates_collapse():
    # Tiny p ⇒ vast universe ⇒ no fingerprint self-collisions, so only exact dups collapse.
    gcs = GolombCodedSet(["x", "x", "x", "y"], p=1e-6, seed=0)
    assert gcs.contains("x") and gcs.contains("y")
    assert len(gcs) == 2                                 # distinct fingerprints only


def test_fingerprint_collisions_only_reduce_count():
    # num_items is the count of distinct fingerprints, so self-collisions can shrink it
    # below the input size — but never grow it, and never cause a false negative.
    items = _members(2000)
    gcs = GolombCodedSet(items, p=0.01, seed=7)
    assert len(gcs) <= 2000 and all(gcs.contains(m) for m in items)


# ── Golomb codec (encode/decode round-trip) ──────────────────────────────────────────

@pytest.mark.parametrize("m", [1, 2, 3, 4, 5, 7, 8, 13, 64, 69, 1000])
def test_codec_roundtrips_exactly(m):
    rng = random.Random(m)
    gaps = [rng.randint(1, 4000) for _ in range(1500)]
    w = _BitWriter()
    for g in gaps:
        GolombCodedSet._encode_gap(w, g, m)
    payload, nbits = w.finish()
    r = _BitReader(payload, nbits)
    out = [GolombCodedSet._decode_gap(r, m) for _ in range(len(gaps))]
    assert out == gaps
    assert r.pos == nbits                                # consumed exactly, no padding misread


def test_codec_m_one_is_unary():
    w = _BitWriter()
    for g in (1, 5, 10):
        GolombCodedSet._encode_gap(w, g, 1)
    payload, nbits = w.finish()
    r = _BitReader(payload, nbits)
    assert [GolombCodedSet._decode_gap(r, 1) for _ in range(3)] == [1, 5, 10]


def test_bit_reader_exhaustion_raises():
    r = _BitReader(b"\x00", 2)
    r.read_bit(); r.read_bit()
    with pytest.raises(GolombCodedSetError):
        r.read_bit()


# ── determinism ──────────────────────────────────────────────────────────────────────

def test_same_seed_identical_num_bits():
    items = _members(1000)
    a = GolombCodedSet(items, p=0.01, seed=5)
    b = GolombCodedSet(items, p=0.01, seed=5)
    assert a.num_bits == b.num_bits


def test_same_seed_identical_membership():
    items = _members(500)
    a = GolombCodedSet(items, p=0.01, seed=5)
    b = GolombCodedSet(items, p=0.01, seed=5)
    assert all(a.contains(m) == b.contains(m) for m in items)


def test_different_seed_diverges():
    items = _members(1000)
    a = GolombCodedSet(items, p=0.01, seed=5)
    c = GolombCodedSet(items, p=0.01, seed=6)
    assert a.num_bits != c.num_bits                      # different fingerprints → different gaps


# ── compression ───────────────────────────────────────────────────────────────────────

def test_bits_per_item_beats_bloom():
    gcs = GolombCodedSet(_members(4000), p=0.01, seed=7)
    bloom = 1.44 * math.log2(1.0 / 0.01)
    assert gcs.bits_per_item() < bloom                   # GCS is more compact than a Bloom filter


def test_bits_per_item_above_info_floor():
    gcs = GolombCodedSet(_members(4000), p=0.01, seed=7)
    assert gcs.bits_per_item() >= math.log2(1.0 / 0.01)  # cannot beat the entropy floor


def test_smaller_p_uses_more_bits():
    items = _members(2000)
    loose = GolombCodedSet(items, p=0.05, seed=7)
    tight = GolombCodedSet(items, p=0.001, seed=7)
    assert tight.bits_per_item() > loose.bits_per_item()


def test_universe_is_ceil_n_over_p():
    items = _members(1000)
    gcs = GolombCodedSet(items, p=0.01, seed=7)
    assert gcs.universe == math.ceil(len(items) / 0.01)


def test_golomb_m_is_optimal():
    gcs = GolombCodedSet(_members(2000), p=0.01, seed=7)
    expected = max(1, round(math.log(2.0) * gcs.universe / gcs.num_items))
    assert gcs.golomb_m == expected


# ── type handling ─────────────────────────────────────────────────────────────────────

def test_str_bytes_int_accepted():
    gcs = GolombCodedSet(["text", b"raw", 42], p=0.01, seed=0)
    assert gcs.contains("text") and gcs.contains(b"raw") and gcs.contains(42)


def test_type_tagging_avoids_alias():
    # int 1, str "1" and bytes b"1" must encode to distinct fingerprint inputs.
    assert GolombCodedSet._to_bytes(1) != GolombCodedSet._to_bytes("1")
    assert GolombCodedSet._to_bytes("1") != GolombCodedSet._to_bytes(b"1")
    assert GolombCodedSet._to_bytes(1) != GolombCodedSet._to_bytes(b"1")


def test_bool_item_rejected():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([True], p=0.01, seed=0)


def test_float_item_rejected():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([3.14], p=0.01, seed=0)


def test_non_iterable_items_rejected():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet(12345, p=0.01, seed=0)            # int is not an item iterable here


# ── validation ────────────────────────────────────────────────────────────────────────

def test_invalid_p_zero():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([], p=0.0, seed=0)


def test_invalid_p_one():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([], p=1.0, seed=0)


def test_invalid_p_negative():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([], p=-0.1, seed=0)


def test_invalid_p_type():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([], p="small", seed=0)


def test_invalid_seed_type():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([], p=0.01, seed="zero")


def test_bool_seed_rejected():
    with pytest.raises(GolombCodedSetError):
        GolombCodedSet([], p=0.01, seed=True)


def test_error_stores_detail():
    err = GolombCodedSetError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── reset ──────────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    gcs = GolombCodedSet(_members(500), p=0.01, seed=0)
    gcs.reset()
    assert len(gcs) == 0 and not gcs.contains("m-0-anything")


def test_reset_reconfigures():
    gcs = GolombCodedSet([], p=0.01, seed=0)
    gcs.reset(p=0.05, seed=9)
    assert gcs.p == 0.05 and gcs.seed == 9


def test_reset_invalid_raises():
    gcs = GolombCodedSet([], p=0.01, seed=0)
    with pytest.raises(GolombCodedSetError):
        gcs.reset(p=2.0)


# ── introspection ─────────────────────────────────────────────────────────────────────

def test_len_counts_distinct():
    # Vast universe (tiny p) ⇒ distinct inputs hash to distinct fingerprints.
    gcs = GolombCodedSet(_members(50), p=1e-6, seed=0)
    assert len(gcs) == 50


def test_stats_keys():
    assert set(GolombCodedSet([], p=0.01, seed=0).stats()) == {
        "p", "num_items", "universe", "golomb_m", "num_bits", "bits_per_item", "seed"}


def test_properties():
    gcs = GolombCodedSet(_members(50), p=1e-6, seed=4)
    assert gcs.p == 1e-6 and gcs.seed == 4 and gcs.num_items == 50
    assert gcs.golomb_m >= 1 and gcs.num_bits > 0


# ── concurrency ───────────────────────────────────────────────────────────────────────

def test_concurrent_contains():
    items = _members(1000)
    gcs = GolombCodedSet(items, p=0.01, seed=0)
    errors = []
    results = []

    def worker():
        try:
            results.append(all(gcs.contains(m) for m in items[:100]))
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and all(results) and len(results) == 10
