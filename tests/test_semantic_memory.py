"""Tests for the Semantic Memory Engine (MinHash + SimHash associative recall)."""

from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.semantic_memory import SemanticMemory, SemanticMemoryError


def _mem(**kw) -> SemanticMemory:
    return SemanticMemory(seed=0, **kw)


# ── construction / validation ─────────────────────────────────────────────────


def test_default_construction():
    m = SemanticMemory()
    s = m.stats()
    assert s["num_hashes"] == 128 and s["simhash_bits"] == 64 and s["size"] == 0


def test_custom_construction():
    m = SemanticMemory(num_hashes=64, simhash_bits=32, capacity=500, seed=3)
    s = m.stats()
    assert s["num_hashes"] == 64 and s["simhash_bits"] == 32 and s["capacity"] == 500


@pytest.mark.parametrize("bad", [0, -1, "x", 1.5])
def test_invalid_num_hashes(bad):
    with pytest.raises(SemanticMemoryError):
        SemanticMemory(num_hashes=bad)


@pytest.mark.parametrize("bad", [0, -5])
def test_invalid_simhash_bits(bad):
    with pytest.raises(SemanticMemoryError):
        SemanticMemory(simhash_bits=bad)


def test_invalid_capacity():
    with pytest.raises(SemanticMemoryError):
        SemanticMemory(capacity=0)


# ── store validation ──────────────────────────────────────────────────────────


def test_store_requires_nonempty_key():
    m = _mem()
    with pytest.raises(SemanticMemoryError):
        m.store("", "c", ["a"])
    with pytest.raises(SemanticMemoryError):
        m.store("   ", "c", ["a"])


def test_store_requires_list_tokens():
    m = _mem()
    with pytest.raises(SemanticMemoryError):
        m.store("k", "c", "not-a-list")


def test_store_adds_item():
    m = _mem()
    m.store("doc1", "hello world", ["hello", "world"])
    assert m.keys() == ["doc1"]
    assert m.stats()["size"] == 1


def test_store_accepts_empty_tokens():
    m = _mem()
    m.store("empty", "", [])
    assert "empty" in m.keys()


def test_restore_bumps_frequency():
    m = _mem()
    m.store("d", "c", ["a", "b"])
    m.store("d", "c", ["a", "b"])
    assert m.stats()["size"] == 1
    assert m.recall(["a", "b"])[0]["freq"] == 2


def test_store_coerces_non_string_tokens():
    m = _mem()
    m.store("d", "c", [1, 2, 3])  # type: ignore[list-item]
    assert m.recall(["1", "2", "3"])[0]["key"] == "d"


# ── recall: ranking + separation ──────────────────────────────────────────────


def _populate(m, n=100, seed=1):
    rng = random.Random(seed)
    vocab = [chr(97 + i) for i in range(20)]
    target = None
    for i in range(n):
        toks = rng.sample(vocab, 6)
        m.store(f"doc{i}", f"content {i}", toks)
        if i == 42:
            target = list(toks)
    return target


def test_recall_near_duplicate_is_rank1():
    m = _mem()
    target = _populate(m)
    near = target[:5] + ["ZZ"]  # 5 of 6 tokens shared
    hits = m.recall(near, top_k=3)
    assert hits[0]["key"] == "doc42"
    assert hits[0]["score"] > 0.5


def test_recall_exact_match_scores_highest():
    m = _mem()
    target = _populate(m)
    hits = m.recall(target, top_k=1)
    assert hits[0]["key"] == "doc42"


def test_unrelated_query_is_clearly_separated():
    m = _mem()
    _populate(m)
    unrelated = m.recall(["ZZ", "YY", "XX", "WW", "VV", "UU"], top_k=1)
    # the noise floor over 100 disjoint candidates is small, never near a real hit
    assert unrelated[0]["score"] < 0.2


def test_min_similarity_filters_noise():
    m = _mem()
    _populate(m)
    filtered = m.recall(["ZZ", "YY", "XX"], top_k=100, min_similarity=0.25)
    assert len(filtered) < 100  # most/all noise excluded


def test_recall_respects_top_k():
    m = _mem()
    _populate(m)
    assert len(m.recall(["a", "b", "c"], top_k=5)) == 5


def test_recall_empty_memory_returns_empty():
    assert _mem().recall(["a", "b"]) == []


def test_recall_result_shape():
    m = _mem()
    m.store("d", "the content", ["a", "b"])
    r = m.recall(["a", "b"])[0]
    assert set(r) == {"key", "score", "jaccard", "hamming_sim", "content", "freq"}
    assert r["content"] == "the content"


def test_recall_validation():
    m = _mem()
    with pytest.raises(SemanticMemoryError):
        m.recall("nope")
    with pytest.raises(SemanticMemoryError):
        m.recall(["a"], top_k=0)


