"""Phase 115 — unit tests for MinHashLSH (pradyos/core/minhash_lsh.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.minhash_lsh import MinHashLSH, MinHashLSHError


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b)


# ── basic correctness ──────────────────────────────────────────────────────────

def test_self_query_finds_self():
    lsh = MinHashLSH(bands=16, rows=4, seed=0)
    A = set(range(100))
    lsh.insert("A", A)
    res = lsh.query(A)
    assert res[0][0] == "A" and res[0][1] > 0.95


def test_len_and_contains():
    lsh = MinHashLSH(seed=0)
    lsh.insert("a", set(range(10)))
    lsh.insert("b", set(range(10, 20)))
    assert len(lsh) == 2 and "a" in lsh and "z" not in lsh


def test_empty_index_query_empty():
    assert MinHashLSH(seed=0).query(set(range(10))) == []


# ── similarity estimate ──────────────────────────────────────────────────────────

def test_similarity_estimate_accurate():
    lsh = MinHashLSH(bands=32, rows=4, seed=0)        # k=128 for a tighter estimate
    a, b = set(range(100)), set(range(50, 150))       # Jaccard 1/3
    assert abs(lsh.similarity(a, b) - _jaccard(a, b)) < 0.1


def test_similarity_identical_is_one():
    lsh = MinHashLSH(seed=0)
    assert lsh.similarity(set(range(50)), set(range(50))) == 1.0


def test_similarity_disjoint_near_zero():
    lsh = MinHashLSH(bands=32, rows=4, seed=0)
    assert lsh.similarity(set(range(50)), set(range(100, 150))) < 0.05


# ── retrieval / S-curve ──────────────────────────────────────────────────────────

def test_near_duplicate_retrieved():
    lsh = MinHashLSH(bands=16, rows=4, seed=1)
    base = set(range(200))
    lsh.insert("doc", base)
    near = set(range(20, 220))                        # Jaccard ~0.82
    assert any(cid == "doc" for cid, _ in lsh.query(near))


def test_disjoint_not_retrieved():
    lsh = MinHashLSH(bands=16, rows=4, seed=1)
    lsh.insert("doc", set(range(200)))
    assert not any(cid == "doc" for cid, _ in lsh.query(set(range(5000, 5200))))


def test_threshold_filters_by_estimate():
    lsh = MinHashLSH(bands=16, rows=4, seed=2)
    lsh.insert("x", set(range(200)))
    near = set(range(40, 240))                        # Jaccard 0.667, est ~0.64
    assert any(c == "x" for c, _ in lsh.query(near, threshold=0.4))
    assert not any(c == "x" for c, _ in lsh.query(near, threshold=0.9))


def test_recall_on_near_duplicates():
    lsh = MinHashLSH(bands=20, rows=4, seed=3)
    rng = random.Random(7)
    docs = {}
    for i in range(200):
        s = set(rng.sample(range(10000), 100))
        docs[f"d{i}"] = s
        lsh.insert(f"d{i}", s)
    hits = 0
    for i in range(200):
        near = set(list(docs[f"d{i}"])[:90]) | set(rng.sample(range(10000), 10))
        if any(cid == f"d{i}" for cid, _ in lsh.query(near)):
            hits += 1
    assert hits / 200 >= 0.9


def test_query_sorted_by_similarity_desc():
    lsh = MinHashLSH(bands=16, rows=4, seed=4)
    base = set(range(200))
    lsh.insert("exact", base)
    lsh.insert("close", set(range(20, 220)))          # high Jaccard
    lsh.insert("looser", set(range(100, 300)))        # lower Jaccard
    res = lsh.query(base)
    sims = [s for _, s in res]
    assert sims == sorted(sims, reverse=True)
    assert res[0][0] == "exact"


def test_multiple_similar_all_retrieved():
    lsh = MinHashLSH(bands=16, rows=4, seed=5)
    for i in range(5):
        lsh.insert(f"v{i}", set(range(i, i + 200)))   # overlapping windows
    res = lsh.query(set(range(200)))
    assert len(res) >= 3                               # several overlapping windows collide


# ── determinism ──────────────────────────────────────────────────────────────────

def test_same_seed_deterministic_query():
    a = MinHashLSH(bands=16, rows=4, seed=5)
    b = MinHashLSH(bands=16, rows=4, seed=5)
    for i in range(50):
        s = set(range(i, i + 30))
        a.insert(f"k{i}", s)
        b.insert(f"k{i}", s)
    q = set(range(10, 40))
    assert a.query(q) == b.query(q)


def test_signature_deterministic_for_same_seed():
    a = MinHashLSH(seed=9)
    b = MinHashLSH(seed=9)
    assert a.similarity(set(range(50)), set(range(25, 75))) == \
        b.similarity(set(range(50)), set(range(25, 75)))


# ── remove / re-insert ───────────────────────────────────────────────────────────

def test_remove_present():
    lsh = MinHashLSH(seed=0)
    lsh.insert("a", set(range(50)))
    assert lsh.remove("a") is True and "a" not in lsh and len(lsh) == 0


def test_remove_absent():
    assert MinHashLSH(seed=0).remove("nope") is False


def test_removed_not_in_query():
    lsh = MinHashLSH(seed=0)
    lsh.insert("a", set(range(50)))
    lsh.remove("a")
    assert all(c != "a" for c, _ in lsh.query(set(range(50))))


def test_reinsert_replaces_signature():
    lsh = MinHashLSH(seed=0)
    lsh.insert("b", set(range(50)))
    lsh.insert("b", set(range(500, 600)))             # totally different tokens
    assert len(lsh) == 1
    assert not any(c == "b" for c, _ in lsh.query(set(range(50))))
    assert any(c == "b" for c, _ in lsh.query(set(range(500, 600))))


# ── empty / edge ─────────────────────────────────────────────────────────────────

def test_insert_empty_token_set():
    lsh = MinHashLSH(seed=0)
    lsh.insert("empty", set())
    assert "empty" in lsh and len(lsh) == 1


def test_string_tokens():
    lsh = MinHashLSH(bands=16, rows=4, seed=0)
    doc1 = {"the", "quick", "brown", "fox", "jumps"}
    doc2 = {"the", "quick", "brown", "fox", "runs"}     # 4/6 overlap
    lsh.insert("doc1", doc1)
    assert any(c == "doc1" for c, _ in lsh.query(doc2))


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_bands_raises():
    with pytest.raises(MinHashLSHError):
        MinHashLSH(bands=0)


def test_invalid_rows_raises():
    with pytest.raises(MinHashLSHError):
        MinHashLSH(rows=0)


def test_invalid_seed_raises():
    with pytest.raises(MinHashLSHError):
        MinHashLSH(seed="nope")


def test_bool_bands_rejected():
    with pytest.raises(MinHashLSHError):
        MinHashLSH(bands=True)


def test_query_threshold_out_of_range_raises():
    lsh = MinHashLSH(seed=0)
    lsh.insert("a", set(range(10)))
    with pytest.raises(MinHashLSHError):
        lsh.query(set(range(10)), threshold=1.5)


def test_query_threshold_negative_raises():
    lsh = MinHashLSH(seed=0)
    with pytest.raises(MinHashLSHError):
        lsh.query(set(range(10)), threshold=-0.1)


def test_reset_invalid_raises():
    lsh = MinHashLSH(seed=0)
    with pytest.raises(MinHashLSHError):
        lsh.reset(bands=0)


def test_error_stores_detail():
    err = MinHashLSHError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & threshold estimate ───────────────────────────────────────────────

def test_properties():
    lsh = MinHashLSH(bands=20, rows=5, seed=7)
    assert lsh.bands == 20 and lsh.rows == 5 and lsh.num_perm == 100 and lsh.seed == 7


def test_threshold_estimate():
    lsh = MinHashLSH(bands=16, rows=4, seed=0)
    assert abs(lsh.threshold_estimate() - (1 / 16) ** (1 / 4)) < 1e-9


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(MinHashLSH(seed=0).stats()) == {
        "num_items", "bands", "rows", "num_perm", "threshold_estimate", "seed"}


def test_stats_values():
    lsh = MinHashLSH(bands=8, rows=4, seed=3)
    lsh.insert("a", set(range(10)))
    s = lsh.stats()
    assert s["num_items"] == 1 and s["bands"] == 8 and s["rows"] == 4 and s["num_perm"] == 32
    assert s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    lsh = MinHashLSH(seed=0)
    for i in range(10):
        lsh.insert(f"k{i}", set(range(i, i + 20)))
    lsh.reset()
    assert len(lsh) == 0 and lsh.query(set(range(20))) == []


def test_reset_reconfigures():
    lsh = MinHashLSH(bands=16, rows=4, seed=0)
    lsh.reset(bands=8, rows=2, seed=5)
    assert lsh.bands == 8 and lsh.rows == 2 and lsh.num_perm == 16 and lsh.seed == 5


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    lsh = MinHashLSH(bands=16, rows=4, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(50):
                lsh.insert(f"t{base}-{i}", set(range(i, i + 30)))
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(lsh) == 500
