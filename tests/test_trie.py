"""Phase 83 — unit tests for SovereignTrie (prefix tree)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.trie import KeyNotFoundError, SovereignTrie


def _seed(*keys: str) -> SovereignTrie:
    t = SovereignTrie()
    for i, k in enumerate(keys):
        t.insert(k, i)
    return t


# ── insert / search ───────────────────────────────────────────────────────────

def test_insert_search_round_trip():
    t = SovereignTrie()
    t.insert("cat", 42)
    assert t.search("cat") == 42


def test_insert_default_value_is_true():
    t = SovereignTrie()
    t.insert("k")
    assert t.search("k") is True


def test_insert_overwrites_value():
    t = SovereignTrie()
    t.insert("k", 1)
    t.insert("k", 2)
    assert t.search("k") == 2
    assert len(t) == 1


def test_insert_empty_key_raises():
    with pytest.raises(ValueError):
        SovereignTrie().insert("")


def test_insert_non_string_raises():
    with pytest.raises(ValueError):
        SovereignTrie().insert(5)  # type: ignore[arg-type]


def test_search_absent_raises_key_not_found():
    t = _seed("cat")
    with pytest.raises(KeyNotFoundError):
        t.search("dog")


def test_key_not_found_carries_key():
    t = SovereignTrie()
    try:
        t.search("ghost")
    except KeyNotFoundError as exc:
        assert exc.key == "ghost"
        assert "ghost" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected KeyNotFoundError")


def test_search_prefix_is_not_a_key():
    t = _seed("cat")
    with pytest.raises(KeyNotFoundError):
        t.search("ca")


# ── contains / len / keys ─────────────────────────────────────────────────────

def test_contains_true_and_false():
    t = _seed("cat")
    assert t.contains("cat") is True
    assert t.contains("ca") is False
    assert t.contains("dog") is False


def test_contains_non_string_is_false():
    assert SovereignTrie().contains(5) is False  # type: ignore[arg-type]


def test_len_tracks_distinct_keys():
    t = _seed("a", "b", "c", "a")
    assert len(t) == 3


def test_keys_sorted():
    t = _seed("dog", "cat", "car")
    assert t.keys() == ["car", "cat", "dog"]


# ── starts_with ───────────────────────────────────────────────────────────────

def test_starts_with_returns_sorted_matches():
    t = _seed("car", "card", "cat", "dog")
    assert [k for k, _ in t.starts_with("ca")] == ["car", "card", "cat"]


def test_starts_with_includes_values():
    t = SovereignTrie()
    t.insert("car", "A")
    t.insert("cart", "B")
    assert t.starts_with("car") == [("car", "A"), ("cart", "B")]


def test_starts_with_empty_prefix_returns_all():
    t = _seed("b", "a", "c")
    assert [k for k, _ in t.starts_with("")] == ["a", "b", "c"]


def test_starts_with_absent_prefix_returns_empty():
    t = _seed("cat")
    assert t.starts_with("zzz") == []


def test_starts_with_exact_key_as_prefix():
    t = _seed("cat", "cats")
    assert [k for k, _ in t.starts_with("cat")] == ["cat", "cats"]


def test_starts_with_non_string_raises():
    with pytest.raises(ValueError):
        SovereignTrie().starts_with(5)  # type: ignore[arg-type]


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_removes_key():
    t = _seed("cat")
    assert t.delete("cat") is True
    assert not t.contains("cat")
    assert len(t) == 0


def test_delete_absent_returns_false():
    t = _seed("cat")
    assert t.delete("dog") is False
    assert t.delete("ca") is False


def test_delete_prunes_dangling_nodes():
    t = _seed("car", "card")
    before = t.stats()["nodes"]
    t.delete("card")
    assert t.stats()["nodes"] < before     # the 'd' node was pruned
    assert t.search("car") == 0


def test_delete_preserves_shared_branch():
    t = _seed("car", "card")
    t.delete("car")               # 'car' is a prefix of 'card'
    assert not t.contains("car")
    assert t.contains("card")     # longer key survives


def test_delete_non_string_raises():
    with pytest.raises(ValueError):
        SovereignTrie().delete(5)  # type: ignore[arg-type]


# ── serialization ─────────────────────────────────────────────────────────────

def test_to_dict_structure():
    t = _seed("a", "b")
    d = t.to_dict()
    assert set(d) == {"size", "nodes", "keys"}
    assert d["size"] == 2


def test_to_dict_round_trip():
    t = SovereignTrie()
    t.insert("apple", 1); t.insert("app", 2); t.insert("banana", 3)
    snapshot = t.to_dict()["keys"]
    rebuilt = SovereignTrie()
    for k, v in snapshot.items():
        rebuilt.insert(k, v)
    assert rebuilt.to_dict()["keys"] == snapshot


def test_stats_keys():
    assert set(SovereignTrie().stats()) == {"size", "nodes"}


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_resets():
    t = _seed("a", "b", "c")
    t.clear()
    assert len(t) == 0
    assert t.stats()["nodes"] == 1
    assert t.starts_with("") == []


# ── heterogeneous keys / values ───────────────────────────────────────────────

def test_unicode_keys():
    t = SovereignTrie()
    t.insert("naïve", 1)
    t.insert("naïveté", 2)
    assert [k for k, _ in t.starts_with("naïve")] == ["naïve", "naïveté"]


def test_arbitrary_values():
    t = SovereignTrie()
    t.insert("k", {"nested": [1, 2, 3]})
    assert t.search("k") == {"nested": [1, 2, 3]}


# ── robustness / concurrency ──────────────────────────────────────────────────

def test_long_key_no_recursion_limit():
    t = SovereignTrie()
    key = "a" * 5000
    t.insert(key, 1)
    assert t.search(key) == 1
    assert [k for k, _ in t.starts_with("a" * 100)] == [key]


def test_concurrent_inserts_are_thread_safe():
    t = SovereignTrie()
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(100):
                t.insert(f"k-{base}-{i}", base * 1000 + i)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert errors == []
    assert len(t) == 1000
    assert t.search("k-5-50") == 5050
