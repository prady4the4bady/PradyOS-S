"""Phase 133 — unit tests for SplayTree / Sleator–Tarjan (pradyos/core/splay_tree.py)."""
from __future__ import annotations

import bisect
import random
import threading

import pytest

from pradyos.core.splay_tree import SplayTree, SplayTreeError

_MISS = object()


def build(n=1000, seed=0):
    t = SplayTree()
    keys = list(range(n))
    random.Random(seed).shuffle(keys)
    for k in keys:
        t.insert(k, k * 10)
    return t


# ── ordered-map semantics ───────────────────────────────────────────────────────────────

def test_insert_find_roundtrip():
    t = SplayTree()
    t.insert("a", 1)
    assert t.find("a") == 1


def test_in_order_sorted():
    assert build(500).keys() == list(range(500))


def test_update_in_place():
    t = SplayTree()
    t.insert(1, "x")
    t.insert(1, "y")
    assert t.find(1) == "y" and len(t) == 1


def test_find_missing_returns_default():
    assert build(100).find(999, "dflt") == "dflt"


def test_contains():
    t = build(100)
    assert 50 in t and 999 not in t


def test_delete_present():
    t = build(100)
    assert t.delete(50) is True and 50 not in t and len(t) == 99


def test_delete_absent():
    assert build(100).delete(999) is False


def test_delete_preserves_order():
    t = build(100)
    for k in (50, 25, 75, 0, 99):
        t.delete(k)
    assert t.keys() == [k for k in range(100) if k not in {50, 25, 75, 0, 99}]


def test_len_tracks_size():
    assert len(build(300)) == 300


def test_keys_sorted_after_random_ops():
    t = SplayTree()
    rng = random.Random(1)
    ref = set()
    for _ in range(500):
        k = rng.randint(0, 200)
        t.insert(k, k); ref.add(k)
    assert t.keys() == sorted(ref)


# ── splay behaviour ────────────────────────────────────────────────────────────────────

def test_find_splays_to_root():
    t = build(500)
    t.find(321)
    assert t.root_key == 321


def test_insert_splays_to_root():
    t = build(500)
    t.insert(1234, 1)
    assert t.root_key == 1234


def test_repeated_access_stays_root():
    t = build(500)
    for _ in range(5):
        t.find(250)
    assert t.root_key == 250


def test_min_max():
    t = build(500)
    assert t.min() == 0 and t.max() == 499


def test_min_splays_to_root():
    t = build(500)
    assert t.min() == 0 and t.root_key == 0


def test_max_splays_to_root():
    t = build(500)
    assert t.max() == 499 and t.root_key == 499


def test_empty_min_raises():
    with pytest.raises(SplayTreeError):
        SplayTree().min()


def test_empty_max_raises():
    with pytest.raises(SplayTreeError):
        SplayTree().max()


# ── predecessor / successor ──────────────────────────────────────────────────────────────

def test_predecessor():
    t = build(100)
    assert t.predecessor(50) == 49 and t.predecessor(0) is None


def test_successor():
    t = build(100)
    assert t.successor(50) == 51 and t.successor(99) is None


def test_predecessor_successor_of_absent_key():
    t = SplayTree()
    for k in (10, 20, 30, 40):
        t.insert(k, k)
    assert t.predecessor(25) == 20 and t.successor(25) == 30


def test_pred_succ_splay_to_root():
    t = build(200)
    assert t.successor(100) == 101 and t.root_key == 101


# ── differential vs dict (ground truth for an exact ordered map) ─────────────────────────

def test_differential_vs_dict():
    rng = random.Random(42)
    ref: dict = {}
    st = SplayTree()
    for _ in range(8000):
        k = rng.randint(0, 800)
        r = rng.random()
        if r < 0.55:
            ref[k] = k * 7
            st.insert(k, k * 7)
        elif r < 0.75:
            ref.pop(k, None)
            st.delete(k)
        else:
            assert st.find(k, _MISS) == ref.get(k, _MISS)
    assert st.keys() == sorted(ref)
    assert all(st.find(k) == ref[k] for k in ref) and len(st) == len(ref)


def test_differential_pred_succ_vs_sorted():
    rng = random.Random(7)
    ref = set()
    st = SplayTree()
    for _ in range(1500):
        k = rng.randint(0, 1000)
        st.insert(k, k); ref.add(k)
    sk = sorted(ref)
    for q in (rng.randint(-5, 1005) for _ in range(200)):
        i = bisect.bisect_left(sk, q)
        exp_pred = sk[i - 1] if i > 0 else None
        j = bisect.bisect_right(sk, q)
        exp_succ = sk[j] if j < len(sk) else None
        assert st.predecessor(q) == exp_pred and st.successor(q) == exp_succ


# ── key kinds / types ──────────────────────────────────────────────────────────────────────

def test_float_keys():
    t = SplayTree()
    for v in (1.5, 0.3, 2.7, 1.1):
        t.insert(v, v)
    assert t.keys() == sorted([1.5, 0.3, 2.7, 1.1])


def test_str_keys():
    t = SplayTree()
    for s in ("banana", "apple", "cherry"):
        t.insert(s, s)
    assert t.keys() == ["apple", "banana", "cherry"]


def test_bool_key_rejected():
    with pytest.raises(SplayTreeError):
        SplayTree().insert(True, 1)


def test_non_orderable_key_rejected():
    with pytest.raises(SplayTreeError):
        SplayTree().insert([1, 2], 1)


def test_mixed_kind_insert_raises():
    t = SplayTree()
    t.insert(1, 1)
    with pytest.raises(SplayTreeError):
        t.insert("x", 1)


def test_find_wrong_kind_returns_default():
    t = SplayTree()
    t.insert(1, 1)
    assert t.find("x", "dflt") == "dflt" and t.delete("x") is False


# ── determinism ──────────────────────────────────────────────────────────────────────────

def _seq_tree():
    t = SplayTree()
    for k in (3, 1, 4, 1, 5, 9, 2, 6):
        t.insert(k, k)
    return t


def test_deterministic_keys():
    assert _seq_tree().keys() == _seq_tree().keys()


def test_deterministic_root():
    assert _seq_tree().root_key == _seq_tree().root_key


# ── reset / introspection ──────────────────────────────────────────────────────────────────

def test_reset_clears():
    t = build(100)
    t.reset()
    assert len(t) == 0 and t.root_key is None and t.find(5) is None


def test_height_in_range():
    t = build(200)
    assert 1 <= t.height() <= len(t)


def test_stats_keys():
    assert set(SplayTree().stats()) == {"size", "height", "root_key", "key_kind"}


def test_key_kind_property():
    t = SplayTree()
    assert t.key_kind is None
    t.insert(1, 1)
    assert t.key_kind == "num"


def test_error_stores_detail():
    err = SplayTreeError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = SplayTree()
    errors = []

    def worker(base):
        try:
            for i in range(500):
                t.insert(base * 1000 + i, i)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and len(t) == 5000
    assert t.keys() == sorted(b * 1000 + i for b in range(10) for i in range(500))
