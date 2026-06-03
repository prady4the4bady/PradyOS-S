"""Phase 143 — unit tests for XorTrie (pradyos/core/xor_trie.py)."""
from __future__ import annotations

import random
import threading
from collections import Counter

import pytest

from pradyos.core.xor_trie import XorTrie, XorTrieError


def filled(values, width=16):
    t = XorTrie(width=width)
    for v in values:
        t.insert(v)
    return t


# ── differential vs brute force (centerpieces) ───────────────────────────────────────────

def test_max_min_xor_differential():
    rng = random.Random(1)
    for width in (4, 8, 16, 32):
        lim = 1 << width
        for _ in range(25):
            vals = [rng.randint(0, lim - 1) for _ in range(rng.randint(1, 50))]
            t = filled(vals, width)
            for _ in range(15):
                q = rng.randint(0, lim - 1)
                assert t.max_xor(q) == max(q ^ x for x in vals)
                assert t.min_xor(q) == min(q ^ x for x in vals)


def test_count_xor_less_differential():
    rng = random.Random(2)
    for width in (4, 8, 16):
        lim = 1 << width
        for _ in range(30):
            vals = [rng.randint(0, lim - 1) for _ in range(rng.randint(1, 40))]
            t = filled(vals, width)
            for _ in range(15):
                q = rng.randint(0, lim - 1)
                k = rng.randint(0, lim)
                assert t.count_xor_less(q, k) == sum(1 for x in vals if (q ^ x) < k)


def test_contains_differential():
    rng = random.Random(3)
    vals = [rng.randint(0, 255) for _ in range(80)]
    t = filled(vals, 8)
    present = set(vals)
    for v in range(256):
        assert t.contains(v) == (v in present)


def test_insert_remove_multiset():
    rng = random.Random(7)
    ref = Counter()
    t = XorTrie(width=10)
    for _ in range(8000):
        v = rng.randint(0, 1023)
        if ref[v] > 0 and rng.random() < 0.4:
            ref[v] -= 1
            if ref[v] == 0:
                del ref[v]
            assert t.remove(v) is True
        else:
            ref[v] += 1
            t.insert(v)
    assert len(t) == sum(ref.values())
    vals = list(ref.elements())
    if vals:
        assert t.max_xor(500) == max(500 ^ x for x in vals)


def test_max_xor_pair_classic():
    # The maximum-XOR-pair over a set = max over x of max_xor(x) with all inserted.
    rng = random.Random(9)
    vals = [rng.randint(0, 65535) for _ in range(60)]
    t = filled(vals, 16)
    best = max(t.max_xor(x) for x in vals)
    brute = max(a ^ b for i, a in enumerate(vals) for b in vals[i:])
    assert best == brute


# ── specific / multiset ───────────────────────────────────────────────────────────────────

def test_max_xor_specific():
    t = filled([2, 20, 12], 5)
    assert t.max_xor(0b11111) == max((0b11111) ^ x for x in (2, 20, 12))


def test_min_xor_specific():
    t = filled([10, 25, 7], 8)
    assert t.min_xor(9) == min(9 ^ x for x in (10, 25, 7))


def test_duplicates_counted():
    t = XorTrie(width=8)
    t.insert(42); t.insert(42)
    assert len(t) == 2
    t.remove(42)
    assert t.contains(42) and len(t) == 1
    t.remove(42)
    assert not t.contains(42) and len(t) == 0


def test_remove_absent():
    assert filled([1, 2, 3], 8).remove(99) is False


def test_single_value():
    t = filled([7], 8)
    assert t.max_xor(3) == (3 ^ 7) and t.min_xor(3) == (3 ^ 7)


def test_two_values_max_min():
    t = filled([5, 3], 8)
    assert t.max_xor(0) == 5 and t.min_xor(0) == 3


def test_count_xor_less_full_range():
    t = filled([1, 2, 3, 4], 8)
    assert t.count_xor_less(0, 256) == 4 and t.count_xor_less(0, 1) == 0


def test_count_k_zero_and_huge():
    t = filled([10, 20, 30], 8)
    assert t.count_xor_less(5, 0) == 0 and t.count_xor_less(5, 10 ** 9) == 3


# ── edges ────────────────────────────────────────────────────────────────────────────────

def test_empty_max_xor_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=8).max_xor(5)


def test_empty_min_xor_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=8).min_xor(5)


def test_empty_count_zero():
    assert XorTrie(width=8).count_xor_less(5, 100) == 0


def test_default_width_32():
    t = XorTrie()
    assert t.width == 32
    t.insert(2 ** 31)
    assert t.max_xor(0) == 2 ** 31


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_width_zero_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=0)


def test_width_too_large_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=257)


def test_value_out_of_range_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=8).insert(256)


def test_negative_value_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=8).insert(-1)


def test_bool_value_raises():
    with pytest.raises(XorTrieError):
        XorTrie(width=8).insert(True)


def test_query_out_of_range_raises():
    with pytest.raises(XorTrieError):
        filled([1, 2], 8).max_xor(300)


def test_count_non_int_k_raises():
    with pytest.raises(XorTrieError):
        filled([1, 2], 8).count_xor_less(1, 1.5)


def test_error_stores_detail():
    err = XorTrieError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── reset / introspection / determinism ───────────────────────────────────────────────────────

def test_reset_clears():
    t = filled([1, 2, 3], 8)
    t.reset()
    assert len(t) == 0


def test_reset_reconfigures_width():
    t = XorTrie(width=16)
    t.reset(width=4)
    assert t.width == 4 and len(t) == 0


def test_size_len():
    t = filled([1, 2, 3], 8)
    assert len(t) == 3 and t.size == 3


def test_width_property():
    assert XorTrie(width=12).width == 12


def test_stats_keys():
    assert set(XorTrie(width=8).stats()) == {"size", "width", "num_nodes"}


def test_num_nodes_grows():
    t = XorTrie(width=8)
    n0 = t.stats()["num_nodes"]
    t.insert(200)
    assert t.stats()["num_nodes"] > n0


def test_deterministic():
    vals = [100, 200, 300, 400]
    assert filled(vals, 16).max_xor(150) == filled(vals, 16).max_xor(150)


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = XorTrie(width=20)
    errors = []

    def worker(base):
        try:
            for i in range(500):
                t.insert(base * 1000 + i)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and len(t) == 5000
    assert t.contains(0) and t.contains(9 * 1000 + 499)
