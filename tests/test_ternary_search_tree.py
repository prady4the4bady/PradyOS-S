"""Phase 164 — unit tests for TernarySearchTree (pradyos/core/ternary_search_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.ternary_search_tree import TernarySearchTree, TernarySearchTreeError


def _rand_word(rng):
    return "".join(rng.choice("abcde") for _ in range(rng.randint(1, 6)))


# ── differential vs Python set (centerpieces) ────────────────────────────────────────────

def test_insert_delete_contains_differential():
    rng = random.Random(1)
    for _ in range(40):
        t = TernarySearchTree(); s = set()
        for _ in range(200):
            w = _rand_word(rng)
            if rng.random() < 0.6:
                assert t.insert(w) == (w not in s); s.add(w)
            else:
                assert t.delete(w) == (w in s); s.discard(w)
        assert t.keys() == sorted(s)
        for w in list(s)[:20] + [_rand_word(rng) for _ in range(20)]:
            assert t.contains(w) == (w in s)


def test_keys_with_prefix_differential():
    rng = random.Random(2)
    for _ in range(40):
        t = TernarySearchTree(); s = set()
        for _ in range(80):
            w = _rand_word(rng); t.insert(w); s.add(w)
        for _ in range(10):
            pre = "".join(rng.choice("abcde") for _ in range(rng.randint(0, 3)))
            assert t.keys_with_prefix(pre) == sorted(w for w in s if w.startswith(pre))


def test_longest_prefix_differential():
    rng = random.Random(3)
    for _ in range(40):
        t = TernarySearchTree(); s = set()
        for _ in range(80):
            w = _rand_word(rng); t.insert(w); s.add(w)
        for _ in range(10):
            q = "".join(rng.choice("abcde") for _ in range(rng.randint(0, 8)))
            cands = [w for w in s if q.startswith(w)]
            exp = max(cands, key=len) if cands else None
            got = t.longest_prefix_of(q)
            assert (len(got) if got else 0) == (len(exp) if exp else 0)
            assert got == exp


def test_large_keys():
    rng = random.Random(4)
    t = TernarySearchTree(); words = set(_rand_word(rng) for _ in range(1500))
    for w in words:
        t.insert(w)
    assert t.keys() == sorted(words) and t.size == len(words)


def test_shared_prefix_no_overflow():
    t = TernarySearchTree()
    for i in range(2000):
        t.insert("k" + str(i).zfill(5))
    assert t.size == 2000 and len(t.keys_with_prefix("k")) == 2000


# ── specific ─────────────────────────────────────────────────────────────────────────────

def test_contains_specific():
    t = TernarySearchTree()
    for w in ["cat", "car", "card", "dog", "do", "cats"]:
        t.insert(w)
    assert t.contains("car") and t.contains("do") and not t.contains("ca") and not t.contains("cards")


def test_keys_specific():
    t = TernarySearchTree()
    for w in ["cat", "car", "card", "dog", "do", "cats"]:
        t.insert(w)
    assert t.keys() == ["car", "card", "cat", "cats", "do", "dog"]


def test_keys_with_prefix_specific():
    t = TernarySearchTree()
    for w in ["cat", "car", "card", "dog", "do", "cats"]:
        t.insert(w)
    assert t.keys_with_prefix("car") == ["car", "card"]
    assert t.keys_with_prefix("ca") == ["car", "card", "cat", "cats"]


def test_keys_with_prefix_empty_is_all():
    t = TernarySearchTree()
    for w in ("a", "b", "ab"):
        t.insert(w)
    assert t.keys_with_prefix("") == t.keys() == ["a", "ab", "b"]


def test_keys_with_prefix_no_match():
    t = TernarySearchTree()
    t.insert("apple")
    assert t.keys_with_prefix("xyz") == []


def test_longest_prefix_of():
    t = TernarySearchTree()
    for w in ["cat", "car", "card", "do", "dog"]:
        t.insert(w)
    assert t.longest_prefix_of("cards") == "card" and t.longest_prefix_of("doggy") == "dog"
    assert t.longest_prefix_of("x") is None and t.longest_prefix_of("cat") == "cat"


def test_single_char_keys():
    t = TernarySearchTree()
    for w in ["a", "b", "ab", "abc"]:
        t.insert(w)
    assert t.contains("a") and t.keys_with_prefix("a") == ["a", "ab", "abc"]
    assert t.longest_prefix_of("abcd") == "abc"


def test_unicode():
    t = TernarySearchTree()
    for w in ["café", "car", "naïve", "café"]:
        t.insert(w)
    assert t.contains("café") and t.size == 3 and t.keys_with_prefix("ca") == ["café", "car"]


# ── delete / dup ─────────────────────────────────────────────────────────────────────────

def test_delete_then_reinsert():
    t = TernarySearchTree(); t.insert("hello")
    assert t.delete("hello") and not t.contains("hello") and t.size == 0
    assert t.insert("hello") and t.contains("hello")


def test_delete_absent():
    assert TernarySearchTree().delete("nope") is False


def test_dup_insert():
    t = TernarySearchTree(); t.insert("hello")
    assert t.insert("hello") is False and t.size == 1


def test_insert_returns_bool():
    assert TernarySearchTree().insert("x") is True


def test_delete_returns_bool():
    t = TernarySearchTree(); t.insert("x")
    assert t.delete("x") is True


# ── empty-input handling ─────────────────────────────────────────────────────────────────

def test_contains_empty_false():
    assert TernarySearchTree().contains("") is False


def test_longest_prefix_empty_none():
    assert TernarySearchTree().longest_prefix_of("") is None


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_insert_non_str_raises():
    with pytest.raises(TernarySearchTreeError):
        TernarySearchTree().insert(123)


def test_insert_empty_raises():
    with pytest.raises(TernarySearchTreeError):
        TernarySearchTree().insert("")


def test_contains_non_str_raises():
    with pytest.raises(TernarySearchTreeError):
        TernarySearchTree().contains(5)


def test_prefix_non_str_raises():
    with pytest.raises(TernarySearchTreeError):
        TernarySearchTree().keys_with_prefix(7)


def test_error_stores_detail():
    err = TernarySearchTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    t = TernarySearchTree()
    for w in ("a", "b", "c"):
        t.insert(w)
    t.reset()
    assert t.is_empty() and t.keys() == []


def test_size_len():
    t = TernarySearchTree()
    t.insert("a"); t.insert("b")
    assert t.size == 2 and len(t) == 2


def test_stats_keys():
    assert set(TernarySearchTree().stats()) == {"size", "nodes"}


def test_stats_nodes():
    t = TernarySearchTree()
    t.insert("abc")
    assert t.stats()["size"] == 1 and t.stats()["nodes"] == 3


def test_deterministic():
    def build():
        x = TernarySearchTree()
        for w in ["the", "quick", "brown", "fox", "the", "fox"]:
            x.insert(w)
        return x.keys()
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = TernarySearchTree()
    errors = []
    words = ["w" + str(i).zfill(4) for i in range(400)]

    def worker(chunk):
        try:
            for w in chunk:
                t.insert(w)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(words[i::4],)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and t.size == 400 and t.keys() == sorted(words)
