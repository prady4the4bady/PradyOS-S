"""Phase 117 — unit tests for HyperMinHash (pradyos/core/hyper_minhash.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.hyper_minhash import HyperMinHash, HyperMinHashError


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b)


# ── cardinality (HyperLogLog part) ───────────────────────────────────────────────

def test_empty_cardinality_zero():
    assert HyperMinHash(p=10, r=8, seed=0).cardinality() == 0.0


def test_cardinality_small():
    h = HyperMinHash(p=12, r=8, seed=0)
    for i in range(1000):
        h.add(f"e-{i}")
    assert abs(h.cardinality() - 1000) / 1000 < 0.05


def test_cardinality_large():
    h = HyperMinHash(p=12, r=8, seed=0)
    for i in range(10000):
        h.add(f"e-{i}")
    assert abs(h.cardinality() - 10000) / 10000 < 0.05


def test_cardinality_ignores_duplicates():
    h = HyperMinHash(p=12, r=8, seed=0)
    for _ in range(5):
        for i in range(2000):
            h.add(f"d-{i}")
    assert abs(h.cardinality() - 2000) / 2000 < 0.05


def test_add_many():
    h = HyperMinHash(p=12, r=8, seed=0)
    h.add_many(f"e-{i}" for i in range(3000))
    assert abs(h.cardinality() - 3000) / 3000 < 0.05


def test_add_many_non_iterable_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(seed=0).add_many(123)


# ── Jaccard / similarity ─────────────────────────────────────────────────────────

def test_self_jaccard_is_one():
    a = HyperMinHash(p=12, r=8, seed=0)
    b = HyperMinHash(p=12, r=8, seed=0)
    a.add_many(range(5000))
    b.add_many(range(5000))
    assert abs(a.jaccard(b) - 1.0) < 1e-9


def test_disjoint_jaccard_near_zero():
    a = HyperMinHash(p=12, r=8, seed=0)
    b = HyperMinHash(p=12, r=8, seed=0)
    a.add_many(range(5000))
    b.add_many(range(10000, 15000))
    assert a.jaccard(b) < 0.02


def test_jaccard_accurate_across_overlaps():
    A = set(range(10000))
    for B in (set(range(2000, 12000)), set(range(5000, 15000)), set(range(9000, 19000))):
        ha = HyperMinHash(p=12, r=8, seed=0)
        hb = HyperMinHash(p=12, r=8, seed=0)
        ha.add_many(A)
        hb.add_many(B)
        assert abs(ha.jaccard(hb) - _jaccard(A, B)) < 0.10


def test_jaccard_symmetric():
    a = HyperMinHash(p=12, r=8, seed=0)
    b = HyperMinHash(p=12, r=8, seed=0)
    a.add_many(range(10000))
    b.add_many(range(5000, 15000))
    assert abs(a.jaccard(b) - b.jaccard(a)) < 1e-9


# ── union / intersection / merge ─────────────────────────────────────────────────

def test_union_cardinality():
    a = HyperMinHash(p=12, r=8, seed=0)
    b = HyperMinHash(p=12, r=8, seed=0)
    a.add_many(range(10000))
    b.add_many(range(5000, 15000))
    assert abs(a.union_cardinality(b) - 15000) / 15000 < 0.06


def test_intersection_cardinality():
    a = HyperMinHash(p=12, r=8, seed=0)
    b = HyperMinHash(p=12, r=8, seed=0)
    a.add_many(range(10000))
    b.add_many(range(5000, 15000))
    assert abs(a.intersection_cardinality(b) - 5000) / 5000 < 0.20


def test_merge_is_union():
    a = HyperMinHash(p=12, r=8, seed=0)
    b = HyperMinHash(p=12, r=8, seed=0)
    a.add_many(range(10000))
    b.add_many(range(8000, 18000))         # union = 18000
    merged = a.merge(b)
    assert abs(merged.cardinality() - 18000) / 18000 < 0.06


def test_merge_equivalent_to_combined_adds():
    a = HyperMinHash(p=10, r=8, seed=0)
    b = HyperMinHash(p=10, r=8, seed=0)
    a.add_many(range(3000))
    b.add_many(range(2000, 5000))
    merged = a.merge(b)
    direct = HyperMinHash(p=10, r=8, seed=0)
    direct.add_many(range(5000))
    assert merged._ranks == direct._ranks   # bucketwise max rank matches the union sketch


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_seed():
    a = HyperMinHash(p=10, r=8, seed=5)
    b = HyperMinHash(p=10, r=8, seed=5)
    for i in range(5000):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a._ranks == b._ranks and a._mantissas == b._mantissas
    assert a.cardinality() == b.cardinality()


def test_different_seed_diverges():
    a = HyperMinHash(p=10, r=8, seed=1)
    b = HyperMinHash(p=10, r=8, seed=2)
    for i in range(5000):
        a.add(f"k{i}")
        b.add(f"k{i}")
    assert a._ranks != b._ranks


# ── compatibility / validation ──────────────────────────────────────────────────

def test_incompatible_p_raises():
    a = HyperMinHash(p=10, seed=0)
    b = HyperMinHash(p=12, seed=0)
    with pytest.raises(HyperMinHashError):
        a.jaccard(b)


def test_incompatible_seed_raises():
    a = HyperMinHash(p=10, seed=0)
    b = HyperMinHash(p=10, seed=1)
    with pytest.raises(HyperMinHashError):
        a.merge(b)


def test_jaccard_non_sketch_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(seed=0).jaccard("not a sketch")


def test_invalid_p_low_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(p=3)


def test_invalid_p_high_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(p=21)


def test_invalid_r_low_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(r=0)


def test_invalid_r_high_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(r=9)


def test_invalid_seed_raises():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(seed="nope")


def test_bool_p_rejected():
    with pytest.raises(HyperMinHashError):
        HyperMinHash(p=True)


def test_error_stores_detail():
    err = HyperMinHashError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    h = HyperMinHash(p=10, r=6, seed=7)
    assert h.p == 10 and h.r == 6 and h.num_buckets == 1024 and h.seed == 7


def test_stats_keys():
    assert set(HyperMinHash(p=8, seed=0).stats()) == {
        "p", "r", "num_buckets", "filled", "cardinality", "seed"}


def test_stats_values():
    h = HyperMinHash(p=10, r=8, seed=3)
    for i in range(500):
        h.add(f"k{i}")
    s = h.stats()
    assert s["p"] == 10 and s["num_buckets"] == 1024 and s["filled"] > 0 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    h = HyperMinHash(p=10, r=8, seed=0)
    for i in range(1000):
        h.add(f"k{i}")
    h.reset()
    assert h.cardinality() == 0.0 and h.stats()["filled"] == 0


def test_reset_reconfigures():
    h = HyperMinHash(p=10, r=8, seed=0)
    h.reset(p=12, r=4, seed=9)
    assert h.p == 12 and h.r == 4 and h.num_buckets == 4096 and h.seed == 9


def test_reset_invalid_raises():
    h = HyperMinHash(p=10, seed=0)
    with pytest.raises(HyperMinHashError):
        h.reset(p=2)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    h = HyperMinHash(p=12, r=8, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(500):
                h.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert abs(h.cardinality() - 5000) / 5000 < 0.05
