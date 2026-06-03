"""Phase 136 — unit tests for SkewHeap / Sleator–Tarjan (pradyos/core/skew_heap.py)."""
from __future__ import annotations

import heapq
import random
import threading

import pytest

from pradyos.core.skew_heap import SkewHeap, SkewHeapError


def filled(values):
    h = SkewHeap()
    for v in values:
        h.insert(v)
    return h


# ── priority-queue semantics ────────────────────────────────────────────────────────────

def test_insert_extract_sorted():
    vals = [random.Random(1).randint(-500, 500) for _ in range(2000)]
    h = filled(vals)
    assert [h.extract_min() for _ in range(len(vals))] == sorted(vals)


def test_peek_min():
    h = filled([5, 2, 8, 1, 9])
    assert h.peek_min() == 1 and len(h) == 5          # peek does not remove


def test_keys_sorted_read_only():
    h = filled([3, 1, 2])
    assert h.keys_sorted() == [1, 2, 3] and len(h) == 3


def test_size():
    assert len(filled(range(300))) == 300


def test_empty_after_drain():
    h = filled([1, 2, 3])
    for _ in range(3):
        h.extract_min()
    assert h.is_empty() and len(h) == 0


def test_find_min_alias():
    assert filled([4, 2, 6]).find_min() == 2


def test_single_element():
    h = filled([42])
    assert h.peek_min() == 42 and h.extract_min() == 42 and h.is_empty()


def test_float_values():
    h = filled([1.5, 0.3, 2.7, 1.1])
    assert [h.extract_min() for _ in range(4)] == sorted([1.5, 0.3, 2.7, 1.1])


def test_string_heap():
    h = filled(["banana", "apple", "cherry", "apple"])
    assert [h.extract_min() for _ in range(4)] == ["apple", "apple", "banana", "cherry"]


def test_duplicates():
    h = filled([5, 5, 5, 1, 1, 9])
    assert [h.extract_min() for _ in range(6)] == [1, 1, 5, 5, 5, 9]


# ── differential vs heapq (centerpiece) ─────────────────────────────────────────────────

def test_differential_vs_heapq():
    rng = random.Random(7)
    ref: list = []
    sh = SkewHeap()
    for _ in range(15000):
        if ref and rng.random() < 0.4:
            assert heapq.heappop(ref) == sh.extract_min()
        else:
            v = rng.randint(0, 10 ** 6)
            heapq.heappush(ref, v)
            sh.insert(v)
    while ref:
        assert heapq.heappop(ref) == sh.extract_min()
    assert len(sh) == 0


# ── adversarial inputs (no recursion limit — iterative meld) ─────────────────────────────

def test_adversarial_sorted_insert():
    h = SkewHeap()
    for v in range(20000):                            # ascending — worst case for naive recursion
        h.insert(v)
    assert h.peek_min() == 0 and len(h) == 20000
    assert [h.extract_min() for _ in range(5)] == [0, 1, 2, 3, 4]


def test_adversarial_descending_insert():
    h = SkewHeap()
    for v in range(20000, 0, -1):
        h.insert(v)
    assert h.peek_min() == 1 and len(h) == 20000


# ── meld ───────────────────────────────────────────────────────────────────────────────

def test_meld_union():
    rng = random.Random(3)
    va = [rng.randint(0, 500) for _ in range(800)]
    vb = [rng.randint(0, 500) for _ in range(600)]
    a, b = filled(va), filled(vb)
    a.meld(b)
    assert len(a) == 1400
    assert [a.extract_min() for _ in range(1400)] == sorted(va + vb)


def test_meld_empties_other():
    a, b = filled([1, 2, 3]), filled([4, 5, 6])
    a.meld(b)
    assert len(b) == 0 and b.is_empty()


def test_meld_into_empty():
    a, b = SkewHeap(), filled([3, 1, 2])
    a.meld(b)
    assert a.keys_sorted() == [1, 2, 3] and len(b) == 0


def test_meld_with_empty_other():
    a, b = filled([3, 1, 2]), SkewHeap()
    a.meld(b)
    assert a.keys_sorted() == [1, 2, 3]


def test_meld_self_noop():
    a = filled([1, 2, 3])
    a.meld(a)
    assert len(a) == 3


def test_meld_kind_mismatch_raises():
    a, b = filled([1, 2]), filled(["x", "y"])
    with pytest.raises(SkewHeapError):
        a.meld(b)


def test_meld_non_heap_raises():
    with pytest.raises(SkewHeapError):
        filled([1]).meld([1, 2])


# ── empty / validation ────────────────────────────────────────────────────────────────────

def test_empty_extract_raises():
    with pytest.raises(SkewHeapError):
        SkewHeap().extract_min()


def test_empty_peek_raises():
    with pytest.raises(SkewHeapError):
        SkewHeap().peek_min()


def test_bool_value_raises():
    with pytest.raises(SkewHeapError):
        SkewHeap().insert(True)


def test_non_orderable_value_raises():
    with pytest.raises(SkewHeapError):
        SkewHeap().insert([1, 2])


def test_mixed_kind_raises():
    h = filled([1, 2])
    with pytest.raises(SkewHeapError):
        h.insert("x")


def test_error_stores_detail():
    err = SkewHeapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── determinism / reset / introspection ─────────────────────────────────────────────────

def test_deterministic():
    seq = [3, 1, 4, 1, 5, 9, 2, 6]
    assert [filled(seq).extract_min() for _ in range(8)] == [filled(seq).extract_min() for _ in range(8)]


def test_reset_clears():
    h = filled([1, 2, 3])
    h.reset()
    assert len(h) == 0 and h.kind is None


def test_kind_property():
    h = SkewHeap()
    assert h.kind is None
    h.insert(1)
    assert h.kind == "num"


def test_kind_resets_when_emptied():
    h = filled([1])
    h.extract_min()
    assert h.kind is None
    h.insert("now-a-string")                          # kind is free to change once empty
    assert h.kind == "str"


def test_stats_keys():
    assert set(SkewHeap().stats()) == {"size", "min", "kind"}


def test_stats_min():
    assert filled([5, 2, 8]).stats()["min"] == 2
    assert SkewHeap().stats()["min"] is None


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    h = SkewHeap()
    errors = []

    def worker(base):
        try:
            for i in range(500):
                h.insert(base * 1000 + i)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(h) == 5000
    assert [h.extract_min() for _ in range(5000)] == sorted(b * 1000 + i for b in range(10) for i in range(500))
