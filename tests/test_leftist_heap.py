"""Phase 158 — unit tests for LeftistHeap (pradyos/core/leftist_heap.py)."""
from __future__ import annotations

import heapq
import itertools
import math
import random
import threading

import pytest

from pradyos.core.leftist_heap import LeftistHeap, LeftistHeapError, _rank


def _invariant_ok(h):
    root = h._root
    if root is None:
        return True
    ok = [True]; stack = [root]
    while stack:
        nd = stack.pop()
        lr = _rank(nd.left); rr = _rank(nd.right)
        if lr < rr or nd.rank != rr + 1:
            ok[0] = False
        if nd.left:
            if nd.left.key < nd.key:
                ok[0] = False
            stack.append(nd.left)
        if nd.right:
            if nd.right.key < nd.key:
                ok[0] = False
            stack.append(nd.right)
    return ok[0]


# ── differential vs heapq + invariant (centerpieces) ──────────────────────────────────────

def test_full_drain_sorted():
    rng = random.Random(1)
    for _ in range(60):
        vals = [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 100))]
        h = LeftistHeap()
        for v in vals:
            h.insert(v)
            assert _invariant_ok(h)
        assert [h.extract_min() for _ in range(len(vals))] == sorted(vals)
        assert h.is_empty()


def test_interleaved_vs_heapq():
    rng = random.Random(2)
    for _ in range(40):
        h = LeftistHeap(); ref = []
        for _ in range(200):
            if rng.random() < 0.6 or not ref:
                v = rng.randint(-500, 500); h.insert(v); heapq.heappush(ref, v)
            else:
                assert h.extract_min() == heapq.heappop(ref)
            if ref:
                assert h.find_min() == ref[0]
            assert _invariant_ok(h)


def test_merge_two_heaps():
    rng = random.Random(3)
    for _ in range(40):
        a = LeftistHeap(); b = LeftistHeap()
        va = [rng.randint(0, 1000) for _ in range(rng.randint(0, 60))]
        vb = [rng.randint(0, 1000) for _ in range(rng.randint(0, 60))]
        for v in va:
            a.insert(v)
        for v in vb:
            b.insert(v)
        a.merge(b)
        assert _invariant_ok(a) and b.is_empty() and a.size == len(va) + len(vb)
        assert [a.extract_min() for _ in range(a.size)] == sorted(va + vb)


def test_rank_bound():
    rng = random.Random(4)
    h = LeftistHeap()
    for _ in range(10000):
        h.insert(rng.randint(0, 1_000_000))
    assert _rank(h._root) <= math.log2(10001) + 1


def test_large_drain():
    rng = random.Random(5)
    h = LeftistHeap()
    big = [rng.randint(-10000, 10000) for _ in range(5000)]
    for v in big:
        h.insert(v)
    assert [h.extract_min() for _ in range(5000)] == sorted(big)


def test_order_independent():
    base = [3, 1, 4, 1, 5, 9]
    res = set()
    for perm in itertools.permutations(base):
        h = LeftistHeap()
        for v in perm:
            h.insert(v)
        res.add(tuple(h.extract_min() for _ in range(len(base))))
    assert len(res) == 1 and res.pop() == tuple(sorted(base))


# ── basics ───────────────────────────────────────────────────────────────────────────────

def test_single():
    h = LeftistHeap(); h.insert(42)
    assert h.find_min() == 42 and h.size == 1 and h.extract_min() == 42 and h.is_empty()


def test_duplicates():
    h = LeftistHeap()
    for v in [5, 5, 1, 1, 9, 5]:
        h.insert(v)
    assert [h.extract_min() for _ in range(6)] == [1, 1, 5, 5, 5, 9]


def test_floats_and_negatives():
    h = LeftistHeap()
    for v in [1.5, 0.5, 2.5, -3.0]:
        h.insert(v)
    assert h.extract_min() == -3.0 and h.extract_min() == 0.5


def test_find_min_basic():
    h = LeftistHeap()
    for v in (8, 3, 9, 1, 7):
        h.insert(v)
    assert h.find_min() == 1


def test_extract_min_returns():
    h = LeftistHeap(); h.insert(3); h.insert(1)
    assert h.extract_min() == 1


def test_insert_increments_size():
    h = LeftistHeap()
    h.insert(1); h.insert(2)
    assert h.size == 2 and len(h) == 2


def test_extract_then_insert():
    h = LeftistHeap()
    for v in (5, 3, 8):
        h.insert(v)
    assert h.extract_min() == 3
    h.insert(1)
    assert h.find_min() == 1 and h.size == 3


def test_is_empty():
    h = LeftistHeap()
    assert h.is_empty()
    h.insert(1)
    assert not h.is_empty()


# ── merge edge cases ─────────────────────────────────────────────────────────────────────

def test_merge_empty_into_nonempty():
    a = LeftistHeap()
    for v in (3, 1, 2):
        a.insert(v)
    a.merge(LeftistHeap())
    assert a.size == 3 and a.find_min() == 1


def test_merge_nonempty_into_empty():
    c = LeftistHeap(); d = LeftistHeap()
    for v in (7, 8):
        d.insert(v)
    c.merge(d)
    assert c.size == 2 and c.find_min() == 7 and d.is_empty()


def test_merge_both_empty():
    a = LeftistHeap(); b = LeftistHeap()
    a.merge(b)
    assert a.is_empty() and b.is_empty()


def test_merge_empties_other():
    a = LeftistHeap(); b = LeftistHeap()
    for v in (1, 2):
        a.insert(v)
    for v in (3, 4):
        b.insert(v)
    a.merge(b)
    assert b.size == 0 and b.is_empty()


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_empty_find_min_raises():
    with pytest.raises(LeftistHeapError):
        LeftistHeap().find_min()


def test_empty_extract_raises():
    with pytest.raises(LeftistHeapError):
        LeftistHeap().extract_min()


def test_insert_non_num_raises():
    with pytest.raises(LeftistHeapError):
        LeftistHeap().insert("x")


def test_insert_bool_raises():
    with pytest.raises(LeftistHeapError):
        LeftistHeap().insert(True)


def test_merge_non_heap_raises():
    with pytest.raises(LeftistHeapError):
        LeftistHeap().merge([1, 2])


def test_merge_self_raises():
    h = LeftistHeap()
    with pytest.raises(LeftistHeapError):
        h.merge(h)


def test_error_stores_detail():
    err = LeftistHeapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    h = LeftistHeap()
    for v in (3, 1, 2):
        h.insert(v)
    h.reset()
    assert h.is_empty() and h.size == 0


def test_size_len():
    h = LeftistHeap()
    h.insert(1); h.insert(2)
    assert h.size == 2 and len(h) == 2


def test_stats_keys():
    assert set(LeftistHeap().stats()) == {"size", "rank", "min"}


def test_stats_values():
    h = LeftistHeap()
    h.insert(5); h.insert(2)
    s = h.stats()
    assert s["size"] == 2 and s["min"] == 2 and s["rank"] >= 1


def test_deterministic():
    def build():
        x = LeftistHeap()
        for v in (3, 1, 4, 1, 5, 9, 2, 6):
            x.insert(v)
        return [x.extract_min() for _ in range(8)]
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    h = LeftistHeap()
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
