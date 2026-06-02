"""Phase 122 — unit tests for BBitMinHash (pradyos/core/bbit_minhash.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.bbit_minhash import BBitMinHash, BBitMinHashError, estimate_jaccard


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b)


def _sketch(items, num_perm=512, b=4, seed=0):
    s = BBitMinHash(num_perm=num_perm, b=b, seed=seed)
    s.add_many(items)
    return s


# ── similarity ─────────────────────────────────────────────────────────────────

def test_self_jaccard_is_one():
    assert abs(_sketch(range(1000)).jaccard(_sketch(range(1000))) - 1.0) < 1e-9


def test_disjoint_jaccard_near_zero():
    assert _sketch(range(1000)).jaccard(_sketch(range(5000, 6000))) < 0.05


def test_jaccard_accurate_across_overlaps():
    A = set(range(1000))
    for B in (set(range(200, 1200)), set(range(500, 1500)), set(range(900, 1900))):
        est = _sketch(A).jaccard(_sketch(B))
        assert abs(est - _jaccard(A, B)) < 0.08


def test_jaccard_symmetric():
    A, B = set(range(1000)), set(range(400, 1400))
    assert abs(_sketch(A).jaccard(_sketch(B)) - _sketch(B).jaccard(_sketch(A))) < 1e-9


def test_larger_b_lowers_error():
    def mean_err(b):
        A, B = set(range(1000)), set(range(500, 1500))
        tj = _jaccard(A, B)
        return sum(abs(_sketch(A, 256, b, s).jaccard(_sketch(B, 256, b, s)) - tj)
                   for s in range(15)) / 15
    assert mean_err(8) <= mean_err(1) + 0.01


# ── signature ────────────────────────────────────────────────────────────────────

def test_signature_length():
    s = BBitMinHash(num_perm=128, b=3, seed=0)
    s.add_many(range(500))
    assert len(s.signature()) == 128


def test_signature_values_in_range():
    s = BBitMinHash(num_perm=128, b=3, seed=0)
    s.add_many(range(500))
    assert all(0 <= v < 8 for v in s.signature())


def test_signature_bits():
    assert BBitMinHash(num_perm=128, b=3, seed=0).signature_bits() == 384


def test_empty_signature_length():
    assert len(BBitMinHash(num_perm=64, b=2, seed=0).signature()) == 64


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic_signature():
    a = BBitMinHash(num_perm=128, b=4, seed=5)
    b = BBitMinHash(num_perm=128, b=4, seed=5)
    a.add_many(range(300))
    b.add_many(range(300))
    assert a.signature() == b.signature()


def test_different_seed_diverges():
    a = BBitMinHash(num_perm=128, b=4, seed=1)
    b = BBitMinHash(num_perm=128, b=4, seed=2)
    a.add_many(range(300))
    b.add_many(range(300))
    assert a.signature() != b.signature()


def test_order_independent():
    items = list(range(500))
    random.Random(1).shuffle(items)
    a = BBitMinHash(num_perm=128, b=4, seed=0)
    a.add_many(items)
    b = BBitMinHash(num_perm=128, b=4, seed=0)
    b.add_many(range(500))
    assert a.signature() == b.signature()


def test_add_many_equals_repeated_add():
    x = BBitMinHash(num_perm=64, b=4, seed=0)
    x.add_many(range(200))
    y = BBitMinHash(num_perm=64, b=4, seed=0)
    for i in range(200):
        y.add(i)
    assert x.signature() == y.signature() and len(x) == 200


def test_add_many_non_iterable_raises():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(seed=0).add_many(123)


# ── estimate_jaccard helper ───────────────────────────────────────────────────────

def test_estimate_jaccard_identical():
    a = BBitMinHash(num_perm=128, b=4, seed=0)
    a.add_many(range(300))
    assert abs(estimate_jaccard(a.signature(), a.signature(), 4) - 1.0) < 1e-9


def test_estimate_jaccard_mismatched_length_raises():
    with pytest.raises(BBitMinHashError):
        estimate_jaccard((1, 2, 3), (1, 2), 4)


def test_estimate_jaccard_empty_raises():
    with pytest.raises(BBitMinHashError):
        estimate_jaccard((), (), 4)


def test_estimate_jaccard_bad_b_raises():
    with pytest.raises(BBitMinHashError):
        estimate_jaccard((1, 2), (1, 2), 0)


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_num_perm_raises():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(num_perm=0)


def test_invalid_b_zero_raises():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(b=0)


def test_invalid_b_too_large_raises():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(b=33)


def test_invalid_seed_raises():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(seed="nope")


def test_bool_num_perm_rejected():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(num_perm=True)


def test_incompatible_jaccard_raises():
    a = BBitMinHash(num_perm=64, b=4, seed=0)
    b = BBitMinHash(num_perm=128, b=4, seed=0)
    with pytest.raises(BBitMinHashError):
        a.jaccard(b)


def test_jaccard_non_sketch_raises():
    with pytest.raises(BBitMinHashError):
        BBitMinHash(seed=0).jaccard("not a sketch")


def test_error_stores_detail():
    err = BBitMinHashError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    s = BBitMinHash(num_perm=256, b=2, seed=7)
    assert s.num_perm == 256 and s.b == 2 and s.seed == 7


def test_count_tracks_adds():
    s = BBitMinHash(num_perm=64, b=2, seed=0)
    s.add_many(range(100))
    assert s.count == 100 and len(s) == 100


def test_stats_keys():
    assert set(BBitMinHash(seed=0).stats()) == {
        "num_perm", "b", "count", "signature_bits", "seed"}


def test_stats_values():
    s = BBitMinHash(num_perm=128, b=2, seed=3)
    s.add_many(range(50))
    st = s.stats()
    assert st["num_perm"] == 128 and st["b"] == 2 and st["count"] == 50
    assert st["signature_bits"] == 256 and st["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = BBitMinHash(num_perm=128, b=4, seed=0)
    s.add_many(range(300))
    s.reset()
    assert len(s) == 0 and len(s.signature()) == 128


def test_reset_reconfigures():
    s = BBitMinHash(num_perm=128, b=4, seed=0)
    s.reset(num_perm=256, b=2, seed=9)
    assert s.num_perm == 256 and s.b == 2 and s.seed == 9 and len(s) == 0


def test_reset_invalid_raises():
    s = BBitMinHash(seed=0)
    with pytest.raises(BBitMinHashError):
        s.reset(b=99)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    s = BBitMinHash(num_perm=128, b=4, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(200):
                s.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(s) == 2000 and len(s.signature()) == 128
