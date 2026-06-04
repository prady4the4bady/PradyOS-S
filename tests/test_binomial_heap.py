"""Phase 160 — unit tests for BinomialHeap (pradyos/core/binomial_heap.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.binomial_heap import BinomialHeap, BinomialHeapError


def _tree_count(node):
    n = 0; stack = [node]
    while stack:
        x = stack.pop(); n += 1
        c = x.child
        while c is not None:
            stack.append(c); c = c.sibling
    return n


def _invariant_ok(h):
    ok = [True]; total = 0; degs = []
    r = h._head
    while r is not None:
        degs.append(r.degree)
        if _tree_count(r) != 2 ** r.degree:
            ok[0] = False
        stack = [r]
        while stack:
            x = stack.pop(); total += 1
            if h._handles.get(x.handle) is not x:
                ok[0] = False
            c = x.child
            while c is not None:
                if c.key < x.key or c.parent is not x:
                    ok[0] = False
                stack.append(c); c = c.sibling
        r = r.sibling
    if degs != sorted(degs) or len(degs) != len(set(degs)):
        ok[0] = False
    if total != h._size or len(h._handles) != h._size:
        ok[0] = False
    return ok[0]


# ── differential vs heapq + binomial invariant (centerpieces) ─────────────────────────────

def test_full_drain_sorted():
    rng = random.Random(1)
    for _ in range(50):
        vals = [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 100))]
        h = BinomialHeap()
        for v in vals:
            h.insert(v)
            assert _invariant_ok(h)
        assert [h.extract_min() for _ in range(len(vals))] == sorted(vals)
        assert h.is_empty()


def test_differential_find_min():
    rng = random.Random(2)
    for _ in range(50):
        h = BinomialHeap(); live = {}
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
            assert _invariant_ok(h)


def test_decrease_then_drain_sorted():
    rng = random.Random(3)
    h = BinomialHeap(); hs = []
    vals = [rng.randint(0, 1000) for _ in range(60)]
    for v in vals:
        hs.append(h.insert(v))
    ref = vals[:]
    for _ in range(30):
        i = rng.randrange(60); nv = ref[i] - rng.randint(0, 300)
        h.decrease_key(hs[i], nv); ref[i] = nv
    assert [h.extract_min() for _ in range(60)] == sorted(ref)


def test_large_drain():
    rng = random.Random(4)
    h = BinomialHeap()
    big = [rng.randint(-10000, 10000) for _ in range(5000)]
    for v in big:
        h.insert(v)
    assert [h.extract_min() for _ in range(5000)] == sorted(big)


def test_order_independent():
    base = [3, 1, 4, 1, 5, 9, 2, 6, 5]
    rng = random.Random(5)
    drains = set()
    for _ in range(10):
        perm = base[:]; rng.shuffle(perm)
        h = BinomialHeap()
        for v in perm:
            h.insert(v)
        drains.add(tuple(h.extract_min() for _ in range(len(perm))))
    assert len(drains) == 1 and drains.pop() == tuple(sorted(base))


# ── decrease_key / merge semantics ────────────────────────────────────────────────────────

def test_decrease_to_new_min():
    h = BinomialHeap()
    a = [h.insert(v) for v in (10, 20, 30, 40, 50)]
    h.decrease_key(a[4], -99)
    assert h.find_min() == -99 and h.extract_min() == -99 and h.find_min() == 10


def test_merge_two_heaps():
    rng = random.Random(6)
    a = BinomialHeap(); b = BinomialHeap()
    va = [rng.randint(0, 1000) for _ in range(40)]
    vb = [rng.randint(0, 1000) for _ in range(40)]
    for v in va:
        a.insert(v)
    for v in vb:
        b.insert(v)
    a.merge(b)
    assert _invariant_ok(a) and a.size == 80 and b.is_empty()
    assert [a.extract_min() for _ in range(80)] == sorted(va + vb)


def test_merge_other_handle_still_valid():
    a = BinomialHeap(); b = BinomialHeap()
    a.insert(100)
    hb = b.insert(50)
    a.merge(b)
    a.decrease_key(hb, -5)                       # handle from b still works after merge
    assert a.find_min() == -5


def test_merge_empties_other():
    a = BinomialHeap(); b = BinomialHeap()
    for v in (1, 2):
        a.insert(v)
    for v in (3, 4):
        b.insert(v)
    a.merge(b)
    assert b.size == 0 and b.is_empty()


# ── basics ───────────────────────────────────────────────────────────────────────────────

def test_single():
    h = BinomialHeap(); h.insert(42)
    assert h.find_min() == 42 and h.size == 1 and h.extract_min() == 42 and h.is_empty()


def test_duplicates():
    h = BinomialHeap()
    for v in [5, 5, 1, 1, 9, 5]:
        h.insert(v)
    assert [h.extract_min() for _ in range(6)] == [1, 1, 5, 5, 5, 9]


def test_floats_and_negatives():
    h = BinomialHeap()
    for v in [1.5, 0.5, 2.5, -3.0]:
        h.insert(v)
    assert h.extract_min() == -3.0 and h.extract_min() == 0.5


def test_insert_returns_distinct_handles():
    h = BinomialHeap()
    handles = [h.insert(v) for v in (1, 2, 3)]
    assert len(set(handles)) == 3


def test_find_min_basic():
    h = BinomialHeap()
    for v in (8, 3, 9, 1, 7):
        h.insert(v)
    assert h.find_min() == 1


def test_extract_min_returns():
    h = BinomialHeap(); h.insert(3); h.insert(1)
    assert h.extract_min() == 1


def test_find_min_handle():
    h = BinomialHeap(); h.insert(5); b = h.insert(2)
    assert h.find_min_handle() == b


def test_extract_then_insert():
    h = BinomialHeap()
    for v in (5, 3, 8):
        h.insert(v)
    assert h.extract_min() == 3
    h.insert(1)
    assert h.find_min() == 1 and h.size == 3


def test_size_tracks():
    h = BinomialHeap()
    h.insert(1); h.insert(2); h.insert(3)
    assert h.size == 3
    h.extract_min()
    assert h.size == 2


def test_is_empty():
    h = BinomialHeap()
    assert h.is_empty()
    h.insert(1)
    assert not h.is_empty()


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_empty_find_min_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().find_min()


def test_empty_extract_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().extract_min()


def test_insert_non_num_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().insert("x")


def test_insert_bool_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().insert(True)


def test_decrease_bad_handle_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().decrease_key(999999999, 1)


def test_decrease_increase_raises():
    h = BinomialHeap(); a = h.insert(5)
    with pytest.raises(BinomialHeapError):
        h.decrease_key(a, 9)


def test_decrease_non_int_handle_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().decrease_key(0.5, 1)


def test_merge_non_heap_raises():
    with pytest.raises(BinomialHeapError):
        BinomialHeap().merge([1, 2])


def test_merge_self_raises():
    h = BinomialHeap()
    with pytest.raises(BinomialHeapError):
        h.merge(h)


def test_error_stores_detail():
    err = BinomialHeapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    h = BinomialHeap()
    for v in (3, 1, 2):
        h.insert(v)
    h.reset()
    assert h.is_empty() and h.size == 0


def test_size_len():
    h = BinomialHeap()
    h.insert(1); h.insert(2)
    assert h.size == 2 and len(h) == 2


def test_stats_keys():
    assert set(BinomialHeap().stats()) == {"size", "num_trees", "min"}


def test_stats_values():
    h = BinomialHeap()
    h.insert(5); h.insert(2)
    s = h.stats()
    assert s["size"] == 2 and s["min"] == 2 and s["num_trees"] >= 1


def test_deterministic():
    def build():
        x = BinomialHeap()
        for v in (3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5):
            x.insert(v)
        return [x.extract_min() for _ in range(11)]
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    h = BinomialHeap()
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
