"""Phase 126 — unit tests for SimHashLSH / cosine LSH (pradyos/core/simhash_lsh.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.simhash_lsh import SimHashLSH, SimHashLSHError


def _angled(theta, dim=128):
    v = [0.0] * dim
    v[0] = math.cos(theta)
    v[1] = math.sin(theta)
    return v


# ── cosine estimate ────────────────────────────────────────────────────────────

def test_self_cosine_one():
    lsh = SimHashLSH(dim=128, bands=32, rows=8, seed=0)
    v = _angled(0.3)
    assert abs(lsh.similarity(v, v) - 1.0) < 1e-9


def test_cosine_estimate_accurate():
    lsh = SimHashLSH(dim=128, bands=32, rows=8, seed=0)
    for theta in (0.0, math.pi / 3, math.pi / 2, 2 * math.pi / 3):
        assert abs(lsh.similarity(_angled(0.0), _angled(theta)) - math.cos(theta)) < 0.12


def test_opposite_cosine_near_minus_one():
    lsh = SimHashLSH(dim=128, bands=32, rows=8, seed=0)
    assert lsh.similarity(_angled(0.0), _angled(math.pi)) < -0.85


# ── retrieval ─────────────────────────────────────────────────────────────────────

def test_near_parallel_retrieved():
    lsh = SimHashLSH(dim=128, bands=32, rows=8, seed=0)
    lsh.insert("base", _angled(0.5))
    assert any(c == "base" for c, _ in lsh.query(_angled(0.52)))


def test_orthogonal_excluded_at_threshold():
    lsh = SimHashLSH(dim=128, bands=32, rows=8, seed=0)
    lsh.insert("base", _angled(0.5))
    assert not any(c == "base" for c, _ in lsh.query(_angled(0.5 + math.pi / 2), threshold=0.5))


def test_recall_on_near_duplicates():
    lsh = SimHashLSH(dim=64, bands=20, rows=4, seed=3)
    rng = random.Random(7)
    vecs = {}
    for i in range(200):
        v = [rng.gauss(0, 1) for _ in range(64)]
        vecs[f"v{i}"] = v
        lsh.insert(f"v{i}", v)
    hits = 0
    for i in range(200):
        near = [x + rng.gauss(0, 0.05) for x in vecs[f"v{i}"]]
        if any(c == f"v{i}" for c, _ in lsh.query(near)):
            hits += 1
    assert hits / 200 >= 0.9


def test_query_sorted_desc():
    lsh = SimHashLSH(dim=128, bands=16, rows=2, seed=4)
    lsh.insert("exact", _angled(0.5))
    lsh.insert("close", _angled(0.55))
    lsh.insert("far", _angled(1.2))
    res = lsh.query(_angled(0.5))
    sims = [s for _, s in res]
    assert sims == sorted(sims, reverse=True)


def test_threshold_filters():
    lsh = SimHashLSH(dim=128, bands=16, rows=2, seed=4)
    lsh.insert("x", _angled(0.5))
    near = _angled(0.55)
    assert any(c == "x" for c, _ in lsh.query(near, threshold=0.5))
    assert not any(c == "x" for c, _ in lsh.query(near, threshold=0.999))


def test_empty_query():
    assert SimHashLSH(dim=8, seed=0).query([1, 0, 0, 0, 0, 0, 0, 0]) == []


# ── remove / re-insert ───────────────────────────────────────────────────────────

def test_remove_present():
    lsh = SimHashLSH(dim=8, bands=4, rows=2, seed=0)
    lsh.insert("a", [1, 0, 0, 0, 0, 0, 0, 0])
    assert lsh.remove("a") is True and "a" not in lsh and len(lsh) == 0


def test_remove_absent():
    assert SimHashLSH(dim=8, seed=0).remove("nope") is False


def test_reinsert_replaces():
    lsh = SimHashLSH(dim=8, bands=4, rows=2, seed=0)
    lsh.insert("a", [1, 0, 0, 0, 0, 0, 0, 0])
    lsh.insert("a", [0, 1, 0, 0, 0, 0, 0, 0])
    assert len(lsh) == 1


def test_contains_and_len():
    lsh = SimHashLSH(dim=4, bands=2, rows=2, seed=0)
    lsh.insert("a", [1, 2, 3, 4])
    assert "a" in lsh and len(lsh) == 1 and "z" not in lsh


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic_query():
    rng = random.Random(1)
    x = SimHashLSH(dim=32, bands=8, rows=4, seed=5)
    y = SimHashLSH(dim=32, bands=8, rows=4, seed=5)
    for i in range(50):
        v = [rng.gauss(0, 1) for _ in range(32)]
        x.insert(f"k{i}", v)
        y.insert(f"k{i}", v)
    q = [rng.gauss(0, 1) for _ in range(32)]
    assert x.query(q) == y.query(q)


def test_different_seed_diverges_signature():
    v = [1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0]
    a = SimHashLSH(dim=8, bands=4, rows=2, seed=1)
    b = SimHashLSH(dim=8, bands=4, rows=2, seed=2)
    assert a._signature(v) != b._signature(v)


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_dim_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(dim=0)


def test_invalid_bands_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(bands=0)


def test_invalid_rows_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(rows=0)


def test_invalid_seed_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(seed="nope")


def test_bool_dim_rejected():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(dim=True)


def test_wrong_dimension_vector_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(dim=4, seed=0).insert("a", [1, 2, 3])


def test_non_numeric_vector_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(dim=3, seed=0).insert("a", [1, "two", 3])


def test_query_threshold_out_of_range_raises():
    lsh = SimHashLSH(dim=4, seed=0)
    lsh.insert("a", [1, 2, 3, 4])
    with pytest.raises(SimHashLSHError):
        lsh.query([1, 2, 3, 4], threshold=2.0)


def test_query_threshold_below_minus_one_raises():
    with pytest.raises(SimHashLSHError):
        SimHashLSH(dim=4, seed=0).query([1, 2, 3, 4], threshold=-1.5)


def test_error_stores_detail():
    err = SimHashLSHError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    lsh = SimHashLSH(dim=100, bands=20, rows=5, seed=7)
    assert lsh.dim == 100 and lsh.bands == 20 and lsh.rows == 5
    assert lsh.num_perm == 100 and lsh.seed == 7


def test_stats_keys():
    assert set(SimHashLSH(dim=8, seed=0).stats()) == {
        "num_items", "dim", "bands", "rows", "num_perm", "seed"}


def test_stats_values():
    lsh = SimHashLSH(dim=16, bands=4, rows=4, seed=3)
    lsh.insert("a", [1.0] * 16)
    s = lsh.stats()
    assert s["num_items"] == 1 and s["dim"] == 16 and s["num_perm"] == 16 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    lsh = SimHashLSH(dim=8, bands=4, rows=2, seed=0)
    for i in range(10):
        lsh.insert(f"k{i}", [float(i)] * 8)
    lsh.reset()
    assert len(lsh) == 0


def test_reset_reconfigures():
    lsh = SimHashLSH(dim=8, bands=4, rows=2, seed=0)
    lsh.reset(dim=16, bands=8, rows=2, seed=9)
    assert lsh.dim == 16 and lsh.bands == 8 and lsh.rows == 2 and lsh.num_perm == 16 and lsh.seed == 9


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    lsh = SimHashLSH(dim=16, bands=4, rows=4, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(50):
                lsh.insert(f"t{base}-{i}", [float((base + i) % 7)] * 16)
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(lsh) == 500
