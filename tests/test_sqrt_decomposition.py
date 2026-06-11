"""Phase 147 — unit tests for SqrtDecomposition (pradyos/core/sqrt_decomposition.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.sqrt_decomposition import SqrtDecomposition, SqrtDecompositionError


# ── differential vs brute array (centerpieces) ───────────────────────────────────────────

def test_range_sum_and_point_differential():
    rng = random.Random(1)
    for n in (1, 2, 5, 9, 16, 17, 50, 100, 200):
        ref = [rng.randint(-50, 50) for _ in range(n)]
        sd = SqrtDecomposition(ref[:])
        for _ in range(n * 3):
            op = rng.random()
            l = rng.randrange(n); r = rng.randint(l, n - 1)
            if op < 0.4:
                d = rng.randint(-30, 30)
                for k in range(l, r + 1):
                    ref[k] += d
                sd.range_add(l, r, d)
            elif op < 0.7:
                assert sd.range_sum(l, r) == sum(ref[l:r + 1])
            elif op < 0.85:
                i = rng.randrange(n)
                assert sd.point_query(i) == ref[i]
            else:
                i = rng.randrange(n); v = rng.randint(-50, 50)
                ref[i] = v
                sd.update(i, v)
        assert sd.range_sum(0, n - 1) == sum(ref)
        assert all(sd.point_query(i) == ref[i] for i in range(n))


def test_large_differential():
    rng = random.Random(2)
    big = list(range(1000))
    sd = SqrtDecomposition(big[:])
    for _ in range(500):
        l = rng.randrange(1000); r = rng.randint(l, 999); d = rng.randint(-10, 10)
        for k in range(l, r + 1):
            big[k] += d
        sd.range_add(l, r, d)
    for _ in range(100):
        l = rng.randrange(1000); r = rng.randint(l, 999)
        assert sd.range_sum(l, r) == sum(big[l:r + 1])


# ── block-boundary behaviour ─────────────────────────────────────────────────────────────

def test_exact_block_range_add():
    sd = SqrtDecomposition([0] * 16)            # block size 4
    sd.range_add(0, 3, 5)
    sd.range_add(4, 15, 2)
    assert sd.range_sum(0, 3) == 20 and sd.range_sum(4, 15) == 24


def test_spanning_range():
    sd = SqrtDecomposition([0] * 16)
    sd.range_add(0, 3, 5); sd.range_add(4, 15, 2); sd.range_add(2, 9, 1)
    ref = [5, 5, 6, 6, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2]
    assert all(sd.point_query(i) == ref[i] for i in range(16)) and sd.total() == sum(ref)


def test_within_one_block():
    sd = SqrtDecomposition(list(range(20)))
    assert sd.range_sum(1, 3) == 1 + 2 + 3


def test_whole_array():
    sd = SqrtDecomposition(list(range(20)))
    assert sd.range_sum(0, 19) == sum(range(20))


def test_range_sum_single_index():
    sd = SqrtDecomposition([4, 8, 15, 16, 23])
    assert sd.range_sum(2, 2) == 15


def test_multiple_overlapping_adds():
    sd = SqrtDecomposition([0] * 10)
    sd.range_add(0, 5, 1); sd.range_add(3, 8, 2); sd.range_add(0, 9, 3)
    ref = [4, 4, 4, 6, 6, 6, 5, 5, 5, 3]
    assert all(sd.point_query(i) == ref[i] for i in range(10))


# ── specific ─────────────────────────────────────────────────────────────────────────────

def test_single_element():
    sd = SqrtDecomposition([7])
    sd.range_add(0, 0, 3)
    assert sd.range_sum(0, 0) == 10 and sd.point_query(0) == 10 and sd.total() == 10


def test_negative_delta():
    sd = SqrtDecomposition([10] * 10)
    sd.range_add(0, 9, -5)
    assert sd.range_sum(0, 9) == 50 and sd.point_query(5) == 5


def test_update_with_active_tag():
    sd = SqrtDecomposition([0] * 8)
    sd.range_add(0, 7, 10)
    sd.update(3, 100)
    assert sd.point_query(3) == 100 and sd.point_query(4) == 10
    assert sd.range_sum(0, 7) == 100 + 10 * 7


def test_update_absolute():
    sd = SqrtDecomposition([1, 2, 3, 4])
    sd.update(2, 99)
    assert sd.point_query(2) == 99 and sd.range_sum(0, 3) == 1 + 2 + 99 + 4


def test_total():
    sd = SqrtDecomposition([1, 2, 3, 4, 5])
    sd.range_add(1, 3, 10)
    assert sd.total() == 15 + 30


def test_float_values():
    sd = SqrtDecomposition([1.5, 2.5, 3.0])      # base sum 7.0
    sd.range_add(0, 2, 0.5)                       # + 0.5 * 3 = 1.5
    assert sd.total() == 8.5


def test_block_size_is_sqrt():
    sd = SqrtDecomposition(list(range(100)))
    assert sd.block_size == int(math.isqrt(100))


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_non_numeric_value_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, "x"])


def test_range_add_lo_gt_hi_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, 2, 3]).range_add(2, 1, 5)


def test_range_sum_out_of_range_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, 2, 3]).range_sum(0, 5)


def test_range_add_non_num_delta_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, 2, 3]).range_add(0, 0, "x")


def test_point_query_out_of_range_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, 2, 3]).point_query(5)


def test_update_non_num_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, 2, 3]).update(0, "x")


def test_non_int_index_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([1, 2, 3]).point_query(0.5)


def test_empty_range_sum_raises():
    with pytest.raises(SqrtDecompositionError):
        SqrtDecomposition([]).range_sum(0, 0)


def test_error_stores_detail():
    err = SqrtDecompositionError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / build / reset / determinism ───────────────────────────────────────────────

def test_reset_clears():
    sd = SqrtDecomposition([1, 2, 3])
    sd.reset()
    assert len(sd) == 0


def test_build_replaces():
    sd = SqrtDecomposition([1, 2])
    sd.build([5, 5, 5])
    assert sd.range_sum(0, 2) == 15 and len(sd) == 3


def test_size_len():
    sd = SqrtDecomposition([1, 2, 3, 4, 5])
    assert len(sd) == 5 and sd.size == 5


def test_block_size_property():
    assert SqrtDecomposition(list(range(16))).block_size == 4


def test_num_blocks_property():
    sd = SqrtDecomposition(list(range(16)))      # bs 4 → 4 blocks
    assert sd.num_blocks == 4


def test_stats_keys():
    assert set(SqrtDecomposition([1, 2, 3]).stats()) == {"size", "block_size", "num_blocks", "total"}


def test_stats_total():
    sd = SqrtDecomposition([1, 2, 3])
    sd.range_add(0, 2, 10)
    assert sd.stats()["total"] == 36


def test_deterministic():
    def build():
        x = SqrtDecomposition([3, 1, 4, 1, 5, 9, 2, 6])
        x.range_add(2, 5, 10)
        return x
    assert build().range_sum(0, 7) == build().range_sum(0, 7)


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_range_adds():
    sd = SqrtDecomposition([0] * 100)
    errors = []

    def worker():
        try:
            for _ in range(200):
                sd.range_add(0, 99, 1)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and sd.range_sum(0, 99) == 100 * 2000
