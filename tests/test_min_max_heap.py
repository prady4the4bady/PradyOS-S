"""Phase 144 — unit tests for MinMaxHeap / Atkinson et al. (pradyos/core/min_max_heap.py)."""
from __future__ import annotations

import random
import threading
from collections import deque

import pytest

from pradyos.core.min_max_heap import MinMaxHeap, MinMaxHeapError, _is_min_level


def filled(values):
    h = MinMaxHeap()
    for v in values:
        h.push(v)
    return h


def invariant_ok(h):
    a, n = h._a, len(h._a)
    for i in range(n):
        mn = _is_min_level(i)
        stack = [2 * i + 1, 2 * i + 2]
        while stack:
            j = stack.pop()
            if j >= n:
                continue
            if (mn and a[i] > a[j]) or (not mn and a[i] < a[j]):
                return False
            stack.append(2 * j + 1)
            stack.append(2 * j + 2)
    return True


# ── differential vs sorted (centerpieces) ────────────────────────────────────────────────

def test_extract_min_ascending():
    rng = random.Random(1)
    for _ in range(150):
        vals = [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 60))]
        h = filled(vals)
        assert [h.extract_min() for _ in range(len(vals))] == sorted(vals)


def test_extract_max_descending():
    rng = random.Random(2)
    for _ in range(150):
        vals = [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 60))]
        h = filled(vals)
        assert [h.extract_max() for _ in range(len(vals))] == sorted(vals, reverse=True)


def test_interleaved_vs_sorted_deque():
    rng = random.Random(3)
    for _ in range(100):
        vals = [rng.randint(0, 500) for _ in range(rng.randint(1, 40))]
        h = filled(vals)
        dq = deque(sorted(vals))
        while dq:
            if rng.random() < 0.5:
                assert h.extract_min() == dq.popleft()
            else:
                assert h.extract_max() == dq.pop()
        assert len(h) == 0


def test_invariant_holds_through_pushes():
    rng = random.Random(4)
    h = MinMaxHeap()
    for _ in range(500):
        h.push(rng.randint(-500, 500))
        assert invariant_ok(h)


def test_large_drain():
    rng = random.Random(5)
    vals = [rng.randint(-10 ** 6, 10 ** 6) for _ in range(2000)]
    h = filled(vals)
    assert [h.extract_min() for _ in range(2000)] == sorted(vals)


# ── peek / sizes ────────────────────────────────────────────────────────────────────────────

def test_peek_min_max():
    h = filled([5, 2, 8, 1, 9, 3])
    assert h.peek_min() == 1 and h.peek_max() == 9 and len(h) == 6


def test_peek_sizes_1_to_5():
    rng = random.Random(6)
    for sz in (1, 2, 3, 4, 5):
        vals = [rng.randint(0, 100) for _ in range(sz)]
        h = filled(vals)
        assert h.peek_min() == min(vals) and h.peek_max() == max(vals)


def test_single_element():
    h = filled([42])
    assert h.peek_min() == 42 and h.peek_max() == 42 and h.extract_min() == 42 and h.is_empty()


def test_two_elements():
    h = filled([7, 3])
    assert h.peek_min() == 3 and h.peek_max() == 7


def test_three_elements():
    h = filled([5, 1, 9])
    assert h.extract_min() == 1 and h.extract_max() == 9 and h.extract_min() == 5


def test_duplicates():
    h = filled([5, 5, 5, 1, 1, 9, 9])
    assert [h.extract_min() for _ in range(7)] == [1, 1, 5, 5, 5, 9, 9]


def test_strings():
    h = filled(["banana", "apple", "cherry"])
    assert h.peek_min() == "apple" and h.peek_max() == "cherry"


def test_float_and_negative_values():
    h = filled([1.5, -2.0, 0.3, -5.5])
    assert h.peek_min() == -5.5 and h.peek_max() == 1.5


def test_extract_min_then_max_same_heap():
    h = filled([5, 2, 8, 1, 9, 3])
    assert h.extract_min() == 1 and h.extract_max() == 9
    assert h.peek_min() == 2 and h.peek_max() == 8 and len(h) == 4


def test_invariant_holds_after_extracts():
    rng = random.Random(11)
    h = filled([rng.randint(0, 100) for _ in range(40)])
    for _ in range(15):
        (h.extract_min if rng.random() < 0.5 else h.extract_max)()
        assert invariant_ok(h)


def test_reset_then_different_kind():
    h = filled([1, 2, 3])
    h.reset()
    h.push("a")                                    # kind is free to change after reset
    assert h.kind == "str" and h.peek_min() == "a"


def test_peek_after_partial_drain():
    h = filled([10, 20, 30, 40, 50])
    h.extract_min(); h.extract_max()
    assert h.peek_min() == 20 and h.peek_max() == 40


# ── empty / validation ────────────────────────────────────────────────────────────────────

def test_empty_ops_raise():
    e = MinMaxHeap()
    for op in ("peek_min", "peek_max", "extract_min", "extract_max"):
        with pytest.raises(MinMaxHeapError):
            getattr(e, op)()


def test_bool_value_raises():
    with pytest.raises(MinMaxHeapError):
        MinMaxHeap().push(True)


def test_non_orderable_raises():
    with pytest.raises(MinMaxHeapError):
        MinMaxHeap().push([1, 2])


def test_mixed_kind_raises():
    h = filled([1, 2])
    with pytest.raises(MinMaxHeapError):
        h.push("x")


def test_push_many_non_iterable_raises():
    with pytest.raises(MinMaxHeapError):
        MinMaxHeap().push_many(123)


def test_error_stores_detail():
    err = MinMaxHeapError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── push_many / introspection / reset / determinism ──────────────────────────────────────────

def test_push_many():
    h = MinMaxHeap()
    assert h.push_many([3, 1, 2]) == 3 and h.keys_sorted() == [1, 2, 3]


def test_keys_sorted_read_only():
    h = filled([3, 1, 2])
    assert h.keys_sorted() == [1, 2, 3] and len(h) == 3


def test_deterministic():
    seq = [3, 1, 4, 1, 5, 9, 2, 6]
    assert [filled(seq).extract_min() for _ in range(8)] == [filled(seq).extract_min() for _ in range(8)]


def test_kind_resets_when_emptied():
    h = filled([1])
    h.extract_min()
    assert h.kind is None
    h.push("now-str")
    assert h.kind == "str"


def test_reset_clears():
    h = filled([1, 2, 3])
    h.reset()
    assert len(h) == 0 and h.kind is None


def test_size_len():
    h = filled([1, 2, 3, 4, 5])
    assert len(h) == 5 and h.size == 5


def test_kind_property():
    h = MinMaxHeap()
    assert h.kind is None
    h.push(1)
    assert h.kind == "num"


def test_stats_keys_and_values():
    assert set(MinMaxHeap().stats()) == {"size", "min", "max", "kind"}
    s = filled([5, 2, 8]).stats()
    assert s["min"] == 2 and s["max"] == 8
    assert MinMaxHeap().stats()["min"] is None


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_pushes():
    h = MinMaxHeap()
    errors = []

    def worker(base):
        try:
            for i in range(500):
                h.push(base * 1000 + i)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(h) == 5000
    assert h.peek_min() == 0 and h.peek_max() == 9 * 1000 + 499
    assert [h.extract_min() for _ in range(5000)] == sorted(b * 1000 + i for b in range(10) for i in range(500))
