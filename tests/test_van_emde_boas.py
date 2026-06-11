"""Phase 152 — unit tests for VanEmdeBoas (pradyos/core/van_emde_boas.py)."""
from __future__ import annotations

import bisect
import random
import threading

import pytest

from pradyos.core.van_emde_boas import VanEmdeBoas, VanEmdeBoasError


def _succ(srt, x):
    i = bisect.bisect_right(srt, x)
    return srt[i] if i < len(srt) else None


def _pred(srt, x):
    i = bisect.bisect_left(srt, x)
    return srt[i - 1] if i > 0 else None


# ── differential vs sorted-set ground truth (centerpieces) ───────────────────────────────

def test_differential_all_ops():
    rng = random.Random(1)
    for U in (2, 4, 8, 16, 256, 1024):
        v = VanEmdeBoas(U); s = set()
        for _ in range(U * 4):
            x = rng.randrange(U)
            if rng.random() < 0.6:
                assert v.insert(x) == (x not in s); s.add(x)
            else:
                assert v.delete(x) == (x in s); s.discard(x)
            srt = sorted(s)
            assert v.minimum() == (srt[0] if srt else None)
            assert v.maximum() == (srt[-1] if srt else None)
            for q in (0, U - 1, x, rng.randrange(U)):
                assert v.member(q) == (q in s)
                assert v.successor(q) == _succ(srt, q)
                assert v.predecessor(q) == _pred(srt, q)


def test_exhaustive_succ_pred():
    v = VanEmdeBoas(256); s = set()
    for x in (3, 17, 17, 200, 255, 0, 128, 129):
        v.insert(x); s.add(x)
    srt = sorted(s)
    for q in range(256):
        assert v.successor(q) == _succ(srt, q)
        assert v.predecessor(q) == _pred(srt, q)
        assert v.member(q) == (q in s)


def test_large_differential():
    rng = random.Random(2)
    v = VanEmdeBoas(65536); s = set()
    for _ in range(8000):
        x = rng.randrange(65536)
        if rng.random() < 0.6:
            v.insert(x); s.add(x)
        else:
            v.delete(x); s.discard(x)
    srt = sorted(s)
    for _ in range(500):
        q = rng.randrange(65536)
        assert v.member(q) == (q in s)
        assert v.successor(q) == _succ(srt, q)
        assert v.predecessor(q) == _pred(srt, q)
    assert v.size == len(s) and v.minimum() == srt[0] and v.maximum() == srt[-1]


def test_full_universe_successor_walk():
    v = VanEmdeBoas(16)
    for x in range(16):
        v.insert(x)
    seq = []; cur = v.minimum()
    while cur is not None:
        seq.append(cur); cur = v.successor(cur)
    assert seq == list(range(16))


def test_delete_min_drain():
    v = VanEmdeBoas(16)
    for x in range(16):
        v.insert(x)
    drained = []
    while not v.is_empty():
        m = v.minimum(); drained.append(m); v.delete(m)
    assert drained == list(range(16))


# ── insert / delete semantics ────────────────────────────────────────────────────────────

def test_insert_returns_added():
    v = VanEmdeBoas(64)
    assert v.insert(10) is True


def test_duplicate_insert_noop():
    v = VanEmdeBoas(64)
    v.insert(10)
    assert v.insert(10) is False and v.size == 1


def test_delete_absent_noop():
    v = VanEmdeBoas(64)
    v.insert(10)
    assert v.delete(20) is False and v.size == 1


def test_delete_present():
    v = VanEmdeBoas(64)
    v.insert(10)
    assert v.delete(10) is True and v.size == 0


# ── lifecycle / boundaries ─────────────────────────────────────────────────────────────────

def test_single_element():
    v = VanEmdeBoas(16); v.insert(7)
    assert v.minimum() == 7 and v.maximum() == 7 and v.member(7)
    assert v.successor(7) is None and v.predecessor(7) is None


