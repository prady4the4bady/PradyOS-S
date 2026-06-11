"""Phase 124 — unit tests for JumpHash (pradyos/core/jump_hash.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.jump_hash import JumpHash, JumpHashError, jump_consistent_hash


# ── core algorithm ─────────────────────────────────────────────────────────────

def test_core_in_range():
    for n in (1, 2, 10, 1000):
        assert all(0 <= jump_consistent_hash(h, n) < n for h in range(0, 100000, 997))


def test_core_single_bucket():
    assert all(jump_consistent_hash(h, 1) == 0 for h in range(0, 100000, 311))


def test_core_monotone_growth():
    # For a fixed key, increasing num_buckets only ever moves it to a larger bucket id.
    seq = [jump_consistent_hash(123456789, n) for n in range(1, 300)]
    assert all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))


def test_core_invalid_buckets_raises():
    with pytest.raises(JumpHashError):
        jump_consistent_hash(123, 0)


# ── assignment ─────────────────────────────────────────────────────────────────

def test_assign_deterministic():
    j = JumpHash(num_buckets=10, seed=0)
    assert all(j.assign(f"k{i}") == j.assign(f"k{i}") for i in range(2000))


def test_assign_in_range():
    j = JumpHash(num_buckets=16, seed=0)
    assert all(0 <= j.assign(f"k{i}") < 16 for i in range(2000))


def test_single_bucket_all_zero():
    j = JumpHash(num_buckets=1, seed=0)
    assert all(j.assign(f"k{i}") == 0 for i in range(1000))


def test_numeric_keys():
    j = JumpHash(num_buckets=8, seed=0)
    assert all(0 <= j.assign(i) < 8 for i in range(1000))


def test_assign_for_matches_assign():
    j = JumpHash(num_buckets=8, seed=0)
    assert all(j.assign_for(f"k{i}", 8) == j.assign(f"k{i}") for i in range(1000))


def test_assign_for_does_not_change_state():
    j = JumpHash(num_buckets=8, seed=0)
    j.assign_for("k", 99)
    assert j.num_buckets == 8


# ── uniform load ─────────────────────────────────────────────────────────────────

def test_uniform_load():
    j = JumpHash(num_buckets=10, seed=0)
    dist = j.load_distribution([f"key-{i}" for i in range(20000)])
    exp = 20000 / 10
    assert len(dist) == 10
    assert max(abs(c - exp) / exp for c in dist.values()) < 0.10


# ── minimal disruption ───────────────────────────────────────────────────────────

def test_minimal_disruption_moves_to_new_bucket():
    j = JumpHash(num_buckets=10, seed=0)
    keys = [f"k{i}" for i in range(20000)]
    before = {k: j.assign(k) for k in keys}
    j.add_bucket()
    after = {k: j.assign(k) for k in keys}
    moved = [k for k in keys if before[k] != after[k]]
    assert all(after[k] == 10 for k in moved)               # only into the new bucket
    assert all(after[k] == before[k] for k in keys if after[k] != 10)


def test_disruption_fraction():
    j = JumpHash(num_buckets=10, seed=0)
    keys = [f"k{i}" for i in range(20000)]
    before = {k: j.assign(k) for k in keys}
    j.add_bucket()
    moved = sum(1 for k in keys if before[k] != j.assign(k))
    assert 0.07 < moved / 20000 < 0.11                       # ~1/11


# ── determinism ──────────────────────────────────────────────────────────────────

def test_same_seed_deterministic():
    x = JumpHash(num_buckets=8, seed=7)
    y = JumpHash(num_buckets=8, seed=7)
    assert all(x.assign(f"k{i}") == y.assign(f"k{i}") for i in range(3000))


def test_different_seed_diverges():
    x = JumpHash(num_buckets=8, seed=7)
    z = JumpHash(num_buckets=8, seed=8)
    assert any(x.assign(f"k{i}") != z.assign(f"k{i}") for i in range(3000))


# ── bucket management ──────────────────────────────────────────────────────────────

def test_add_bucket():
    j = JumpHash(num_buckets=5, seed=0)
    assert j.add_bucket() == 6 and j.num_buckets == 6


def test_remove_bucket():
    j = JumpHash(num_buckets=5, seed=0)
    assert j.remove_bucket() == 4 and j.num_buckets == 4


def test_cannot_remove_last_bucket():
    j = JumpHash(num_buckets=1, seed=0)
    with pytest.raises(JumpHashError):
        j.remove_bucket()


def test_set_buckets():
    j = JumpHash(num_buckets=5, seed=0)
    j.set_buckets(20)
    assert j.num_buckets == 20


def test_set_buckets_invalid_raises():
    j = JumpHash(num_buckets=5, seed=0)
    with pytest.raises(JumpHashError):
        j.set_buckets(0)


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_num_buckets_raises():
    with pytest.raises(JumpHashError):
        JumpHash(num_buckets=0)


def test_invalid_seed_raises():
    with pytest.raises(JumpHashError):
        JumpHash(seed="nope")


def test_bool_num_buckets_rejected():
    with pytest.raises(JumpHashError):
        JumpHash(num_buckets=True)


def test_assign_for_invalid_raises():
    with pytest.raises(JumpHashError):
        JumpHash(num_buckets=5, seed=0).assign_for("k", 0)


def test_error_stores_detail():
    err = JumpHashError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    j = JumpHash(num_buckets=42, seed=7)
    assert j.num_buckets == 42 and j.seed == 7


def test_stats():
    assert JumpHash(num_buckets=12, seed=3).stats() == {"num_buckets": 12, "seed": 3}


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_reconfigures():
    j = JumpHash(num_buckets=5, seed=0)
    j.reset(num_buckets=20, seed=9)
    assert j.num_buckets == 20 and j.seed == 9


def test_reset_invalid_raises():
    j = JumpHash(num_buckets=5, seed=0)
    with pytest.raises(JumpHashError):
        j.reset(num_buckets=0)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_assigns():
    j = JumpHash(num_buckets=16, seed=0)
    errors = []
    out = []

    def worker():
        try:
            for i in range(500):
                out.append(j.assign(f"k{i}"))
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert all(0 <= v < 16 for v in out)
