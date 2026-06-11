"""Phase 77 — unit tests for MerkleTree (data-integrity proofs)."""
from __future__ import annotations

import math
import threading

import pytest

from pradyos.core.merkle_tree import MerkleTree


# ── empty / construction ──────────────────────────────────────────────────────

def test_empty_root_is_none():
    assert MerkleTree().root is None


def test_empty_stats():
    stats = MerkleTree().stats()
    assert stats == {"leaves": 0, "height": 0, "root": None}


def test_empty_len_zero():
    assert len(MerkleTree()) == 0


# ── add / root ────────────────────────────────────────────────────────────────

def test_root_set_after_add():
    t = MerkleTree()
    t.add("a")
    assert t.root is not None


def test_root_is_sha256_hex():
    t = MerkleTree()
    t.add("a")
    root = t.root
    assert len(root) == 64
    assert all(c in "0123456789abcdef" for c in root)


def test_root_changes_after_add():
    t = MerkleTree()
    t.add("a")
    r1 = t.root
    t.add("b")
    assert t.root != r1


def test_len_tracks_leaves():
    t = MerkleTree()
    t.add("a"); t.add("b"); t.add("c")
    assert len(t) == 3


def test_build_returns_root_equal_to_property():
    t = MerkleTree()
    t.add("a"); t.add("b")
    assert t.build() == t.root


# ── determinism / ordering ────────────────────────────────────────────────────

def test_same_items_same_root():
    a, b = MerkleTree(), MerkleTree()
    for x in ("a", "b", "c"):
        a.add(x); b.add(x)
    assert a.root == b.root


def test_order_changes_root():
    a, b = MerkleTree(), MerkleTree()
    a.add("a"); a.add("b")
    b.add("b"); b.add("a")
    assert a.root != b.root


# ── verify ────────────────────────────────────────────────────────────────────

def test_verify_added_item_true():
    t = MerkleTree()
    t.add("a"); t.add("b"); t.add("c")
    assert t.verify("a") is True
    assert t.verify("c") is True


def test_verify_unknown_item_false():
    t = MerkleTree()
    t.add("a")
    assert t.verify("ghost") is False


def test_verify_on_empty_false():
    assert MerkleTree().verify("a") is False


def test_verify_all_for_various_sizes():
    for n in (1, 2, 3, 5, 8, 9, 16):
        t = MerkleTree()
        for i in range(n):
            t.add(f"item-{i}")
        assert all(t.verify(f"item-{i}") for i in range(n))


# ── proof ─────────────────────────────────────────────────────────────────────

def test_proof_length_is_ceil_log2():
    for n in (2, 3, 4, 5, 8, 9, 16):
        t = MerkleTree()
        for i in range(n):
            t.add(f"item-{i}")
        expected = math.ceil(math.log2(n))
        assert len(t.proof("item-0")) == expected


def test_proof_single_leaf_is_empty():
    t = MerkleTree()
    t.add("only")
    assert t.proof("only") == []


def test_proof_entries_have_hash_and_side():
    t = MerkleTree()
    for x in ("a", "b", "c", "d"):
        t.add(x)
    for step in t.proof("a"):
        assert set(step) == {"hash", "side"}
        assert step["side"] in ("left", "right")
        assert len(step["hash"]) == 64


def test_proof_recomputes_root_for_odd_tree():
    # n=3 exercises odd-leaf duplication on level 0
    t = MerkleTree()
    for x in ("x", "y", "z"):
        t.add(x)
    assert t.verify("z") is True  # verify recomputes root from proof
    assert len(t.proof("z")) == 2


def test_proof_unknown_item_raises():
    t = MerkleTree()
    t.add("a")
    with pytest.raises(ValueError):
        t.proof("missing")


def test_proof_empty_tree_raises():
    with pytest.raises(ValueError):
        MerkleTree().proof("a")


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys():
    t = MerkleTree()
    t.add("a")
    assert set(t.stats()) == {"leaves", "height", "root"}


def test_stats_height_is_ceil_log2():
    for n in (1, 2, 4, 5, 8):
        t = MerkleTree()
        for i in range(n):
            t.add(f"i{i}")
        expected = math.ceil(math.log2(n)) if n > 1 else 0
        assert t.stats()["height"] == expected


def test_stats_leaf_count():
    t = MerkleTree()
    t.add("a"); t.add("b")
    assert t.stats()["leaves"] == 2


# ── clear / errors / heterogeneous ────────────────────────────────────────────

def test_clear_resets():
    t = MerkleTree()
    t.add("a"); t.add("b")
    t.clear()
    assert t.root is None
    assert len(t) == 0


def test_add_none_raises():
    with pytest.raises(ValueError):
        MerkleTree().add(None)


def test_non_string_items():
    t = MerkleTree()
    t.add(42)
    t.add((1, 2))
    assert t.verify(42) is True
    assert t.verify((1, 2)) is True


def test_unicode_items():
    t = MerkleTree()
    t.add("naïve"); t.add("Ω")
    assert t.verify("naïve") is True


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_adds_are_thread_safe():
    t = MerkleTree()
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(100):
                t.add(f"k-{base}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert errors == []
    assert len(t) == 1000
    assert t.root is not None
    # a sample of leaves still verify against the rebuilt root
    assert all(t.verify(f"k-{b}-{i}") for b in range(10) for i in (0, 50, 99))