def test_single_neighbors():
    v = VanEmdeBoas(16); v.insert(7)
    assert v.successor(3) == 7 and v.predecessor(10) == 7


def test_empty_after_delete():
    v = VanEmdeBoas(16); v.insert(7); v.delete(7)
    assert v.is_empty() and v.minimum() is None and v.successor(0) is None


def test_empty_min_max_none():
    v = VanEmdeBoas(16)
    assert v.minimum() is None and v.maximum() is None and v.predecessor(5) is None


def test_boundaries():
    v = VanEmdeBoas(16)
    v.insert(0); v.insert(15)
    assert v.minimum() == 0 and v.maximum() == 15
    assert v.successor(0) == 15 and v.predecessor(15) == 0
    assert v.successor(15) is None and v.predecessor(0) is None


def test_successor_basic():
    v = VanEmdeBoas(256)
    for x in (10, 50, 200):
        v.insert(x)
    assert v.successor(10) == 50 and v.successor(9) == 10 and v.successor(200) is None


def test_predecessor_basic():
    v = VanEmdeBoas(256)
    for x in (10, 50, 200):
        v.insert(x)
    assert v.predecessor(200) == 50 and v.predecessor(201) == 200 and v.predecessor(10) is None


def test_member():
    v = VanEmdeBoas(256)
    for x in (1, 100, 255):
        v.insert(x)
    assert v.member(100) and not v.member(99) and v.member(255) and v.member(1)


# ── universe rounding ──────────────────────────────────────────────────────────────────────

def test_universe_rounding():
    assert VanEmdeBoas(1000).universe == 1024


def test_universe_power_of_two_unchanged():
    assert VanEmdeBoas(256).universe == 256 and VanEmdeBoas(2).universe == 2


def test_insert_near_rounded_edge():
    v = VanEmdeBoas(1000)            # rounds to 1024
    v.insert(999)
    assert v.member(999) and v.maximum() == 999


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_universe_too_small_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(0)


def test_universe_negative_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(-5)


def test_insert_out_of_range_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(16).insert(20)


def test_insert_negative_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(16).insert(-1)


def test_insert_non_int_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(16).insert("x")


def test_member_out_of_range_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(16).member(99)


def test_successor_non_int_raises():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(16).successor(2.5)


def test_bool_rejected():
    with pytest.raises(VanEmdeBoasError):
        VanEmdeBoas(16).insert(True)


def test_error_stores_detail():
    err = VanEmdeBoasError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── introspection / reset / determinism ────────────────────────────────────────────────────

def test_reset_clears():
    v = VanEmdeBoas(256)
    for x in (5, 10, 15):
        v.insert(x)
    v.reset()
    assert v.is_empty() and v.size == 0


def test_size_len():
    v = VanEmdeBoas(64)
    v.insert(1); v.insert(2); v.insert(3)
    assert v.size == 3 and len(v) == 3


def test_universe_property():
    assert VanEmdeBoas(65536).universe == 65536


def test_stats_keys():
    assert set(VanEmdeBoas(16).stats()) == {"size", "universe", "min", "max"}


def test_stats_values():
    v = VanEmdeBoas(256)
    v.insert(5); v.insert(200)
    s = v.stats()
    assert s["size"] == 2 and s["min"] == 5 and s["max"] == 200 and s["universe"] == 256


def test_deterministic():
    def build():
        x = VanEmdeBoas(1024)
        for v in (500, 3, 999, 3, 250):
            x.insert(v)
        return (x.minimum(), x.maximum(), x.successor(100), x.predecessor(600))
    assert build() == build()


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_inserts():
    v = VanEmdeBoas(4096)
    errors = []
    vals = list(range(0, 4000, 2))

    def worker(chunk):
        try:
            for x in chunk:
                v.insert(x)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(vals[i::4],)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and v.size == len(vals)
    assert all(v.member(x) for x in vals) and v.minimum() == 0 and v.maximum() == 3998
