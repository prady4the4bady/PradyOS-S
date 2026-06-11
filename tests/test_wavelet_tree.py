"""Phase 135 — unit tests for WaveletTree / Grossi–Gupta–Vitter (pradyos/core/wavelet_tree.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.wavelet_tree import WaveletTree, WaveletTreeError


def naive_select(seq, sym, k):
    c = 0
    for p, x in enumerate(seq):
        if x == sym:
            c += 1
            if c == k:
                return p
    return None


_RNG = random.Random(2026)
_CONFIGS = {
    "sigma5": [_RNG.randint(0, 4) for _ in range(500)],
    "sigma50": [_RNG.randint(0, 49) for _ in range(1500)],
    "sigma2": [_RNG.randint(0, 1) for _ in range(300)],
    "sigma3": [_RNG.randint(0, 2) for _ in range(400)],       # non-power-of-2
    "sigma7": [_RNG.randint(0, 6) for _ in range(600)],       # non-power-of-2
    "strings": [_RNG.choice(["apple", "banana", "cherry", "date"]) for _ in range(400)],
    "wide": [_RNG.choice([10, 20, 30, 1000, -5]) for _ in range(300)],
}


# ── differential vs naive (the centerpiece) ─────────────────────────────────────────────

def test_access_matches_sequence():
    for seq in _CONFIGS.values():
        wt = WaveletTree(seq)
        assert all(wt.access(i) == seq[i] for i in range(len(seq)))


def test_rank_matches_naive_including_absent():
    for seq in _CONFIGS.values():
        wt = WaveletTree(seq)
        n = len(seq)
        absent = "ZZZ" if isinstance(seq[0], str) else 10 ** 9
        for sym in sorted(set(seq)) + [absent]:
            for i in range(0, n + 1, max(1, n // 30)):
                assert wt.rank(sym, i) == seq[:i].count(sym)


def test_select_matches_naive():
    for seq in _CONFIGS.values():
        wt = WaveletTree(seq)
        for sym in sorted(set(seq)):
            for k in range(1, seq.count(sym) + 1):
                assert wt.select(sym, k) == naive_select(seq, sym, k)


def test_quantile_matches_sorted():
    rng = random.Random(1)
    for seq in _CONFIGS.values():
        wt = WaveletTree(seq)
        n = len(seq)
        for _ in range(80):
            i = rng.randint(0, n - 1)
            j = rng.randint(i + 1, n)
            k = rng.randint(1, j - i)
            assert wt.quantile(i, j, k) == sorted(seq[i:j])[k - 1]


def test_range_count_matches_naive():
    rng = random.Random(2)
    for seq in _CONFIGS.values():
        wt = WaveletTree(seq)
        n = len(seq)
        alpha = sorted(set(seq))
        for _ in range(80):
            i = rng.randint(0, n)
            j = rng.randint(i, n)
            a, b = sorted(rng.sample(alpha, 2)) if len(alpha) >= 2 else (alpha[0], alpha[0])
            assert wt.range_count(i, j, a, b) == sum(1 for x in seq[i:j] if a <= x < b)


# ── identities ───────────────────────────────────────────────────────────────────────────

def test_select_rank_access_identity():
    seq = [random.Random(7).randint(0, 9) for _ in range(3000)]
    seq = [(_ * 7 + 3) % 10 for _ in range(3000)]            # deterministic mixed sequence
    wt = WaveletTree(seq)
    for s in set(seq):
        for k in range(1, seq.count(s) + 1):
            p = wt.select(s, k)
            assert wt.access(p) == s and wt.rank(s, p) == k - 1 and wt.rank(s, p + 1) == k


def test_rank_full_is_total_count():
    seq = _CONFIGS["sigma5"]
    wt = WaveletTree(seq)
    assert all(wt.rank(s, len(seq)) == seq.count(s) for s in set(seq))


# ── edge cases ─────────────────────────────────────────────────────────────────────────────

def test_empty():
    wt = WaveletTree([])
    assert len(wt) == 0 and wt.alphabet_size == 0 and wt.rank(5, 0) == 0


def test_empty_access_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([]).access(0)


def test_sigma_one():
    wt = WaveletTree([7, 7, 7, 7])
    assert wt.access(2) == 7 and wt.rank(7, 4) == 4 and wt.select(7, 3) == 2
    assert wt.quantile(0, 4, 1) == 7 and wt.alphabet_size == 1


def test_sigma_two():
    wt = WaveletTree([0, 1, 0, 1, 1])
    assert wt.rank(1, 5) == 3 and wt.select(0, 2) == 2 and wt.quantile(0, 5, 1) == 0


def test_single_element():
    wt = WaveletTree(["only"])
    assert wt.access(0) == "only" and wt.rank("only", 1) == 1 and len(wt) == 1


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_mixed_kind_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, "x"])


def test_bool_symbol_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([True, False])


def test_non_orderable_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([[1], [2]])


def test_access_out_of_range_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, 2, 3]).access(3)


def test_rank_index_out_of_range_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, 2, 3]).rank(2, 4)


def test_select_overcount_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, 2, 3]).select(2, 2)             # only one '2'


def test_select_k_zero_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, 2, 3]).select(2, 0)


def test_rank_absent_symbol_is_zero():
    assert WaveletTree([1, 2, 3]).rank(99, 3) == 0


def test_quantile_bad_range_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, 2, 3]).quantile(2, 2, 1)        # empty range


def test_quantile_k_out_of_range_raises():
    with pytest.raises(WaveletTreeError):
        WaveletTree([1, 2, 3]).quantile(0, 2, 3)        # only 2 elements


def test_error_stores_detail():
    err = WaveletTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── range_count specifics ────────────────────────────────────────────────────────────────────

def test_range_count_empty_range():
    assert WaveletTree([1, 2, 3, 4]).range_count(2, 2, 1, 5) == 0


def test_range_count_full_alphabet():
    wt = WaveletTree([1, 2, 3, 4, 5])
    assert wt.range_count(0, 5, 0, 100) == 5


def test_range_count_inverted_bounds_zero():
    assert WaveletTree([1, 2, 3, 4]).range_count(0, 4, 5, 1) == 0


def test_range_count_half_open():
    wt = WaveletTree([1, 2, 3, 4, 5])
    assert wt.range_count(0, 5, 2, 4) == 2              # values 2,3 (4 excluded)


# ── determinism / build / reset / introspection ───────────────────────────────────────────────

def test_deterministic():
    seq = _CONFIGS["sigma50"]
    assert WaveletTree(seq).quantile(10, 500, 7) == WaveletTree(seq).quantile(10, 500, 7)


def test_build_replaces():
    wt = WaveletTree([1, 2, 3])
    wt.build(["a", "b", "a"])
    assert wt.alphabet_size == 2 and wt.rank("a", 3) == 2


def test_reset_clears():
    wt = WaveletTree([1, 2, 3])
    wt.reset()
    assert len(wt) == 0 and wt.alphabet_size == 0


def test_alphabet_size_and_symbols():
    wt = WaveletTree([5, 1, 5, 3, 1])
    assert wt.alphabet_size == 3 and wt.symbols == [1, 3, 5]


def test_stats_keys():
    assert set(WaveletTree([1, 2]).stats()) == {"size", "alphabet_size", "height", "kind"}


def test_len():
    assert len(WaveletTree([1, 2, 3, 4, 5])) == 5


# ── concurrency (read-only queries on a static index) ──────────────────────────────────────────

def test_concurrent_queries():
    seq = [(_ * 13 + 5) % 20 for _ in range(4000)]
    wt = WaveletTree(seq)
    errors = []
    results = []

    def worker():
        try:
            ok = all(wt.access(i) == seq[i] for i in range(0, 4000, 200))
            ok = ok and all(wt.rank(s, 4000) == seq.count(s) for s in range(20))
            results.append(ok)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
