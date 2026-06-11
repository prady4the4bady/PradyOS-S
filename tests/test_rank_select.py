"""Phase 134 — unit tests for RankSelect / Jacobson succinct bitvector (pradyos/core/rank_select.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.rank_select import RankSelect, RankSelectError


def mixed(n, seed=0, p=0.4):
    """A genuinely mixed bitvector (ONE shared rng — not reseeded per element)."""
    rng = random.Random(seed)
    return [1 if rng.random() < p else 0 for _ in range(n)]


def naive_rank1(arr, i):
    return sum(arr[:i])


def naive_select1(arr, k):
    c = 0
    for p, b in enumerate(arr):
        c += b
        if c == k:
            return p
    return -1


def naive_select0(arr, k):
    c = 0
    for p, b in enumerate(arr):
        c += 1 - b
        if c == k:
            return p
    return -1


_SIZES = (0, 1, 63, 64, 65, 127, 128, 500, 512, 513, 2000)


# ── differential vs naive (the centerpiece) ─────────────────────────────────────────────

def test_rank_matches_naive_across_sizes():
    for n in _SIZES:
        arr = mixed(n, seed=n)
        rs = RankSelect(arr)
        for i in range(n + 1):
            assert rs.rank1(i) == naive_rank1(arr, i)
            assert rs.rank0(i) == i - naive_rank1(arr, i)


def test_select1_matches_naive():
    for n in _SIZES:
        arr = mixed(n, seed=n + 1)
        rs = RankSelect(arr)
        for k in range(1, sum(arr) + 1):
            assert rs.select1(k) == naive_select1(arr, k)


def test_select0_matches_naive():
    for n in _SIZES:
        arr = mixed(n, seed=n + 2)
        rs = RankSelect(arr)
        for k in range(1, (n - sum(arr)) + 1):
            assert rs.select0(k) == naive_select0(arr, k)


def test_get_matches_array():
    arr = mixed(2000, seed=5)
    rs = RankSelect(arr)
    assert all(rs.get(i) == arr[i] for i in range(2000))


def test_superblock_crossing_sparse():
    sparse = [1 if i % 137 == 0 else 0 for i in range(6000)]   # > 512 bits, crosses superblocks
    rs = RankSelect(sparse)
    assert all(rs.select1(k) == naive_select1(sparse, k) for k in range(1, sum(sparse) + 1))
    assert all(rs.rank1(i) == naive_rank1(sparse, i) for i in range(0, 6001, 11))


# ── identities ───────────────────────────────────────────────────────────────────────────

def test_select1_rank1_identity():
    arr = mixed(8000, seed=7, p=0.55)
    rs = RankSelect(arr)
    for k in range(1, rs.count1 + 1):
        p = rs.select1(k)
        assert arr[p] == 1 and rs.rank1(p) == k - 1 and rs.rank1(p + 1) == k


def test_select0_rank0_identity():
    arr = mixed(8000, seed=8, p=0.45)
    rs = RankSelect(arr)
    for k in range(1, rs.count0 + 1):
        p = rs.select0(k)
        assert arr[p] == 0 and rs.rank0(p) == k - 1


def test_rank1_plus_rank0_equals_i():
    arr = mixed(1000, seed=9)
    rs = RankSelect(arr)
    assert all(rs.rank1(i) + rs.rank0(i) == i for i in range(1001))


def test_rank1_full_is_count1():
    arr = mixed(1000, seed=10)
    rs = RankSelect(arr)
    assert rs.rank1(1000) == rs.count1 == sum(arr)


def test_rank1_zero():
    assert RankSelect(mixed(100, seed=1)).rank1(0) == 0


# ── edge cases ─────────────────────────────────────────────────────────────────────────────

def test_all_zeros():
    rs = RankSelect("0" * 1000)
    assert rs.count1 == 0 and rs.rank1(1000) == 0 and rs.select0(1000) == 999


def test_all_ones():
    rs = RankSelect("1" * 1000)
    assert rs.count1 == 1000 and rs.select1(1) == 0 and rs.select1(1000) == 999


def test_empty():
    rs = RankSelect()
    assert len(rs) == 0 and rs.count1 == 0 and rs.rank1(0) == 0


def test_single_bit():
    assert RankSelect("1").select1(1) == 0 and RankSelect("0").rank1(1) == 0


def test_word_boundary_sizes():
    for n in (63, 64, 65):
        arr = mixed(n, seed=n)
        rs = RankSelect(arr)
        assert rs.rank1(n) == sum(arr) and rs.get(n - 1) == arr[n - 1]


# ── input forms ────────────────────────────────────────────────────────────────────────────

def test_string_input():
    assert RankSelect("10110").count1 == 3


def test_list_input():
    assert RankSelect([1, 0, 1, 1, 0]).count1 == 3


def test_bool_input():
    assert RankSelect([True, False, True]).count1 == 2


def test_str_and_list_agree():
    assert RankSelect("10110").select1(2) == RankSelect([1, 0, 1, 1, 0]).select1(2)


# ── select / rank bounds ─────────────────────────────────────────────────────────────────────

def test_select1_zero_raises():
    with pytest.raises(RankSelectError):
        RankSelect("101").select1(0)


def test_select1_overcount_raises():
    with pytest.raises(RankSelectError):
        RankSelect("101").select1(3)            # only 2 ones


def test_select1_on_all_zeros_raises():
    with pytest.raises(RankSelectError):
        RankSelect("000").select1(1)


def test_select0_overcount_raises():
    with pytest.raises(RankSelectError):
        RankSelect("111").select0(1)            # no zeros


def test_rank1_negative_raises():
    with pytest.raises(RankSelectError):
        RankSelect("101").rank1(-1)


def test_rank1_over_n_raises():
    with pytest.raises(RankSelectError):
        RankSelect("101").rank1(4)


def test_rank1_at_n_ok():
    assert RankSelect("101").rank1(3) == 2


# ── get / validation ──────────────────────────────────────────────────────────────────────────

def test_get_out_of_range_raises():
    with pytest.raises(RankSelectError):
        RankSelect("101").get(3)


def test_get_bool_index_rejected():
    with pytest.raises(RankSelectError):
        RankSelect("101").get(True)


def test_bad_bit_char_raises():
    with pytest.raises(RankSelectError):
        RankSelect("012")


def test_bad_bit_value_raises():
    with pytest.raises(RankSelectError):
        RankSelect([0, 1, 2])


def test_non_iterable_raises():
    with pytest.raises(RankSelectError):
        RankSelect(12345)


def test_error_stores_detail():
    err = RankSelectError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / build / reset ──────────────────────────────────────────────────────────────

def test_count1_count0():
    rs = RankSelect("11010")
    assert rs.count1 == 3 and rs.count0 == 2 and len(rs) == 5


def test_stats_keys():
    assert set(RankSelect("101").stats()) == {
        "size", "count1", "count0", "num_words", "num_superblocks"}


def test_build_replaces():
    rs = RankSelect("111")
    rs.build("0000")
    assert rs.count1 == 0 and len(rs) == 4


def test_reset_clears():
    rs = RankSelect("1010101010")
    rs.reset()
    assert len(rs) == 0 and rs.count1 == 0


# ── concurrency (read-only queries on a static vector) ──────────────────────────────────────────

def test_concurrent_queries():
    arr = mixed(5000, seed=3)
    rs = RankSelect(arr)
    c1 = sum(arr)
    errors = []
    results = []

    def worker():
        try:
            ok = all(rs.rank1(i) == naive_rank1(arr, i) for i in range(0, 5001, 250))
            ok = ok and all(rs.get(i) == arr[i] for i in range(0, 5000, 250))
            results.append(ok)
        except Exception as exc:                  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10 and rs.count1 == c1
