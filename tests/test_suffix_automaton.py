"""Phase 151 — unit tests for SuffixAutomaton (pradyos/core/suffix_automaton.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.suffix_automaton import SuffixAutomaton, SuffixAutomatonError


def _brute(s):
    return {s[i:j] for i in range(len(s)) for j in range(i + 1, len(s) + 1)}


# ── differential vs brute substring set (centerpieces) ───────────────────────────────────

def test_distinct_substrings_differential():
    rng = random.Random(1)
    for _ in range(200):
        n = rng.randint(0, 40)
        s = "".join(rng.choice("abc") for _ in range(n))
        assert SuffixAutomaton(s).distinct_substrings() == len(_brute(s))


def test_distinct_substrings_larger_alphabet():
    rng = random.Random(2)
    for _ in range(100):
        n = rng.randint(0, 60)
        s = "".join(rng.choice("abcdefgh") for _ in range(n))
        assert SuffixAutomaton(s).distinct_substrings() == len(_brute(s))


def test_contains_differential():
    rng = random.Random(3)
    for _ in range(150):
        n = rng.randint(1, 30)
        s = "".join(rng.choice("ab") for _ in range(n))
        sam = SuffixAutomaton(s); bs = _brute(s)
        for _ in range(5):
            i = rng.randrange(n); j = rng.randint(i + 1, n); p = s[i:j]
            assert sam.contains(p) == (p in bs)
        for _ in range(5):
            p = "".join(rng.choice("abc") for _ in range(rng.randint(1, 5)))
            assert sam.contains(p) == (p in bs)


def test_large_differential():
    rng = random.Random(4)
    s = "".join(rng.choice("abcde") for _ in range(2000))
    assert SuffixAutomaton(s).distinct_substrings() == len(_brute(s))


def test_extend_incremental_equals_build():
    a = SuffixAutomaton()
    for ch in "abcabc":
        a.extend(ch)
    b = SuffixAutomaton("abcabc")
    assert a.distinct_substrings() == b.distinct_substrings() == len(_brute("abcabc"))


# ── structured strings ───────────────────────────────────────────────────────────────────

def test_aaaa():
    assert SuffixAutomaton("aaaa").distinct_substrings() == 4


def test_repeated_chars():
    assert SuffixAutomaton("aaaaa").distinct_substrings() == 5


def test_abab():
    assert SuffixAutomaton("abab").distinct_substrings() == len(_brute("abab"))


def test_abcabc():
    assert SuffixAutomaton("abcabc").distinct_substrings() == len(_brute("abcabc"))


def test_banana():
    assert SuffixAutomaton("banana").distinct_substrings() == len(_brute("banana"))


def test_single_char():
    assert SuffixAutomaton("z").distinct_substrings() == 1


def test_empty_string():
    sam = SuffixAutomaton("")
    assert sam.distinct_substrings() == 0 and sam.length == 0 and sam.num_states == 1


def test_two_distinct_chars():
    assert SuffixAutomaton("ab").distinct_substrings() == 3      # a, b, ab


# ── unicode ──────────────────────────────────────────────────────────────────────────────

def test_unicode_distinct():
    u = "héllo☃héllo"
    assert SuffixAutomaton(u).distinct_substrings() == len(_brute(u))


def test_unicode_contains():
    u = "héllo☃héllo"
    sam = SuffixAutomaton(u)
    assert sam.contains("llo☃") and not sam.contains("xyz")


# ── membership semantics ──────────────────────────────────────────────────────────────────

def test_contains_empty_true():
    assert SuffixAutomaton("abc").contains("") is True


def test_contains_full_string():
    assert SuffixAutomaton("mississippi").contains("mississippi")


def test_contains_substrings():
    sam = SuffixAutomaton("mississippi")
    assert sam.contains("ippi") and sam.contains("miss") and sam.contains("issi")


def test_not_contains():
    sam = SuffixAutomaton("mississippi")
    assert not sam.contains("mississippix") and not sam.contains("z")


def test_every_substring_contained():
    s = "abracadabra"
    sam = SuffixAutomaton(s)
    assert all(sam.contains(p) for p in _brute(s))


def test_num_states_bound():
    rng = random.Random(5)
    for _ in range(50):
        n = rng.randint(2, 80)
        s = "".join(rng.choice("abcd") for _ in range(n))
        assert SuffixAutomaton(s).num_states <= 2 * n


# ── build / extend / reset ─────────────────────────────────────────────────────────────────

def test_build_replaces():
    sam = SuffixAutomaton("hello")
    sam.build("world")
    assert sam.distinct_substrings() == len(_brute("world")) and not sam.contains("hello")


def test_extend_single():
    sam = SuffixAutomaton()
    sam.extend("a")
    assert sam.contains("a") and sam.length == 1 and sam.distinct_substrings() == 1


def test_reset_clears():
    sam = SuffixAutomaton("hello")
    sam.reset()
    assert sam.num_states == 1 and sam.distinct_substrings() == 0 and sam.length == 0


def test_length():
    assert SuffixAutomaton("hello").length == 5 and len(SuffixAutomaton("hello")) == 5


def test_deterministic():
    assert SuffixAutomaton("mississippi").distinct_substrings() == \
        SuffixAutomaton("mississippi").distinct_substrings()


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_build_non_str_raises():
    with pytest.raises(SuffixAutomatonError):
        SuffixAutomaton(123)


def test_extend_multichar_raises():
    with pytest.raises(SuffixAutomatonError):
        SuffixAutomaton().extend("ab")


def test_extend_non_str_raises():
    with pytest.raises(SuffixAutomatonError):
        SuffixAutomaton().extend(5)


def test_contains_non_str_raises():
    with pytest.raises(SuffixAutomatonError):
        SuffixAutomaton("a").contains(7)


def test_error_stores_detail():
    err = SuffixAutomatonError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection ──────────────────────────────────────────────────────────────────────────

def test_num_states_property():
    assert SuffixAutomaton("").num_states == 1 and SuffixAutomaton("ab").num_states >= 2


def test_stats_keys():
    assert set(SuffixAutomaton("ab").stats()) == {"num_states", "length", "distinct_substrings", "transitions"}


def test_stats_values():
    s = SuffixAutomaton("abcabc").stats()
    assert s["length"] == 6 and s["distinct_substrings"] == len(_brute("abcabc"))


# ── concurrency (read-only queries on a built automaton) ───────────────────────────────────

def test_concurrent_contains():
    s = "abracadabra"
    sam = SuffixAutomaton(s)
    subs = list(_brute(s))
    errors = []
    results = []

    def worker():
        try:
            results.append(all(sam.contains(p) for p in subs))
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
