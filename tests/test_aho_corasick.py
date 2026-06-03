"""Phase 142 — unit tests for AhoCorasick (pradyos/core/aho_corasick.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.aho_corasick import AhoCorasick, AhoCorasickError


def brute(patterns, text):
    out = []
    for p in set(patterns):
        m = len(p)
        if m == 0:
            continue
        for i in range(len(text) - m + 1):
            if text[i:i + m] == p:
                out.append((p, i + m - 1))     # end index, inclusive
    return sorted(out, key=lambda x: (x[1], x[0]))


def make(patterns):
    ac = AhoCorasick()
    for p in patterns:
        ac.add(p)
    return ac


# ── differential vs brute force (centerpieces) ───────────────────────────────────────────

def test_classic_ushers():
    ac = make(["he", "she", "his", "hers"])
    assert ac.search("ushers") == [("he", 3), ("she", 3), ("hers", 5)]


def test_nested_patterns():
    ac = make(["a", "ab", "abc"])
    assert ac.search("xabcy") == brute(["a", "ab", "abc"], "xabcy")


def test_differential_vs_brute():
    rng = random.Random(2026)
    for _ in range(300):
        pats = ["".join(rng.choice("abc") for _ in range(rng.randint(1, 4)))
                for _ in range(rng.randint(1, 8))]
        text = "".join(rng.choice("abc") for _ in range(rng.randint(0, 40)))
        assert make(pats).search(text) == brute(pats, text)


def test_overlapping():
    ac = make(["aa"])
    assert ac.search("aaaa") == [("aa", 1), ("aa", 2), ("aa", 3)] and ac.count("aaaa") == 3


def test_pattern_is_substring_of_another():
    ac = make(["test", "testing", "est"])
    assert ac.search("testing") == brute(["test", "testing", "est"], "testing")


def test_unicode_patterns():
    ac = make(["héllo", "llo"])
    assert ac.search("héllo héllo") == brute(["héllo", "llo"], "héllo héllo")


# ── count / contains_any ─────────────────────────────────────────────────────────────────

def test_count():
    assert make(["ab", "bc"]).count("abcabc") == 4


def test_contains_any():
    ac = make(["cat", "dog"])
    assert ac.contains_any("the dog ran") and not ac.contains_any("nothing here")


# ── edges ────────────────────────────────────────────────────────────────────────────────

def test_no_patterns():
    ac = AhoCorasick()
    assert ac.search("anything") == [] and not ac.contains_any("x")


def test_empty_text():
    assert make(["abc"]).search("") == []


def test_pattern_absent():
    assert make(["abc"]).search("xyz") == []


def test_pattern_longer_than_text():
    assert make(["abcdef"]).search("abc") == []


def test_match_end_index_semantics():
    # "cat" ends at index 2 in "cats" (0-based inclusive)
    assert make(["cat"]).search("cats") == [("cat", 2)]


def test_single_char_patterns():
    assert make(["a", "b"]).search("ab") == [("a", 0), ("b", 1)]


def test_suffix_match_via_failure_link():
    # "b" is a proper suffix of "ab"; at index 1 both must be reported (failure-link output)
    assert make(["ab", "b"]).search("ab") == [("ab", 1), ("b", 1)]


# ── duplicates / build lifecycle ─────────────────────────────────────────────────────────────

def test_add_new_returns_true_dup_false():
    ac = AhoCorasick()
    assert ac.add("he") is True and ac.add("he") is False and ac.num_patterns == 1


def test_dup_single_match():
    ac = AhoCorasick()
    ac.add("he"); ac.add("he")
    assert ac.search("hehe") == [("he", 1), ("he", 3)]


def test_auto_build_on_search():
    ac = make(["cat"])
    assert not ac.built                            # dirty until first search/build
    assert ac.search("cats") == [("cat", 2)] and ac.built


def test_re_add_marks_dirty_and_rebuilds():
    ac = make(["cat"])
    ac.search("cats")                              # build
    ac.add("dog")
    assert not ac.built
    assert ac.search("dogcat") == [("dog", 2), ("cat", 5)] and ac.built


def test_explicit_build():
    ac = make(["test"])
    ac.build()
    assert ac.built and ac.search("testing") == [("test", 3)]


def test_add_many():
    ac = AhoCorasick()
    assert ac.add_many(["a", "b", "a", "c"]) == 3 and ac.num_patterns == 3


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_add_non_str_raises():
    with pytest.raises(AhoCorasickError):
        AhoCorasick().add(5)


def test_add_empty_raises():
    with pytest.raises(AhoCorasickError):
        AhoCorasick().add("")


def test_search_non_str_raises():
    with pytest.raises(AhoCorasickError):
        make(["a"]).search(5)


def test_add_many_non_iterable_raises():
    with pytest.raises(AhoCorasickError):
        AhoCorasick().add_many(123)


def test_error_stores_detail():
    err = AhoCorasickError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ──────────────────────────────────────────────────────

def test_reset_clears():
    ac = make(["he", "she"])
    ac.reset()
    assert ac.num_patterns == 0 and ac.search("ushers") == []


def test_num_patterns_and_len():
    ac = make(["a", "b", "c"])
    assert ac.num_patterns == 3 and len(ac) == 3


def test_patterns_sorted():
    assert make(["banana", "apple", "cherry"]).patterns() == ["apple", "banana", "cherry"]


def test_built_property():
    ac = make(["x"])
    assert not ac.built
    ac.build()
    assert ac.built


def test_stats_keys():
    assert set(make(["a"]).stats()) == {"num_patterns", "num_nodes", "built"}


def test_deterministic():
    pats = ["he", "she", "his", "hers"]
    assert make(pats).search("ushers") == make(pats).search("ushers")


# ── concurrency (read-only searches on a built automaton) ──────────────────────────────────────

def test_concurrent_search():
    ac = make(["ab", "bc", "ca"])
    ac.build()
    text = "".join(random.Random(5).choice("abc") for _ in range(2000))
    expected = ac.search(text)
    errors = []
    results = []

    def worker():
        try:
            results.append(ac.search(text) == expected)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
