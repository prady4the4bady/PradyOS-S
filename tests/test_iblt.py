"""Phase 121 — unit tests for InvertibleBloomLookupTable (pradyos/core/iblt.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.iblt import InvertibleBloomLookupTable as IBLT, IBLTError


# ── get (best-effort) / insert / delete ───────────────────────────────────────────

def test_get_never_wrong_and_high_recall():
    t = IBLT(num_cells=2000, num_hashes=4, seed=0)
    pairs = {f"key-{i}": i * 7 + 1 for i in range(300)}
    for k, v in pairs.items():
        t.insert(k, v)
    assert all(t.get(k) in (v, None) for k, v in pairs.items())     # precision
    recall = sum(1 for k, v in pairs.items() if t.get(k) == v) / 300
    assert recall >= 0.95                                            # best-effort recall


def test_get_low_load_exact():
    t = IBLT(num_cells=4000, num_hashes=4, seed=0)
    for i in range(50):
        t.insert(f"k{i}", i)
    assert all(t.get(f"k{i}") == i for i in range(50))               # tiny load ⇒ all decode


def test_contains():
    t = IBLT(num_cells=4000, num_hashes=4, seed=0)
    t.insert("a", 1)
    assert "a" in t and t.contains("a") and "zzz" not in t


def test_non_member_absent():
    t = IBLT(num_cells=1000, seed=0)
    t.insert("a", 1)
    assert t.get("ghost") is None


def test_size_tracks_inserts_and_deletes():
    t = IBLT(num_cells=2000, seed=0)
    for i in range(100):
        t.insert(f"k{i}", i)
    for i in range(30):
        t.delete(f"k{i}", i)
    assert len(t) == 70


def test_delete_makes_absent():
    t = IBLT(num_cells=4000, num_hashes=4, seed=0)
    t.insert("a", 99)
    t.delete("a", 99)
    assert t.get("a") is None


# ── list_entries (full decode) ─────────────────────────────────────────────────────

def test_list_entries_decodes_all():
    t = IBLT(num_cells=2000, num_hashes=4, seed=1)
    pairs = {f"k{i}": f"v{i}" for i in range(300)}
    for k, v in pairs.items():
        t.insert(k, v)
    assert dict(t.list_entries()) == pairs


def test_list_entries_empty():
    assert IBLT(num_cells=200, seed=0).list_entries() == []


def test_list_after_deletes():
    t = IBLT(num_cells=2000, num_hashes=4, seed=2)
    for i in range(150):
        t.insert(f"k{i}", i * 2)
    for i in range(50):
        t.delete(f"k{i}", i * 2)
    assert dict(t.list_entries()) == {f"k{i}": i * 2 for i in range(50, 150)}


def test_overloaded_list_raises():
    t = IBLT(num_cells=400, num_hashes=4, seed=0)
    for i in range(2000):
        t.insert(f"x{i}", i)
    assert not t.is_listable()
    with pytest.raises(IBLTError):
        t.list_entries()


def test_is_listable_below_load():
    t = IBLT(num_cells=2000, num_hashes=4, seed=0)
    for i in range(200):
        t.insert(f"k{i}", i)
    assert t.is_listable() is True


# ── set reconciliation ───────────────────────────────────────────────────────────

def test_set_reconciliation():
    a = IBLT(num_cells=2000, num_hashes=4, seed=0)
    b = IBLT(num_cells=2000, num_hashes=4, seed=0)
    for i in range(400):
        a.insert(f"k{i}", i)
    for i in range(200, 600):
        b.insert(f"k{i}", i)
    a_only, b_only = a.subtract(b).decode_difference()
    assert sorted(int(k[1:]) for k, _ in a_only) == list(range(0, 200))
    assert sorted(int(k[1:]) for k, _ in b_only) == list(range(400, 600))


def test_reconciliation_identical_sets_empty_diff():
    a = IBLT(num_cells=2000, num_hashes=4, seed=0)
    b = IBLT(num_cells=2000, num_hashes=4, seed=0)
    for i in range(300):
        a.insert(f"k{i}", i)
        b.insert(f"k{i}", i)
    a_only, b_only = a.subtract(b).decode_difference()
    assert a_only == [] and b_only == []


def test_subtract_incompatible_raises():
    with pytest.raises(IBLTError):
        IBLT(num_cells=2000, seed=0).subtract(IBLT(num_cells=1000, seed=0))


def test_subtract_non_iblt_raises():
    with pytest.raises(IBLTError):
        IBLT(num_cells=1000, seed=0).subtract("not an iblt")


def test_decode_difference_too_large_raises():
    a = IBLT(num_cells=200, num_hashes=4, seed=0)
    b = IBLT(num_cells=200, num_hashes=4, seed=0)
    for i in range(2000):
        a.insert(f"k{i}", i)            # huge difference vs empty b
    with pytest.raises(IBLTError):
        a.subtract(b).decode_difference()


# ── value / key types ──────────────────────────────────────────────────────────────

def test_arbitrary_key_value_types():
    t = IBLT(num_cells=2000, num_hashes=4, seed=0)
    pairs = {("tuple", 1): [1, 2, 3], 42: "str", "k": {"nested": 1}}
    for k, v in pairs.items():
        t.insert(k, v)
    assert dict(t.list_entries()) == pairs


def test_int_keys_and_values():
    t = IBLT(num_cells=2000, num_hashes=4, seed=0)
    for i in range(100):
        t.insert(i, i * i)
    assert dict(t.list_entries()) == {i: i * i for i in range(100)}


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism():
    x = IBLT(num_cells=1000, num_hashes=4, seed=5)
    y = IBLT(num_cells=1000, num_hashes=4, seed=5)
    for i in range(200):
        x.insert(f"k{i}", i)
        y.insert(f"k{i}", i)
    assert x._count == y._count and x._key_sum == y._key_sum
    assert x._val_sum == y._val_sum and x._khash_sum == y._khash_sum


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_num_cells_raises():
    with pytest.raises(IBLTError):
        IBLT(num_cells=0)


def test_invalid_num_hashes_raises():
    with pytest.raises(IBLTError):
        IBLT(num_cells=100, num_hashes=0)


def test_invalid_seed_raises():
    with pytest.raises(IBLTError):
        IBLT(num_cells=100, seed="nope")


def test_bool_num_cells_rejected():
    with pytest.raises(IBLTError):
        IBLT(num_cells=True)


def test_error_stores_detail():
    err = IBLTError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    t = IBLT(num_cells=1000, num_hashes=5, seed=7)
    assert t.num_cells == 1000 and t.num_hashes == 5 and t.seed == 7


def test_num_cells_is_multiple_of_hashes():
    t = IBLT(num_cells=1003, num_hashes=4, seed=0)
    assert t.num_cells == (1003 // 4) * 4        # partitioned, rounded down


def test_stats_keys():
    assert set(IBLT(num_cells=1000, seed=0).stats()) == {
        "size", "num_cells", "num_hashes", "listable", "seed"}


def test_stats_values():
    t = IBLT(num_cells=2000, num_hashes=4, seed=3)
    for i in range(50):
        t.insert(f"k{i}", i)
    s = t.stats()
    assert s["size"] == 50 and s["num_hashes"] == 4 and s["listable"] is True and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    t = IBLT(num_cells=2000, seed=0)
    for i in range(100):
        t.insert(f"k{i}", i)
    t.reset()
    assert len(t) == 0 and t.list_entries() == []


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    t = IBLT(num_cells=8000, num_hashes=4, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(50):
                t.insert(f"t{base}-{i}", base * 1000 + i)
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == []
    assert len(t) == 500
    assert len(t.list_entries()) == 500        # 500 entries, m=8000 ⇒ decodes
