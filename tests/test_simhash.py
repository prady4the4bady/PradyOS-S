"""Phase 89 — unit tests for SimHash (pradyos/core/simhash.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.simhash import NEAR_DUPLICATE_HAMMING, SimHash, SimHashError


def make_doc(n=600, prefix="word"):
    """A deterministic bag of ``n`` distinct tokens (large enough that a 1–2 token
    edit stays within the near-duplicate Hamming threshold)."""
    return [f"{prefix}{i}" for i in range(n)]


# ── basic structure ──────────────────────────────────────────────────────────────

def test_hash_returns_int_fingerprint():
    s = SimHash(num_bits=64)
    fp = s.hash("d", ["a", "b", "c"])
    assert isinstance(fp, int)


def test_hash_stores_document():
    s = SimHash(num_bits=64)
    s.hash("d", ["a"])
    assert "d" in s


def test_fingerprint_missing_is_none():
    assert SimHash(num_bits=64).fingerprint("nope") is None


def test_documents_listed_sorted():
    s = SimHash(num_bits=64)
    s.hash("b", ["x"])
    s.hash("a", ["x"])
    assert s.documents() == ["a", "b"]


def test_len_tracks_doc_count():
    s = SimHash(num_bits=64)
    s.hash("a", ["x"])
    s.hash("b", ["y"])
    assert len(s) == 2


def test_contains_dunder():
    s = SimHash(num_bits=64)
    s.hash("present", ["x"])
    assert "present" in s and "absent" not in s


def test_fingerprint_within_num_bits():
    s = SimHash(num_bits=64)
    s.hash("d", make_doc(100))
    assert 0 <= s.fingerprint("d") < (1 << 64)


def test_custom_num_bits_fingerprint_range():
    s = SimHash(num_bits=128)
    s.hash("d", make_doc(100))
    assert 0 <= s.fingerprint("d") < (1 << 128)
    assert s.num_bits == 128


# ── identical / near-duplicate / different ───────────────────────────────────────

def test_identical_docs_hamming_zero():
    s = SimHash(num_bits=64, seed=0)
    doc = make_doc()
    s.hash("A", doc)
    s.hash("B", doc[:])
    assert s.hamming("A", "B") == 0


def test_identical_docs_similarity_one():
    s = SimHash(num_bits=64, seed=0)
    s.hash("A", make_doc())
    s.hash("B", make_doc())
    assert s.similarity("A", "B") == 1.0


def test_near_duplicate_one_token_swap():
    s = SimHash(num_bits=64, seed=0)
    base = make_doc()
    near = base[:]
    near[0] = "CHANGED"
    s.hash("A", base)
    s.hash("near", near)
    assert s.hamming("A", "near") <= NEAR_DUPLICATE_HAMMING


def test_near_duplicate_two_token_swap():
    s = SimHash(num_bits=64, seed=0)
    base = make_doc()
    near = base[:]
    near[0] = "CHANGED_A"
    near[300] = "CHANGED_B"
    s.hash("A", base)
    s.hash("near", near)
    assert s.hamming("A", "near") <= NEAR_DUPLICATE_HAMMING


def test_near_duplicate_method_true_for_near():
    s = SimHash(num_bits=64, seed=0)
    base = make_doc()
    near = base[:]
    near[0] = "CHANGED"
    s.hash("A", base)
    s.hash("near", near)
    assert s.near_duplicate("A", "near") is True


def test_near_duplicate_method_false_for_different():
    s = SimHash(num_bits=64, seed=0)
    s.hash("A", make_doc())
    s.hash("B", make_doc(prefix="other"))
    assert s.near_duplicate("A", "B") is False


def test_different_docs_hamming_near_half():
    s = SimHash(num_bits=64, seed=0)
    s.hash("A", make_doc())
    s.hash("B", make_doc(prefix="other"))
    assert 20 <= s.hamming("A", "B") <= 44      # ≈ num_bits / 2 = 32 for unrelated docs


def test_different_docs_low_similarity():
    s = SimHash(num_bits=64, seed=0)
    s.hash("A", make_doc())
    s.hash("B", make_doc(prefix="other"))
    assert s.similarity("A", "B") < 0.75


# ── similarity / hamming relationships ───────────────────────────────────────────

def test_similarity_matches_formula():
    s = SimHash(num_bits=64, seed=0)
    base = make_doc()
    near = base[:]
    near[0] = "CHANGED"
    s.hash("A", base)
    s.hash("near", near)
    d = s.hamming("A", "near")
    assert s.similarity("A", "near") == pytest.approx(1 - d / 64)


def test_hamming_symmetric():
    s = SimHash(num_bits=64, seed=1)
    s.hash("A", make_doc(200))
    s.hash("B", make_doc(200, prefix="z"))
    assert s.hamming("A", "B") == s.hamming("B", "A")


def test_self_hamming_zero():
    s = SimHash(num_bits=64)
    s.hash("A", make_doc(50))
    assert s.hamming("A", "A") == 0


# ── missing documents → None ─────────────────────────────────────────────────────

def test_hamming_missing_is_none():
    s = SimHash(num_bits=64)
    s.hash("A", ["x"])
    assert s.hamming("A", "ghost") is None


def test_similarity_missing_is_none():
    s = SimHash(num_bits=64)
    s.hash("A", ["x"])
    assert s.similarity("A", "ghost") is None


def test_near_duplicate_missing_is_none():
    assert SimHash(num_bits=64).near_duplicate("a", "b") is None


# ── determinism / seed / order / frequency ───────────────────────────────────────

def test_same_seed_same_fingerprint():
    a = SimHash(num_bits=64, seed=42)
    b = SimHash(num_bits=64, seed=42)
    a.hash("d", make_doc(100))
    b.hash("d", make_doc(100))
    assert a.fingerprint("d") == b.fingerprint("d")


def test_order_independent_fingerprint():
    s = SimHash(num_bits=64, seed=0)
    doc = make_doc(100)
    shuffled = doc[:]
    random.Random(5).shuffle(shuffled)
    s.hash("A", doc)
    s.hash("B", shuffled)
    assert s.hamming("A", "B") == 0


def test_different_seed_differs():
    a = SimHash(num_bits=64, seed=1)
    b = SimHash(num_bits=64, seed=2)
    a.hash("d", make_doc(100))
    b.hash("d", make_doc(100))
    assert a.fingerprint("d") != b.fingerprint("d")


def test_frequency_sensitive_bag_of_words():
    # SimHash is frequency-weighted: repeating a token changes the fingerprint.
    s = SimHash(num_bits=64, seed=0)
    s.hash("f1", ["x", "y", "z"])
    s.hash("f2", ["x", "x", "x", "x", "x", "y", "z"])
    assert s.hamming("f1", "f2") > 0


def test_deterministic_hamming_reproducible():
    a = SimHash(num_bits=64, seed=7)
    b = SimHash(num_bits=64, seed=7)
    for s in (a, b):
        s.hash("A", make_doc(300))
        s.hash("B", make_doc(300, prefix="other"))
    assert a.hamming("A", "B") == b.hamming("A", "B")


def test_empty_document_fingerprint_zero():
    s = SimHash(num_bits=64)
    s.hash("empty", [])
    assert s.fingerprint("empty") == 0


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_num_bits_is_64():
    assert SimHash().num_bits == 64


def test_num_bits_configurable():
    assert SimHash(num_bits=32).num_bits == 32


def test_near_duplicate_threshold_constant():
    assert NEAR_DUPLICATE_HAMMING == 3


def test_invalid_num_bits_zero_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=0)


def test_invalid_num_bits_negative_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=-8)


def test_invalid_num_bits_bool_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=True)


def test_invalid_num_bits_float_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=2.5)


def test_invalid_num_bits_too_large_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=513)


def test_invalid_seed_float_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=64, seed=1.5)


def test_invalid_seed_bool_raises():
    with pytest.raises(SimHashError):
        SimHash(num_bits=64, seed=True)


def test_negative_seed_allowed():
    assert SimHash(num_bits=64, seed=-9).seed == -9


def test_simhash_error_stores_detail():
    err = SimHashError(-3)
    assert err.detail == -3
    assert "invalid simhash configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(SimHash(num_bits=64).stats()) == {"num_bits", "docs", "total_hashed", "seed"}


def test_stats_initial():
    assert SimHash(num_bits=32, seed=4).stats() == {
        "num_bits": 32, "docs": 0, "total_hashed": 0, "seed": 4,
    }


def test_stats_tracks_docs_and_total():
    s = SimHash(num_bits=64)
    s.hash("a", ["x"])
    s.hash("b", ["y"])
    s.hash("a", ["x", "z"])           # re-hash same name: docs stays 2, total 3
    st = s.stats()
    assert st["docs"] == 2 and st["total_hashed"] == 3


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = SimHash(num_bits=64)
    s.hash("a", ["x"])
    s.reset()
    assert len(s) == 0 and s.stats()["total_hashed"] == 0


def test_reset_reconfigures_num_bits():
    s = SimHash(num_bits=64)
    s.reset(num_bits=128)
    s.hash("d", make_doc(50))
    assert s.num_bits == 128 and 0 <= s.fingerprint("d") < (1 << 128)


def test_reset_reconfigures_seed():
    s = SimHash(num_bits=64, seed=1)
    s.reset(seed=5)
    assert s.seed == 5


def test_reset_invalid_num_bits_raises():
    s = SimHash(num_bits=64)
    with pytest.raises(SimHashError):
        s.reset(num_bits=0)


def test_reset_then_reuse():
    s = SimHash(num_bits=64, seed=0)
    s.hash("a", make_doc(50))
    s.reset()
    s.hash("a", make_doc(50))
    s.hash("b", make_doc(50))
    assert s.hamming("a", "b") == 0


# ── concurrency ──────────────────────────────────────────────────────────────────

def test_concurrent_hash_10_threads():
    s = SimHash(num_bits=64, seed=0)
    errors = []

    def worker(tag):
        try:
            for i in range(50):
                s.hash(f"doc{tag}-{i}", [f"t{tag}", f"u{i}"])
        except Exception as exc:        # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(s) == 500
    assert s.stats()["total_hashed"] == 500


def test_concurrent_same_doc_consistent_fingerprint():
    ref = SimHash(num_bits=64, seed=0)
    doc = make_doc(200)
    ref.hash("s", doc)

    s = SimHash(num_bits=64, seed=0)
    errors = []

    def worker():
        try:
            for _ in range(50):
                s.hash("s", doc)
        except Exception as exc:        # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert s.fingerprint("s") == ref.fingerprint("s")
