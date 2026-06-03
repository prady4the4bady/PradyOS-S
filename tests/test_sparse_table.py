"""Phase 138 — unit tests for SparseTable / Bender–Farach-Colton (pradyos/core/sparse_table.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.sparse_table import SparseTable, SparseTableError


# ── differential vs brute force (centerpiece) ────────────────────────────────────────────

def test_range_min_all_ranges():
    rng = random.Random(1)
    for n in (1, 2, 3, 5, 8, 16, 17, 50, 100):
        arr = [rng.randint(-1000, 1000) for _ in range(n)]
        st = SparseTable(arr, "min")
        for l in range(n):
            for r in range(l + 1, n + 1):
                assert st.query(l, r) == min(arr[l:r])


def test_range_max_all_ranges():
    rng = random.Random(2)
    for n in (1, 2, 3, 5, 8, 16, 17, 50, 100):
        arr = [rng.randint(-1000, 1000) for _ in range(n)]
        st = SparseTable(arr, "max")
        for l in range(n):
            for r in range(l + 1, n + 1):
                assert st.query(l, r) == max(arr[l:r])


def test_big_array_queries():
    rng = random.Random(3)
    arr = [rng.randint(-10 ** 6, 10 ** 6) for _ in range(5000)]
    st = SparseTable(arr, "min")
    for _ in range(2000):
        l = rng.randint(0, 4999)
        r = rng.randint(l + 1, 5000)
        assert st.query(l, r) == min(arr[l:r])


# ── basics / edges ────────────────────────────────────────────────────────────────────────

def test_single_element():
    assert SparseTable([42]).query(0, 1) == 42


def test_full_range():
    assert SparseTable([3, 1, 4, 1, 5, 9, 2, 6]).query(0, 8) == 1


def test_adjacent_range():
    assert SparseTable([3, 1, 4]).query(1, 2) == 1


def test_get_index():
    assert SparseTable([3, 1, 4]).get(2) == 4


def test_float_values():
    assert SparseTable([1.5, 0.3, 2.7, 1.1], "max").query(0, 4) == 2.7


def test_negative_values():
    assert SparseTable([-5, -2, -9, -1], "min").query(0, 4) == -9


def test_duplicates():
    assert SparseTable([5, 5, 5, 5]).query(0, 4) == 5


def test_idempotent_overlap():
    # range length 3 covered by two overlapping length-2 blocks → must still be exact
    assert SparseTable([4, 1, 7]).query(0, 3) == 1


def test_empty_len():
    assert len(SparseTable()) == 0 and SparseTable().size == 0


# ── query / get validation ──────────────────────────────────────────────────────────────────

def test_empty_query_raises():
    with pytest.raises(SparseTableError):
        SparseTable().query(0, 1)


def test_query_lo_ge_hi_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2, 3]).query(2, 2)


def test_query_hi_over_n_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2, 3]).query(1, 5)


def test_query_negative_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2, 3]).query(-1, 2)


def test_query_non_int_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2, 3]).query(0.5, 2)


def test_get_out_of_range_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2, 3]).get(3)


def test_get_non_int_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2, 3]).get(True)


# ── build validation ──────────────────────────────────────────────────────────────────────

def test_bad_value_str_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, "x"])


def test_bad_value_bool_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, True])


def test_bad_op_raises():
    with pytest.raises(SparseTableError):
        SparseTable([1, 2], "avg")


def test_non_iterable_raises():
    with pytest.raises(SparseTableError):
        SparseTable(12345)


def test_error_stores_detail():
    err = SparseTableError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / introspection ───────────────────────────────────────────────────────────

def test_build_replaces():
    st = SparseTable([5, 1, 3], "min")
    st.build([10, 2, 7])
    assert st.query(0, 3) == 2 and len(st) == 3


def test_build_op_change():
    st = SparseTable([5, 1, 3], "min")
    st.build([10, 2, 7], "max")
    assert st.query(0, 3) == 10 and st.op == "max"


def test_reset_clears():
    st = SparseTable([1, 2, 3])
    st.reset()
    assert len(st) == 0


def test_reset_op_change():
    st = SparseTable([1, 2, 3], "min")
    st.reset("max")
    assert st.op == "max" and len(st) == 0


def test_op_property():
    assert SparseTable([1], "max").op == "max" and SparseTable([1]).op == "min"


def test_levels_property():
    assert SparseTable([0] * 8).levels == 4          # 2^0..2^3 ≤ 8 → 4 levels


def test_stats_keys():
    assert set(SparseTable([1, 2, 3]).stats()) == {"size", "op", "levels"}


def test_deterministic():
    arr = [random.Random(9).randint(0, 1000) for _ in range(500)]
    assert SparseTable(arr).query(10, 400) == SparseTable(arr).query(10, 400)


# ── concurrency (read-only queries on a static table) ──────────────────────────────────────────

def test_concurrent_queries():
    rng = random.Random(5)
    arr = [rng.randint(-1000, 1000) for _ in range(3000)]
    st = SparseTable(arr, "min")
    errors = []
    results = []

    def worker():
        try:
            ok = all(st.query(l, l + 100) == min(arr[l:l + 100]) for l in range(0, 2900, 100))
            results.append(ok)
        except Exception as exc:                          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
