"""Phase 132 — unit tests for CuckooHashTable / Pagh–Rodler (pradyos/core/cuckoo_hashtable.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.cuckoo_hashtable import CuckooHashTable, CuckooHashError

_MISS = object()


# ── exact map semantics ────────────────────────────────────────────────────────────────

def test_put_get_roundtrip():
    t = CuckooHashTable(seed=0)
    t.put("a", 1)
    assert t.get("a") == 1


def test_update_in_place():
    t = CuckooHashTable(seed=0)
    t.put("a", 1)
    t.put("a", 2)
    assert t.get("a") == 2 and len(t) == 1


def test_get_missing_returns_default():
    assert CuckooHashTable(seed=0).get("absent", "dflt") == "dflt"


def test_contains():
    t = CuckooHashTable(seed=0)
    t.put("a", 1)
    assert "a" in t and "b" not in t


def test_remove_present():
    t = CuckooHashTable(seed=0)
    t.put("a", 1)
    assert t.remove("a") is True and t.get("a") is None and len(t) == 0


def test_remove_absent():
    assert CuckooHashTable(seed=0).remove("nope") is False


def test_len_tracks_size():
    t = CuckooHashTable(seed=0)
    for i in range(200):
        t.put(f"k{i}", i)
    assert len(t) == 200


def test_keys_returns_all():
    t = CuckooHashTable(seed=0)
    for i in range(100):
        t.put(f"k{i}", i)
    assert set(t.keys()) == {f"k{i}" for i in range(100)}


def test_value_can_be_any_object():
    t = CuckooHashTable(seed=0)
    t.put("a", {"nested": [1, 2, 3]})
    t.put("b", None)
    assert t.get("a") == {"nested": [1, 2, 3]} and t.get("b", _MISS) is None and "b" in t


# ── growth / rehash (no loss) ────────────────────────────────────────────────────────────

def test_grows_under_load_no_loss():
    t = CuckooHashTable(capacity=8, seed=0)          # tiny → forces rehash/grow
    for i in range(5000):
        t.put(f"k{i}", i * 10)
    assert all(t.get(f"k{i}") == i * 10 for i in range(5000))
    assert len(t) == 5000 and t.num_rehashes > 0 and t.capacity > 8


def test_two_probe_lookup_invariant():
    # Every stored item must sit at one of its two homes (so get probes ≤ 2 slots).
    t = CuckooHashTable(capacity=8, seed=0)
    for i in range(1000):
        t.put(f"k{i}", i)
    for key in t.keys():
        kb = t._key_bytes(key)
        e1, e2 = t._t1[t._h1(kb)], t._t2[t._h2(kb)]
        assert (e1 is not None and e1[0] == key) or (e2 is not None and e2[0] == key)


def test_capacity_grows():
    t = CuckooHashTable(capacity=4, seed=0)
    for i in range(2000):
        t.put(f"k{i}", i)
    assert t.capacity > 4


# ── differential vs dict (ground truth for an exact map) ─────────────────────────────────

def test_differential_vs_dict():
    rng = random.Random(42)
    ref: dict = {}
    ct = CuckooHashTable(capacity=4, seed=7)
    for _ in range(8000):
        k = f"key{rng.randint(0, 800)}"
        r = rng.random()
        if r < 0.6:
            v = rng.randint(0, 10 ** 6)
            ref[k] = v
            ct.put(k, v)
        elif r < 0.8:
            ref.pop(k, None)
            ct.remove(k)
        else:
            assert ct.get(k, _MISS) == ref.get(k, _MISS)
    keys = set(ref) | set(ct.keys())
    assert all(ct.get(k, _MISS) == ref.get(k, _MISS) for k in keys)
    assert len(ct) == len(ref)


# ── key types ───────────────────────────────────────────────────────────────────────────

def test_int_key():
    t = CuckooHashTable(seed=0)
    t.put(42, "x")
    assert t.get(42) == "x"


def test_bytes_key():
    t = CuckooHashTable(seed=0)
    t.put(b"raw", "x")
    assert t.get(b"raw") == "x"


def test_int_str_bytes_keys_distinct():
    t = CuckooHashTable(seed=0)
    t.put(1, "int"); t.put("1", "str"); t.put(b"1", "bytes")
    assert t.get(1) == "int" and t.get("1") == "str" and t.get(b"1") == "bytes" and len(t) == 3


def test_bool_key_rejected():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(seed=0).put(True, 1)


def test_float_key_rejected():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(seed=0).put(3.14, 1)


def test_get_bool_key_rejected():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(seed=0).get(True)


# ── put_many ─────────────────────────────────────────────────────────────────────────────

def test_put_many_returns_count():
    t = CuckooHashTable(seed=0)
    assert t.put_many([("a", 1), ("b", 2), ("c", 3)]) == 3 and t.get("b") == 2


def test_put_many_bad_shape_raises():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(seed=0).put_many([("a",)])


# ── determinism ──────────────────────────────────────────────────────────────────────────

def _build(seed, n=1000):
    t = CuckooHashTable(capacity=8, seed=seed)
    for i in range(n):
        t.put(f"k{i}", i)
    return t


def test_deterministic_key_set():
    assert set(_build(3).keys()) == set(_build(3).keys())


def test_deterministic_get():
    a, b = _build(3), _build(3)
    assert all(a.get(f"k{i}") == b.get(f"k{i}") for i in range(1000))


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_invalid_capacity_raises():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(capacity=0)


def test_invalid_seed_raises():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(seed="zero")


def test_bool_seed_rejected():
    with pytest.raises(CuckooHashError):
        CuckooHashTable(seed=True)


def test_error_stores_detail():
    err = CuckooHashError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── reset ──────────────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    t = _build(0)
    assert len(t) == 1000
    t.reset()
    assert len(t) == 0 and t.get("k0") is None and t.num_rehashes == 0


def test_reset_reconfigures():
    t = CuckooHashTable(capacity=16, seed=0)
    t.reset(capacity=64, seed=9)
    assert t.capacity == 64 and t.seed == 9


def test_reset_invalid_raises():
    t = CuckooHashTable(seed=0)
    with pytest.raises(CuckooHashError):
        t.reset(capacity=0)


# ── introspection ─────────────────────────────────────────────────────────────────────────

def test_load_factor_in_range():
    t = CuckooHashTable(capacity=8, seed=0)
    for i in range(100):
        t.put(f"k{i}", i)
    assert 0.0 < t.load_factor <= 1.0


def test_stats_keys():
    assert set(CuckooHashTable(seed=0).stats()) == {
        "size", "capacity", "total_slots", "load_factor", "num_rehashes", "seed"}


def test_properties():
    t = CuckooHashTable(capacity=32, seed=4)
    assert t.capacity == 32 and t.seed == 4 and t.size == 0 and t.num_rehashes == 0


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_puts():
    t = CuckooHashTable(capacity=16, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(500):
                t.put(f"k-{base}-{i}", base * 1000 + i)
        except Exception as exc:                      # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and len(t) == 5000
    assert all(t.get(f"k-{b}-{i}") == b * 1000 + i for b in range(10) for i in range(0, 500, 50))
