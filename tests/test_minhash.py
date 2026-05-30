"""Phase 88 — unit tests for MinHash (pradyos/core/minhash.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.minhash import MinHash, MinHashError, _MERSENNE


def true_jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else 0.0


# ── basic structure ──────────────────────────────────────────────────────────────

def test_add_single_creates_set():
    m = MinHash(num_hashes=16)
    m.add("S", "x")
    assert "S" in m


def test_sets_are_listed_sorted():
    m = MinHash(num_hashes=16)
    m.add("b", 1)
    m.add("a", 1)
    assert m.sets() == ["a", "b"]


def test_signature_length_equals_num_hashes():
    m = MinHash(num_hashes=32)
    m.add("S", "x")
    assert len(m.signature("S")) == 32


def test_signature_missing_is_none():
    assert MinHash(num_hashes=16).signature("nope") is None


def test_len_tracks_set_count():
    m = MinHash(num_hashes=16)
    m.add_many("a", [1, 2])
    m.add_many("b", [3])
    assert len(m) == 2


def test_contains_dunder():
    m = MinHash(num_hashes=16)
    m.add("present", 1)
    assert "present" in m and "absent" not in m


def test_add_many_returns_count():
    m = MinHash(num_hashes=16)
    assert m.add_many("S", [1, 2, 3, 4]) == 4


# ── similarity correctness ───────────────────────────────────────────────────────

def test_self_similarity_is_one():
    m = MinHash(num_hashes=64, seed=0)
    m.add_many("S", range(50))
    assert m.similarity("S", "S") == 1.0


def test_identical_content_similarity_one():
    m = MinHash(num_hashes=64, seed=0)
    m.add_many("A", range(50))
    m.add_many("B", range(50))
    assert m.similarity("A", "B") == 1.0


def test_disjoint_similarity_near_zero():
    m = MinHash(num_hashes=256, seed=3)
    m.add_many("L", range(0, 500))
    m.add_many("R", range(10_000, 10_500))
    assert m.similarity("L", "R") < 0.05


def test_missing_set_similarity_zero():
    m = MinHash(num_hashes=64)
    m.add("S", 1)
    assert m.similarity("S", "ghost") == 0.0


def test_both_missing_similarity_zero():
    assert MinHash(num_hashes=64).similarity("x", "y") == 0.0


def test_similarity_is_symmetric():
    m = MinHash(num_hashes=128, seed=1)
    m.add_many("A", range(0, 300))
    m.add_many("B", range(150, 450))
    assert m.similarity("A", "B") == m.similarity("B", "A")


def test_partial_overlap_estimate_close():
    m = MinHash(num_hashes=256, seed=7)
    A, B = set(range(0, 600)), set(range(300, 900))   # true Jaccard = 300/900 = 1/3
    m.add_many("A", A)
    m.add_many("B", B)
    assert abs(m.similarity("A", "B") - true_jaccard(A, B)) < 0.08


def test_accuracy_mean_error_bounded():
    rnd = random.Random(1)
    errs = []
    for _ in range(15):
        A = set(rnd.sample(range(2000), 500))
        B = set(rnd.sample(range(2000), 500))
        m = MinHash(num_hashes=256, seed=7)
        m.add_many("A", A)
        m.add_many("B", B)
        errs.append(abs(m.similarity("A", "B") - true_jaccard(A, B)))
    assert sum(errs) / len(errs) < 0.05


# ── determinism & injectable seed ────────────────────────────────────────────────

def test_same_seed_same_signature():
    a = MinHash(num_hashes=64, seed=42)
    b = MinHash(num_hashes=64, seed=42)
    a.add_many("x", range(100))
    b.add_many("x", range(100))
    assert a.signature("x") == b.signature("x")


def test_signature_order_independent():
    a = MinHash(num_hashes=64, seed=42)
    b = MinHash(num_hashes=64, seed=42)
    els = list(range(100))
    shuf = els[:]
    random.Random(9).shuffle(shuf)
    a.add_many("x", els)
    b.add_many("x", shuf)
    assert a.signature("x") == b.signature("x")


def test_different_seed_differs():
    a = MinHash(num_hashes=64, seed=1)
    b = MinHash(num_hashes=64, seed=2)
    a.add_many("x", range(100))
    b.add_many("x", range(100))
    assert a.signature("x") != b.signature("x")


def test_idempotent_readd():
    m = MinHash(num_hashes=64, seed=5)
    m.add_many("q", [1, 2, 3])
    before = m.signature("q")
    m.add("q", 2)
    m.add("q", 1)
    assert m.signature("q") == before


def test_deterministic_similarity_reproducible():
    a = MinHash(num_hashes=128, seed=99)
    b = MinHash(num_hashes=128, seed=99)
    for mh in (a, b):
        mh.add_many("A", range(0, 400))
        mh.add_many("B", range(200, 600))
    assert a.similarity("A", "B") == b.similarity("A", "B")


# ── sum-of-minima invariant / range ──────────────────────────────────────────────

def test_sum_of_minima_monotone_non_increasing():
    m = MinHash(num_hashes=128, seed=11)
    sums = []
    for e in range(200):
        m.add("m", e)
        sums.append(sum(m.signature("m")))
    assert all(sums[i + 1] <= sums[i] for i in range(len(sums) - 1))


def test_adding_element_only_lowers_or_keeps_signature():
    m = MinHash(num_hashes=64, seed=2)
    m.add_many("s", range(20))
    before = m.signature("s")
    m.add("s", 999)
    after = m.signature("s")
    assert all(after[i] <= before[i] for i in range(len(before)))


def test_signature_values_within_modulus():
    m = MinHash(num_hashes=64, seed=4)
    m.add_many("s", range(100))
    assert all(0 <= v < _MERSENNE for v in m.signature("s"))


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_num_hashes_is_128():
    assert MinHash().num_hashes == 128


def test_num_hashes_configurable():
    assert MinHash(num_hashes=64).num_hashes == 64


def test_invalid_num_hashes_zero_raises():
    with pytest.raises(MinHashError):
        MinHash(num_hashes=0)


def test_invalid_num_hashes_negative_raises():
    with pytest.raises(MinHashError):
        MinHash(num_hashes=-8)


def test_invalid_num_hashes_bool_raises():
    with pytest.raises(MinHashError):
        MinHash(num_hashes=True)


def test_invalid_num_hashes_float_raises():
    with pytest.raises(MinHashError):
        MinHash(num_hashes=2.5)


def test_invalid_seed_float_raises():
    with pytest.raises(MinHashError):
        MinHash(num_hashes=16, seed=1.5)


def test_invalid_seed_bool_raises():
    with pytest.raises(MinHashError):
        MinHash(num_hashes=16, seed=True)


def test_negative_seed_allowed():
    assert MinHash(num_hashes=16, seed=-7).seed == -7


def test_minhash_error_stores_detail():
    err = MinHashError(-3)
    assert err.detail == -3
    assert "invalid minhash configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(MinHash(num_hashes=16).stats()) == {"num_hashes", "sets", "total_added", "seed"}


def test_stats_initial():
    assert MinHash(num_hashes=16, seed=2).stats() == {
        "num_hashes": 16, "sets": 0, "total_added": 0, "seed": 2,
    }


def test_stats_tracks_sets_and_total():
    m = MinHash(num_hashes=16)
    m.add_many("a", [1, 2, 3])
    m.add_many("b", [4])
    st = m.stats()
    assert st["sets"] == 2 and st["total_added"] == 4


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    m = MinHash(num_hashes=16)
    m.add_many("a", [1, 2])
    m.reset()
    assert len(m) == 0 and m.stats()["total_added"] == 0


def test_reset_reconfigures_num_hashes():
    m = MinHash(num_hashes=16)
    m.reset(num_hashes=32)
    m.add("s", "x")
    assert m.num_hashes == 32 and len(m.signature("s")) == 32


def test_reset_reconfigures_seed():
    m = MinHash(num_hashes=16, seed=1)
    m.reset(seed=2)
    assert m.seed == 2


def test_reset_invalid_num_hashes_raises():
    m = MinHash(num_hashes=16)
    with pytest.raises(MinHashError):
        m.reset(num_hashes=0)


def test_reset_then_reuse():
    m = MinHash(num_hashes=32, seed=0)
    m.add_many("a", range(10))
    m.reset()
    m.add_many("a", range(10))
    m.add_many("b", range(10))
    assert m.similarity("a", "b") == 1.0


# ── item types & concurrency ─────────────────────────────────────────────────────

def test_mixed_element_types():
    m = MinHash(num_hashes=64, seed=0)
    m.add_many("A", ["x", 1, ("t", 2)])
    m.add_many("B", ["x", 1, ("t", 2)])
    assert m.similarity("A", "B") == 1.0


def test_concurrent_adds_10_threads():
    m = MinHash(num_hashes=64, seed=0)
    errors = []

    def worker(tag):
        try:
            for i in range(100):
                m.add(f"set{tag}", i)
        except Exception as exc:        # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(m) == 10
    assert m.stats()["total_added"] == 1000


def test_concurrent_same_set_consistent_signature():
    # All threads add the SAME elements to ONE set; the min-signature is
    # order-independent, so it must equal the single-threaded result.
    ref = MinHash(num_hashes=64, seed=0)
    ref.add_many("s", range(200))

    m = MinHash(num_hashes=64, seed=0)
    errors = []

    def worker():
        try:
            for i in range(200):
                m.add("s", i)
        except Exception as exc:        # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert m.signature("s") == ref.signature("s")
