"""Phase 162 — unit tests for ImplicitTreap (pradyos/core/implicit_treap.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.implicit_treap import ImplicitTreap, ImplicitTreapError


# ── differential vs Python list (centerpieces) ───────────────────────────────────────────

def test_differential_vs_list():
    rng = random.Random(1)
    for trial in range(40):
        t = ImplicitTreap(seed=trial); ref = []
        for _ in range(300):
            op = rng.random(); n = len(ref)
            if op < 0.4 or n == 0:
                i = rng.randint(0, n); v = rng.randint(-100, 100); t.insert(i, v); ref.insert(i, v)
            elif op < 0.6:
                i = rng.randrange(n)
                assert t.delete(i) == ref[i]; ref.pop(i)
            elif op < 0.75:
                i = rng.randrange(n)
                assert t.get(i) == ref[i]
            elif op < 0.9:
                i = rng.randrange(n); v = rng.randint(-100, 100); t.set(i, v); ref[i] = v
            else:
                lo = rng.randrange(n); hi = rng.randint(lo, n - 1)
                assert t.range_sum(lo, hi) == sum(ref[lo:hi + 1])
        assert t.to_list() == ref and t.size == len(ref)


def test_large_differential():
    rng = random.Random(2)
    t = ImplicitTreap(seed=99); ref = []
    for _ in range(2000):
        n = len(ref)
        if rng.random() < 0.55 or n == 0:
            i = rng.randint(0, n); v = rng.randint(-50, 50); t.insert(i, v); ref.insert(i, v)
        else:
            i = rng.randrange(n); t.delete(i); ref.pop(i)
    assert t.to_list() == ref and t.size == len(ref)


# ── positional ops ─────────────────────────────────────────────────────────────────────────

def test_insert_boundaries():
    t = ImplicitTreap()
    t.insert(0, 1); t.insert(0, 0); t.insert(2, 3); t.insert(2, 2)
    assert t.to_list() == [0, 1, 2, 3]


def test_delete_positions():
    t = ImplicitTreap()
    for v in range(5):
        t.insert(v, v)
    assert t.delete(0) == 0 and t.to_list() == [1, 2, 3, 4]
    assert t.delete(3) == 4 and t.to_list() == [1, 2, 3]
    assert t.delete(1) == 2 and t.to_list() == [1, 3]


def test_get():
    t = ImplicitTreap()
    for v in (10, 20, 30, 40, 50):
        t.insert(t.size, v)
    assert t.get(0) == 10 and t.get(4) == 50 and t.get(2) == 30


def test_set():
    t = ImplicitTreap()
    for v in (10, 20, 30, 40, 50):
        t.insert(t.size, v)
    t.set(2, 99)
    assert t.get(2) == 99 and t.to_list() == [10, 20, 99, 40, 50]


def test_range_sum():
    t = ImplicitTreap()
    for v in (10, 20, 30, 40, 50):
        t.insert(t.size, v)
    assert t.range_sum(0, 4) == 150 and t.range_sum(1, 3) == 90 and t.range_sum(2, 2) == 30


def test_thousand_append():
    t = ImplicitTreap()
    for v in range(1000):
        t.insert(t.size, v)
    assert t.to_list() == list(range(1000)) and t.size == 1000
    assert t.range_sum(0, 999) == sum(range(1000))
    assert all(t.get(i) == i for i in (0, 1, 500, 998, 999))


def test_insert_middle_of_large():
    t = ImplicitTreap()
    for v in range(1000):
        t.insert(t.size, v)
    t.insert(500, -1)
    assert t.get(500) == -1 and t.get(501) == 500 and t.size == 1001


def test_insert_at_size_appends():
    t = ImplicitTreap()
    t.insert(0, 5); t.insert(t.size, 7)
    assert t.to_list() == [5, 7]


def test_delete_returns_value():
    t = ImplicitTreap()
    t.insert(0, 42)
    assert t.delete(0) == 42 and t.is_empty()


def test_range_sum_single_and_full():
    t = ImplicitTreap()
    for v in (3, 1, 4, 1, 5):
        t.insert(t.size, v)
    assert t.range_sum(2, 2) == 4 and t.range_sum(0, 4) == 14


def test_floats():
    t = ImplicitTreap()
    for v in (1.5, 2.5, 3.0):
        t.insert(t.size, v)
    assert abs(t.range_sum(0, 2) - 7.0) < 1e-9


def test_deterministic_same_seed():
    def build(seed):
        x = ImplicitTreap(seed=seed); r = random.Random(7)
        for _ in range(200):
            x.insert(r.randint(0, x.size), r.randint(0, 1000))
        return x.to_list()
    assert build(42) == build(42)


def test_size_len():
    t = ImplicitTreap()
    for v in (1, 2, 3):
        t.insert(t.size, v)
    assert t.size == 3 and len(t) == 3


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_seed_non_int_raises():
    with pytest.raises(ImplicitTreapError):
        ImplicitTreap("x")


def test_insert_out_of_range_raises():
    with pytest.raises(ImplicitTreapError):
        ImplicitTreap().insert(1, 5)             # index 1 > size 0


def test_insert_non_num_raises():
    with pytest.raises(ImplicitTreapError):
        ImplicitTreap().insert(0, "x")


def test_delete_empty_raises():
    with pytest.raises(ImplicitTreapError):
        ImplicitTreap().delete(0)


def test_get_empty_raises():
    with pytest.raises(ImplicitTreapError):
        ImplicitTreap().get(0)


def test_get_out_of_range_raises():
    t = ImplicitTreap(); t.insert(0, 1)
    with pytest.raises(ImplicitTreapError):
        t.get(5)


def test_set_out_of_range_raises():
    t = ImplicitTreap(); t.insert(0, 1)
    with pytest.raises(ImplicitTreapError):
        t.set(5, 9)


def test_range_sum_inverted_raises():
    t = ImplicitTreap()
    for v in (1, 2, 3):
        t.insert(t.size, v)
    with pytest.raises(ImplicitTreapError):
        t.range_sum(2, 1)


def test_index_non_int_raises():
    with pytest.raises(ImplicitTreapError):
        ImplicitTreap().insert(0.5, 1)


def test_error_stores_detail():
    err = ImplicitTreapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── empty / reset / stats ─────────────────────────────────────────────────────────────────

def test_empty():
    e = ImplicitTreap()
    assert e.is_empty() and e.size == 0 and e.to_list() == []


def test_reset_clears():
    t = ImplicitTreap()
    for v in (1, 2, 3):
        t.insert(t.size, v)
    t.reset()
    assert t.is_empty() and t.to_list() == []


def test_stats_keys():
    assert set(ImplicitTreap().stats()) == {"size", "total"}


def test_stats_total():
    t = ImplicitTreap()
    for v in (5, 10, 15):
        t.insert(t.size, v)
    assert t.stats() == {"size": 3, "total": 30}


def test_two_elements():
    t = ImplicitTreap()
    t.insert(0, 7); t.insert(1, 9)
    assert t.to_list() == [7, 9] and t.range_sum(0, 1) == 16 and t.get(1) == 9


def test_insert_all_at_front():
    t = ImplicitTreap()
    for v in (1, 2, 3, 4):
        t.insert(0, v)                           # front inserts → reversed
    assert t.to_list() == [4, 3, 2, 1]


def test_range_sum_after_delete():
    t = ImplicitTreap()
    for v in (10, 20, 30, 40, 50):
        t.insert(t.size, v)
    t.delete(2)                                  # remove 30 → [10,20,40,50]
    assert t.to_list() == [10, 20, 40, 50] and t.range_sum(0, 3) == 120


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = ImplicitTreap()
    errors = []
    all_vals = list(range(400))

    def worker(chunk):
        try:
            for v in chunk:
                t.insert(0, v)                       # always front; lock serializes
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(all_vals[i::4],)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and t.size == 400 and sorted(t.to_list()) == all_vals
