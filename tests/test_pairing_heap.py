"""Phase 150 — unit tests for PairingHeap (pradyos/core/pairing_heap.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.pairing_heap import PairingHeap, PairingHeapError


# ── differential vs sorted / brute dict (centerpieces) ───────────────────────────────────

def test_full_drain_sorted():
    rng = random.Random(1)
    for _ in range(60):
        vals = [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 60))]
        h = PairingHeap()
        for v in vals:
            h.insert(v)
        assert [h.delete_min() for _ in range(len(vals))] == sorted(vals)
        assert h.is_empty()


def test_differential_find_min():
    rng = random.Random(2)
    for _ in range(40):
        h = PairingHeap(); live = {}
        for _ in range(120):
            r = rng.random()
            if r < 0.45 or not live:
                v = rng.randint(-500, 500); hd = h.insert(v); live[hd] = v
            elif r < 0.7:
                mn = min(live.values()); h.delete_min()
                for k, val in live.items():
                    if val == mn:
                        del live[k]; break
            else:
                hd = rng.choice(list(live)); nv = live[hd] - rng.randint(0, 50)
                h.decrease_key(hd, nv); live[hd] = nv
            if live:
                assert h.find_min() == min(live.values())


def test_decrease_then_drain_sorted():
    rng = random.Random(3)
    h = PairingHeap(); hs = []
    vals = [rng.randint(0, 1000) for _ in range(40)]
    for v in vals:
        hs.append(h.insert(v))
    ref = vals[:]
    for _ in range(20):
        idx = rng.randrange(40); nv = ref[idx] - rng.randint(0, 200)
        h.decrease_key(hs[idx], nv); ref[idx] = nv
    assert [h.delete_min() for _ in range(40)] == sorted(ref)


def test_large_drain():
    rng = random.Random(4)
    h = PairingHeap()
    big = [rng.randint(-10000, 10000) for _ in range(3000)]
    for v in big:
        h.insert(v)
    assert [h.delete_min() for _ in range(3000)] == sorted(big)


def test_insert_order_independent():
    base = [3, 1, 4, 1, 5, 9, 2, 6]
    rng = random.Random(5)
    drains = set()
    for _ in range(10):
        perm = base[:]; rng.shuffle(perm)
        h = PairingHeap()
        for v in perm:
            h.insert(v)
        drains.add(tuple(h.delete_min() for _ in range(len(perm))))
    assert len(drains) == 1 and drains.pop() == tuple(sorted(base))


# ── decrease_key semantics ───────────────────────────────────────────────────────────────

def test_decrease_key_to_new_min():
    h = PairingHeap()
    hs = [h.insert(v) for v in (10, 20, 30, 40)]
    h.decrease_key(hs[3], -5)
    assert h.find_min() == -5 and h.delete_min() == -5 and h.find_min() == 10


def test_decrease_root():
    h = PairingHeap(); a = h.insert(5); h.insert(8)
    h.decrease_key(a, 1)
    assert h.find_min() == 1


def test_decrease_same_value():
    h = PairingHeap(); a = h.insert(7); h.insert(3)
    h.decrease_key(a, 7)
    assert h.delete_min() == 3 and h.delete_min() == 7


def test_decrease_key_basic():
    h = PairingHeap()
    a = h.insert(100); h.insert(50)
    h.decrease_key(a, 1)
    assert h.delete_min() == 1 and h.delete_min() == 50


# ── basics ───────────────────────────────────────────────────────────────────────────────

def test_single_element():
    h = PairingHeap(); h.insert(42)
    assert h.find_min() == 42 and h.size == 1 and h.delete_min() == 42 and h.is_empty()


def test_duplicates():
    h = PairingHeap()
    for v in [5, 5, 5, 1, 1, 9]:
        h.insert(v)
    assert [h.delete_min() for _ in range(6)] == [1, 1, 5, 5, 5, 9]


def test_interleaved_find_min():
    h = PairingHeap(); ref = []
    for v in [50, 40, 30, 20, 10]:
        h.insert(v); ref.append(v)
        assert h.find_min() == min(ref)


def test_insert_returns_distinct_handles():
    h = PairingHeap()
    handles = [h.insert(v) for v in (1, 2, 3)]
    assert len(set(handles)) == 3


def test_find_min_basic():
    h = PairingHeap()
    for v in (8, 3, 9, 1, 7):
        h.insert(v)
    assert h.find_min() == 1


def test_delete_min_returns_value():
    h = PairingHeap(); h.insert(3); h.insert(1)
    assert h.delete_min() == 1


def test_find_min_handle():
    h = PairingHeap(); a = h.insert(5); b = h.insert(2)
    assert h.find_min_handle() == b


def test_negatives():
    h = PairingHeap()
    for v in (-3, -1, -7, -2):
        h.insert(v)
    assert h.delete_min() == -7


def test_floats():
    h = PairingHeap()
    for v in (1.5, 0.5, 2.5):
        h.insert(v)
    assert h.delete_min() == 0.5


def test_size_tracks():
    h = PairingHeap()
    h.insert(1); h.insert(2); h.insert(3)
    assert h.size == 3
    h.delete_min()
    assert h.size == 2


def test_is_empty():
    h = PairingHeap()
    assert h.is_empty()
    h.insert(1)
    assert not h.is_empty()


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_empty_find_min_raises():
    with pytest.raises(PairingHeapError):
        PairingHeap().find_min()


def test_empty_delete_min_raises():
    with pytest.raises(PairingHeapError):
        PairingHeap().delete_min()


def test_insert_non_num_raises():
    with pytest.raises(PairingHeapError):
        PairingHeap().insert("x")


def test_decrease_key_bad_handle_raises():
    with pytest.raises(PairingHeapError):
        PairingHeap().decrease_key(0, 1)


def test_decrease_key_increase_raises():
    h = PairingHeap(); a = h.insert(5)
    with pytest.raises(PairingHeapError):
        h.decrease_key(a, 9)


def test_decrease_key_non_int_handle_raises():
    with pytest.raises(PairingHeapError):
        PairingHeap().decrease_key(0.5, 1)


def test_decrease_key_non_num_value_raises():
    h = PairingHeap(); a = h.insert(5)
    with pytest.raises(PairingHeapError):
        h.decrease_key(a, "x")


def test_decrease_key_dead_handle_raises():
    h = PairingHeap(); a = h.insert(1); h.delete_min()
    with pytest.raises(PairingHeapError):
        h.decrease_key(a, 0)


def test_bool_rejected():
    with pytest.raises(PairingHeapError):
        PairingHeap().insert(True)


def test_error_stores_detail():
    err = PairingHeapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    h = PairingHeap()
    for v in (3, 1, 2):
        h.insert(v)
    h.reset()
    assert h.is_empty() and h.size == 0


def test_size_property():
    h = PairingHeap()
    h.insert(1); h.insert(2)
    assert h.size == 2 and len(h) == 2


def test_stats_keys():
    assert set(PairingHeap().stats()) == {"size", "nodes", "min"}


def test_stats_values():
    h = PairingHeap()
    h.insert(5); h.insert(2)
    s = h.stats()
    assert s["size"] == 2 and s["min"] == 2 and s["nodes"] >= 2


def test_stats_empty_min_none():
    assert PairingHeap().stats()["min"] is None


def test_deterministic():
    def build():
        x = PairingHeap()
        for v in (3, 1, 4, 1, 5, 9, 2, 6):
            x.insert(v)
        return [x.delete_min() for _ in range(8)]
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    h = PairingHeap()
    errors = []
    all_vals = list(range(200))

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
    assert errors == [] and h.size == 200
    assert [h.delete_min() for _ in range(200)] == sorted(all_vals)
