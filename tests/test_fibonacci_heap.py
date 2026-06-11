"""Phase 154 — unit tests for FibonacciHeap (pradyos/core/fibonacci_heap.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.fibonacci_heap import FibonacciHeap, FibonacciHeapError


# ── differential vs sorted / brute dict (centerpieces) ───────────────────────────────────

def test_full_drain_sorted():
    rng = random.Random(1)
    for _ in range(60):
        vals = [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 80))]
        h = FibonacciHeap()
        for v in vals:
            h.insert(v)
        assert [h.extract_min() for _ in range(len(vals))] == sorted(vals)
        assert h.is_empty()


def test_differential_find_min():
    rng = random.Random(2)
    for _ in range(50):
        h = FibonacciHeap(); live = {}
        for _ in range(200):
            r = rng.random()
            if r < 0.45 or not live:
                v = rng.randint(-500, 500); hd = h.insert(v); live[hd] = v
            elif r < 0.7:
                hmin = h.find_min_handle(); h.extract_min(); del live[hmin]
            else:
                hd = rng.choice(list(live)); nv = live[hd] - rng.randint(0, 50)
                h.decrease_key(hd, nv); live[hd] = nv
            if live:
                assert h.find_min() == min(live.values())


def test_decrease_then_drain_sorted():
    rng = random.Random(3)
    h = FibonacciHeap(); hs = []
    vals = [rng.randint(0, 1000) for _ in range(60)]
    for v in vals:
        hs.append(h.insert(v))
    ref = vals[:]
    for _ in range(30):
        i = rng.randrange(60); nv = ref[i] - rng.randint(0, 300)
        h.decrease_key(hs[i], nv); ref[i] = nv
    assert [h.extract_min() for _ in range(60)] == sorted(ref)


def test_cascading_cut_stress():
    rng = random.Random(4)
    h = FibonacciHeap(); hs = [h.insert(i) for i in range(100)]
    h.extract_min()                                    # consolidate → deep trees
    ref = {hs[i]: i for i in range(100) if i != 0}
    for _ in range(80):
        hd = rng.choice(list(ref)); nv = ref[hd] - rng.randint(1, 200)
        h.decrease_key(hd, nv); ref[hd] = nv
        assert h.find_min() == min(ref.values())
    drain = []
    while not h.is_empty():
        drain.append(h.extract_min())
    assert drain == sorted(ref.values())


def test_large_drain():
    rng = random.Random(5)
    h = FibonacciHeap()
    big = [rng.randint(-10000, 10000) for _ in range(5000)]
    for v in big:
        h.insert(v)
    assert [h.extract_min() for _ in range(5000)] == sorted(big)


def test_insert_order_independent():
    base = [3, 1, 4, 1, 5, 9, 2, 6, 5]
    rng = random.Random(6)
    drains = set()
    for _ in range(10):
        perm = base[:]; rng.shuffle(perm)
        h = FibonacciHeap()
        for v in perm:
            h.insert(v)
        drains.add(tuple(h.extract_min() for _ in range(len(perm))))
    assert len(drains) == 1 and drains.pop() == tuple(sorted(base))


# ── decrease_key semantics ───────────────────────────────────────────────────────────────

def test_decrease_to_new_min():
    h = FibonacciHeap()
    a = [h.insert(v) for v in (10, 20, 30, 40, 50)]
    h.decrease_key(a[4], -99)
    assert h.find_min() == -99 and h.extract_min() == -99 and h.find_min() == 10


def test_decrease_root():
    h = FibonacciHeap(); a = h.insert(5); h.insert(8)
    h.decrease_key(a, 1)
    assert h.find_min() == 1


def test_decrease_key_basic():
    h = FibonacciHeap()
    a = h.insert(100); h.insert(50)
    h.decrease_key(a, 1)
    assert h.extract_min() == 1 and h.extract_min() == 50


# ── basics ───────────────────────────────────────────────────────────────────────────────

def test_single():
    h = FibonacciHeap(); h.insert(42)
    assert h.find_min() == 42 and h.size == 1 and h.extract_min() == 42 and h.is_empty()


def test_duplicates():
    h = FibonacciHeap()
    for v in [5, 5, 1, 1, 9, 5]:
        h.insert(v)
    assert [h.extract_min() for _ in range(6)] == [1, 1, 5, 5, 5, 9]


def test_floats_and_negatives():
    h = FibonacciHeap()
    for v in [1.5, 0.5, 2.5, -3.0]:
        h.insert(v)
    assert h.extract_min() == -3.0 and h.extract_min() == 0.5


def test_insert_returns_distinct_handles():
    h = FibonacciHeap()
    handles = [h.insert(v) for v in (1, 2, 3)]
    assert len(set(handles)) == 3


def test_find_min_basic():
    h = FibonacciHeap()
    for v in (8, 3, 9, 1, 7):
        h.insert(v)
    assert h.find_min() == 1


def test_extract_min_returns_value():
    h = FibonacciHeap(); h.insert(3); h.insert(1)
    assert h.extract_min() == 1


def test_find_min_handle():
    h = FibonacciHeap(); h.insert(5); b = h.insert(2)
    assert h.find_min_handle() == b


def test_extract_then_insert():
    h = FibonacciHeap()
    for v in (5, 3, 8):
        h.insert(v)
    assert h.extract_min() == 3
    h.insert(1)
    assert h.find_min() == 1 and h.size == 3


def test_size_tracks():
    h = FibonacciHeap()
    h.insert(1); h.insert(2); h.insert(3)
    assert h.size == 3
    h.extract_min()
    assert h.size == 2


def test_is_empty():
    h = FibonacciHeap()
    assert h.is_empty()
    h.insert(1)
    assert not h.is_empty()


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_empty_find_min_raises():
    with pytest.raises(FibonacciHeapError):
        FibonacciHeap().find_min()


def test_empty_extract_raises():
    with pytest.raises(FibonacciHeapError):
        FibonacciHeap().extract_min()


def test_insert_non_num_raises():
    with pytest.raises(FibonacciHeapError):
        FibonacciHeap().insert("x")


def test_decrease_bad_handle_raises():
    with pytest.raises(FibonacciHeapError):
        FibonacciHeap().decrease_key(0, 1)


def test_decrease_increase_raises():
    h = FibonacciHeap(); a = h.insert(5)
    with pytest.raises(FibonacciHeapError):
        h.decrease_key(a, 9)


def test_decrease_non_int_handle_raises():
    with pytest.raises(FibonacciHeapError):
        FibonacciHeap().decrease_key(0.5, 1)


def test_decrease_non_num_value_raises():
    h = FibonacciHeap(); a = h.insert(5)
    with pytest.raises(FibonacciHeapError):
        h.decrease_key(a, "x")


def test_dead_handle_raises():
    h = FibonacciHeap(); a = h.insert(1); h.extract_min()
    with pytest.raises(FibonacciHeapError):
        h.decrease_key(a, 0)


def test_bool_rejected():
    with pytest.raises(FibonacciHeapError):
        FibonacciHeap().insert(True)


def test_error_stores_detail():
    err = FibonacciHeapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    h = FibonacciHeap()
    for v in (3, 1, 2):
        h.insert(v)
    h.reset()
    assert h.is_empty() and h.size == 0


def test_size_property():
    h = FibonacciHeap()
    h.insert(1); h.insert(2)
    assert h.size == 2 and len(h) == 2


def test_stats_keys():
    assert set(FibonacciHeap().stats()) == {"size", "num_trees", "min"}


def test_stats_values():
    h = FibonacciHeap()
    h.insert(5); h.insert(2)
    s = h.stats()
    assert s["size"] == 2 and s["min"] == 2 and s["num_trees"] >= 1


def test_deterministic():
    def build():
        x = FibonacciHeap()
        for v in (3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5):
            x.insert(v)
        return [x.extract_min() for _ in range(11)]
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    h = FibonacciHeap()
    errors = []
    all_vals = list(range(400))

    def worker(chunk):
        try:
            for v in chunk:
                h.insert(v)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(all_vals[i::4],)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and h.size == 400
    assert [h.extract_min() for _ in range(400)] == sorted(all_vals)