def test_scores_in_unit_interval():
    m = _mem()
    _populate(m, n=30)
    for r in m.recall(["a", "b", "c", "d"], top_k=30):
        assert 0.0 <= r["score"] <= 1.0
        assert 0.0 <= r["jaccard"] <= 1.0
        assert 0.0 <= r["hamming_sim"] <= 1.0


# ── forget ─────────────────────────────────────────────────────────────────────


def test_forget_prunes_below_threshold():
    m = _mem()
    m.store("cold", "c", ["a"])  # freq 1
    m.store("hot", "c", ["b"])
    m.store("hot", "c", ["b"])  # freq 2
    pruned = m.forget(2.0)
    assert pruned == 1
    assert m.keys() == ["hot"]


def test_forget_returns_zero_when_nothing_prunes():
    m = _mem()
    m.store("a", "c", ["x"])
    assert m.forget(0.5) == 0


def test_forgotten_items_not_recalled():
    m = _mem()
    m.store("gone", "c", ["a", "b"])
    m.forget(2.0)
    assert all(h["key"] != "gone" for h in m.recall(["a", "b"]))


# ── merge ──────────────────────────────────────────────────────────────────────


def test_merge_combines_disjoint():
    a, b = _mem(), _mem()
    a.store("k1", "c", ["a", "b"])
    b.store("k2", "c", ["c", "d"])
    a.merge(b)
    assert set(a.keys()) == {"k1", "k2"}


def test_merge_higher_frequency_wins():
    a, b = _mem(), _mem()
    a.store("k", "old", ["a"])
    b.store("k", "new", ["a"])
    b.store("k", "new", ["a"])  # freq 2 in b
    a.merge(b)
    assert a.recall(["a"])[0]["freq"] == 2


def test_merge_rejects_mismatched_config():
    a = SemanticMemory(num_hashes=128, seed=0)
    b = SemanticMemory(num_hashes=64, seed=0)
    with pytest.raises(SemanticMemoryError):
        a.merge(b)


def test_merge_rejects_non_memory():
    with pytest.raises(SemanticMemoryError):
        _mem().merge(object())  # type: ignore[arg-type]


# ── capacity eviction ──────────────────────────────────────────────────────────


def test_capacity_evicts_least_frequent():
    m = SemanticMemory(capacity=3, seed=0)
    m.store("keep", "c", ["a"])
    m.store("keep", "c", ["a"])  # freq 2
    m.store("b", "c", ["b"])
    m.store("c", "c", ["c"])
    m.store("d", "c", ["d"])  # over capacity → evict a freq-1 item
    assert m.stats()["size"] == 3
    assert "keep" in m.keys()  # the frequent one survives


# ── determinism ────────────────────────────────────────────────────────────────


def test_same_seed_same_ranking():
    m1, m2 = SemanticMemory(seed=7), SemanticMemory(seed=7)
    for m in (m1, m2):
        m.store("x", "c", ["p", "q", "r"])
        m.store("y", "c", ["p", "q", "s"])
        m.store("z", "c", ["t", "u", "v"])
    q = ["p", "q", "r"]
    assert [h["key"] for h in m1.recall(q)] == [h["key"] for h in m2.recall(q)]


def test_signatures_are_deterministic():
    m1, m2 = SemanticMemory(seed=11), SemanticMemory(seed=11)
    m1.store("a", "c", ["one", "two", "three"])
    m2.store("a", "c", ["one", "two", "three"])
    assert m1.recall(["one", "two", "three"])[0]["score"] == m2.recall(["one", "two", "three"])[0]["score"]


# ── stats / reset / keys ───────────────────────────────────────────────────────


def test_stats_top_concepts_ordered_by_freq():
    m = _mem()
    m.store("popular", "c", ["a"])
    m.store("popular", "c", ["a"])
    m.store("rare", "c", ["b"])
    top = m.stats()["top_concepts"]
    assert top[0]["key"] == "popular" and top[0]["freq"] == 2


def test_reset_clears():
    m = _mem()
    _populate(m, n=10)
    m.reset()
    assert m.stats()["size"] == 0 and m.keys() == []


def test_keys_sorted():
    m = _mem()
    for k in ["zebra", "apple", "mango"]:
        m.store(k, "c", ["x"])
    assert m.keys() == ["apple", "mango", "zebra"]


# ── thread safety ──────────────────────────────────────────────────────────────


def test_concurrent_stores_no_loss():
    m = SemanticMemory(capacity=10_000, seed=0)

    def worker(base):
        for i in range(100):
            m.store(f"k{base}-{i}", "c", ["a", "b", str(i)])

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert m.stats()["size"] == 800
