"""Phase 141 — unit tests for SuffixArray / Manber–Myers (pradyos/core/suffix_array.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.suffix_array import SuffixArray, SuffixArrayError


def brute_pos(t, p):
    return [i for i in range(len(t) - len(p) + 1) if t[i:i + len(p)] == p]


def brute_distinct(t):
    return len({t[i:j] for i in range(len(t)) for j in range(i + 1, len(t) + 1)})


def brute_lcp(t, sa):
    n = len(t)
    out = [0] * n
    for r in range(1, n):
        a, b, k = sa[r - 1], sa[r], 0
        while a + k < n and b + k < n and t[a + k] == t[b + k]:
            k += 1
        out[r] = k
    return out


_RNG = random.Random(2026)
_TEXTS = (["banana", "mississippi", "aaaaa", "abcabcabc", "", "a", "abracadabra"]
          + ["".join(_RNG.choice("abc") for _ in range(_RNG.randint(1, 60))) for _ in range(30)])


# ── differential vs brute force (centerpieces) ───────────────────────────────────────────

def test_sa_is_sorted_permutation():
    for t in _TEXTS:
        sa = SuffixArray(t).suffix_array()
        assert sorted(sa) == list(range(len(t)))
        assert all(t[sa[i]:] <= t[sa[i + 1]:] for i in range(len(t) - 1))


def test_count_matches_brute():
    for t in _TEXTS:
        sa = SuffixArray(t)
        for p in {t[i:i + L] for i in range(len(t)) for L in (1, 2, 3)} | {"x", "zz", "qq"}:
            if p:
                assert sa.count(p) == len(brute_pos(t, p))


def test_positions_match_brute():
    for t in _TEXTS:
        sa = SuffixArray(t)
        for p in {t[i:i + L] for i in range(len(t)) for L in (1, 2, 3, 4)} | {"ab", "zz"}:
            if p:
                assert sa.positions(p) == brute_pos(t, p)


def test_contains_matches_membership():
    for t in _TEXTS:
        sa = SuffixArray(t)
        for p in {t[i:i + L] for i in range(len(t)) for L in (1, 2)} | {"x", "abc"}:
            if p:
                assert sa.contains(p) == (p in t)


def test_lcp_matches_brute():
    for t in _TEXTS:
        sa = SuffixArray(t)
        assert sa.lcp_array() == brute_lcp(t, sa.suffix_array())


def test_distinct_substrings_matches_brute():
    for t in _TEXTS:
        assert SuffixArray(t).distinct_substrings() == brute_distinct(t)


# ── specific values ────────────────────────────────────────────────────────────────────────

def test_banana_suffix_array():
    assert SuffixArray("banana").suffix_array() == [5, 3, 1, 0, 4, 2]


def test_banana_positions_and_count():
    sa = SuffixArray("banana")
    assert sa.positions("ana") == [1, 3] and sa.count("ana") == 2


def test_overlapping_count():
    assert SuffixArray("aaaa").count("aa") == 3 and SuffixArray("aaaa").positions("aa") == [0, 1, 2]


def test_full_text_pattern():
    sa = SuffixArray("banana")
    assert sa.contains("banana") and sa.count("banana") == 1 and sa.positions("banana") == [0]


def test_distinct_substrings_banana():
    assert SuffixArray("banana").distinct_substrings() == 15


def test_count_single_char():
    assert SuffixArray("banana").count("a") == 3 and SuffixArray("banana").count("n") == 2


def test_non_overlapping_distinct_block():
    sa = SuffixArray("abcabc")
    assert sa.count("abc") == 2 and sa.positions("abc") == [0, 3]


def test_distinct_substrings_all_unique():
    assert SuffixArray("abc").distinct_substrings() == 6   # a,b,c,ab,bc,abc


def test_lcp_first_is_zero():
    assert SuffixArray("mississippi").lcp_array()[0] == 0


# ── edges ────────────────────────────────────────────────────────────────────────────────

def test_empty_text():
    sa = SuffixArray("")
    assert sa.suffix_array() == [] and sa.count("a") == 0 and not sa.contains("a")
    assert sa.lcp_array() == [] and sa.distinct_substrings() == 0


def test_single_char():
    sa = SuffixArray("z")
    assert sa.suffix_array() == [0] and sa.contains("z") and not sa.contains("y")


def test_pattern_longer_than_text():
    sa = SuffixArray("ab")
    assert sa.count("abc") == 0 and not sa.contains("abc")


def test_pattern_absent():
    assert SuffixArray("banana").count("xyz") == 0 and SuffixArray("banana").positions("xyz") == []


def test_repeated_char():
    sa = SuffixArray("aaaa")
    assert sa.suffix_array() == [3, 2, 1, 0] and sa.distinct_substrings() == 4   # a, aa, aaa, aaaa


def test_unicode_text():
    sa = SuffixArray("héllo héllo")
    assert sa.count("héllo") == 2 and sa.contains("llo")


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_empty_pattern_raises():
    for op in ("count", "contains", "positions"):
        with pytest.raises(SuffixArrayError):
            getattr(SuffixArray("abc"), op)("")


def test_non_str_pattern_raises():
    with pytest.raises(SuffixArrayError):
        SuffixArray("abc").count(5)


def test_positions_non_str_raises():
    with pytest.raises(SuffixArrayError):
        SuffixArray("abc").positions(5)


def test_non_str_text_raises():
    with pytest.raises(SuffixArrayError):
        SuffixArray(123)


def test_error_stores_detail():
    err = SuffixArrayError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / introspection ───────────────────────────────────────────────────────────

def test_build_replaces():
    sa = SuffixArray("abc")
    sa.build("xyzxyz")
    assert sa.text == "xyzxyz" and sa.count("xyz") == 2


def test_reset_clears():
    sa = SuffixArray("abc")
    sa.reset()
    assert len(sa) == 0 and sa.suffix_array() == []


def test_size_len_text():
    sa = SuffixArray("hello")
    assert len(sa) == 5 and sa.size == 5 and sa.text == "hello"


def test_lcp_array_length():
    assert len(SuffixArray("mississippi").lcp_array()) == 11


def test_stats_keys():
    assert set(SuffixArray("ab").stats()) == {"size", "num_suffixes", "distinct_substrings"}


def test_deterministic():
    assert SuffixArray("mississippi").suffix_array() == SuffixArray("mississippi").suffix_array()


# ── concurrency (read-only queries on a static index) ──────────────────────────────────────────

def test_concurrent_queries():
    text = "".join(random.Random(5).choice("abcd") for _ in range(2000))
    sa = SuffixArray(text)
    errors = []
    results = []

    def worker():
        try:
            ok = all(sa.count(text[i:i + 3]) == len(brute_pos(text, text[i:i + 3]))
                     for i in range(0, 1990, 100))
            results.append(ok)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
