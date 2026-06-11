"""Phase 140 — unit tests for RadixTree / Patricia trie (pradyos/core/radix_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.radix_tree import RadixTree, RadixTreeError


def rstr(rng, alpha="abcde", lo=1, hi=8):
    return "".join(rng.choice(alpha) for _ in range(rng.randint(lo, hi)))


def filled(pairs):
    rt = RadixTree()
    for k, v in pairs:
        rt.insert(k, v)
    return rt


# ── differential vs dict / brute force (centerpieces) ────────────────────────────────────

def test_insert_search_differential():
    rng = random.Random(1)
    rt = RadixTree()
    ref = {}
    for _ in range(2000):
        k = rstr(rng)
        v = rng.randint(0, 10 ** 6)
        rt.insert(k, v)
        ref[k] = v
    assert all(rt.search(k) == ref[k] for k in ref)
    assert len(rt) == len(ref) and rt.keys() == sorted(ref)


def test_prefix_search_brute_force():
    rng = random.Random(2)
    ref = {rstr(rng): i for i in range(800)}
    rt = filled(ref.items())
    for p in ["a", "ab", "abc", "", "zz"] + [rstr(rng, lo=1, hi=3) for _ in range(30)]:
        assert rt.prefix_search(p) == sorted((k, ref[k]) for k in ref if k.startswith(p))


def test_longest_prefix_brute_force():
    rng = random.Random(3)
    ref = {rstr(rng): i for i in range(600)}
    rt = filled(ref.items())
    for _ in range(200):
        q = rstr(rng)
        cands = [k for k in ref if q.startswith(k)]
        got = rt.longest_prefix(q)
        if not cands:
            assert got is None
        else:
            assert got in ref and q.startswith(got) and len(got) == max(len(c) for c in cands)


def test_differential_insert_delete_search():
    rng = random.Random(7)
    ref = {}
    rt = RadixTree()
    for _ in range(8000):
        k = "".join(rng.choice("abc") for _ in range(rng.randint(1, 6)))
        r = rng.random()
        if r < 0.55:
            v = rng.randint(0, 1000)
            ref[k] = v
            rt.insert(k, v)
        elif r < 0.75:
            had = k in ref
            ref.pop(k, None)
            assert rt.delete(k) == had
        else:
            assert rt.search(k) == ref.get(k)
    assert len(rt) == len(ref) and rt.keys() == sorted(ref)


# ── core semantics ────────────────────────────────────────────────────────────────────────

def test_search_absent_none():
    assert filled([("abc", 1)]).search("xyz") is None


def test_update_value():
    rt = filled([("key", 1)])
    rt.insert("key", 2)
    assert rt.search("key") == 2 and len(rt) == 1


def test_contains():
    rt = filled([("a", 1), ("b", 2)])
    assert "a" in rt and "z" not in rt


def test_keys_sorted():
    assert filled([("c", 1), ("a", 1), ("b", 1)]).keys() == ["a", "b", "c"]


def test_split_edge():
    rt = filled([("test", 1), ("team", 2)])    # split at "te"
    rt.insert("te", 3)
    assert rt.search("test") == 1 and rt.search("team") == 2 and rt.search("te") == 3


def test_empty_key():
    rt = filled([("", 0), ("a", 1)])
    assert rt.search("") == 0 and rt.search("a") == 1 and len(rt) == 2
    assert rt.longest_prefix("apex") == "a"        # "a" is the longest stored prefix
    assert rt.longest_prefix("xyz") == ""          # only the empty key is a prefix of "xyz"


def test_prefix_of_another():
    rt = filled([("a", 1), ("ab", 2), ("abc", 3)])
    assert rt.search("a") == 1 and rt.search("ab") == 2 and rt.search("abc") == 3


# ── prefix / longest_prefix specifics ─────────────────────────────────────────────────────

def test_prefix_search_empty_returns_all():
    rt = filled([("a", 1), ("b", 2), ("ab", 3)])
    assert rt.prefix_search("") == [("a", 1), ("ab", 3), ("b", 2)]


def test_prefix_search_no_match():
    assert filled([("apple", 1), ("banana", 2)]).prefix_search("cherry") == []


def test_prefix_search_partial_edge():
    rt = filled([("interview", 1), ("internet", 2)])
    assert rt.prefix_search("inte") == [("internet", 2), ("interview", 1)]


def test_longest_prefix_none():
    assert filled([("abc", 1)]).longest_prefix("xyz") is None


def test_longest_prefix_exact_and_routing():
    rt = filled([("10", 1), ("10.0", 2), ("10.0.0", 3)])
    assert rt.longest_prefix("10.0.0.1") == "10.0.0" and rt.longest_prefix("10.5") == "10"


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete_reduces_count():
    rt = filled([("a", 1), ("b", 2)])
    assert rt.delete("a") is True and len(rt) == 1 and rt.search("a") is None


def test_delete_remerge_keeps_siblings():
    rt = filled([("a", 1), ("ab", 2), ("abc", 3), ("abd", 4)])
    rt.delete("ab")
    assert rt.search("abc") == 3 and rt.search("abd") == 4 and rt.search("a") == 1
    assert rt.search("ab") is None


def test_reinsert_after_delete():
    rt = filled([("ab", 2), ("abc", 3)])
    rt.delete("ab")
    rt.insert("ab", 99)
    assert rt.search("ab") == 99 and rt.search("abc") == 3


def test_delete_absent_false():
    assert filled([("a", 1)]).delete("z") is False


def test_delete_non_key_internal_false():
    rt = filled([("abc", 1), ("abd", 2)])      # "ab" is an internal non-key node
    assert rt.delete("ab") is False and rt.search("abc") == 1


# ── compression / stats ─────────────────────────────────────────────────────────────────────

def test_compression_ratio_gt1():
    rt = filled([(k, 1) for k in ("interview", "internet", "internal", "interval")])
    assert rt.stats()["compression_ratio"] > 1.0


def test_num_nodes():
    rt = filled([("abc", 1), ("abd", 2)])      # root, "ab", "c", "d" = 4 nodes
    assert rt.num_nodes() == 4


def test_stats_keys():
    assert set(RadixTree().stats()) == {"num_keys", "num_nodes", "compression_ratio", "seed"}


def test_size_len():
    rt = filled([("a", 1), ("b", 2), ("c", 3)])
    assert len(rt) == 3 and rt.size == 3


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_insert_non_str_raises():
    with pytest.raises(RadixTreeError):
        RadixTree().insert(5, 1)


def test_search_non_str_raises():
    with pytest.raises(RadixTreeError):
        RadixTree().search(5)


def test_delete_non_str_raises():
    with pytest.raises(RadixTreeError):
        RadixTree().delete(5)


def test_prefix_non_str_raises():
    with pytest.raises(RadixTreeError):
        RadixTree().prefix_search(5)


def test_bad_seed_raises():
    with pytest.raises(RadixTreeError):
        RadixTree(seed="x")


def test_error_stores_detail():
    err = RadixTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── reset / determinism / seed ──────────────────────────────────────────────────────────────

def test_reset_clears():
    rt = filled([("a", 1), ("b", 2)])
    rt.reset()
    assert len(rt) == 0 and rt.search("a") is None


def test_deterministic():
    pairs = [("cat", 1), ("car", 2), ("card", 3), ("dog", 4), ("do", 5)]
    assert filled(pairs).stats() == filled(pairs).stats()
    assert filled(pairs).keys() == filled(pairs).keys()


def test_seed_property():
    assert RadixTree(seed=42).seed == 42


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    rt = RadixTree()
    errors = []

    def worker(base):
        try:
            for i in range(500):
                rt.insert(f"k-{base}-{i}", base * 1000 + i)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(rt) == 5000
    assert all(rt.search(f"k-{b}-{i}") == b * 1000 + i for b in range(10) for i in range(0, 500, 50))
