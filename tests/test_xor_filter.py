"""Phase 100 — unit tests for XorFilter (pradyos/core/xor_filter.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.xor_filter import XorFilter, XorFilterError


def keyset(n, prefix="key"):
    return [f"{prefix}-{i}" for i in range(n)]


# ── basic ────────────────────────────────────────────────────────────────────────

def test_build_sets_len():
    xf = XorFilter()
    xf.build(keyset(100))
    assert len(xf) == 100


def test_contains_before_build_raises():
    with pytest.raises(XorFilterError, match="not built"):
        XorFilter().contains("x")


def test_built_property():
    xf = XorFilter()
    assert xf.built is False
    xf.build(keyset(50))
    assert xf.built is True


def test_array_size_about_3_69n():
    xf = XorFilter()
    xf.build(keyset(1000))
    assert 3.5 * 1000 < xf.array_size < 4.0 * 1000


# ── membership (zero false negatives) ────────────────────────────────────────────

def test_all_members_contained():
    xf = XorFilter(bits_per_entry=8, seed=0)
    keys = keyset(10_000)
    xf.build(keys)
    assert all(xf.contains(k) for k in keys)


def test_members_contained_small_set():
    xf = XorFilter(seed=3)
    keys = keyset(200)
    xf.build(keys)
    assert [k for k in keys if not xf.contains(k)] == []


def test_contains_dunder():
    xf = XorFilter()
    xf.build(["alpha", "beta"])
    assert "alpha" in xf


def test_single_key():
    xf = XorFilter()
    xf.build(["solo"])
    assert xf.contains("solo")


def test_empty_build():
    xf = XorFilter()
    xf.build([])
    assert xf.built and len(xf) == 0


# ── false-positive rate ──────────────────────────────────────────────────────────

def test_false_positive_rate_8bit():
    xf = XorFilter(bits_per_entry=8, seed=0)
    xf.build(keyset(10_000))
    fp = sum(1 for i in range(10_000) if xf.contains(f"absent-{i}"))
    assert fp / 10_000 < 1 / 128          # ≈ 1/256 expected, accept within 2×


def test_false_positive_rate_16bit_zero():
    xf = XorFilter(bits_per_entry=16, seed=0)
    xf.build(keyset(10_000))
    fp = sum(1 for i in range(10_000) if xf.contains(f"absent16-{i}"))
    assert fp == 0


def test_wider_fingerprint_fewer_false_positives():
    keys = keyset(5000)
    f8 = XorFilter(bits_per_entry=8, seed=0)
    f12 = XorFilter(bits_per_entry=12, seed=0)
    f8.build(keys)
    f12.build(keys)
    fp8 = sum(1 for i in range(5000) if f8.contains(f"q-{i}"))
    fp12 = sum(1 for i in range(5000) if f12.contains(f"q-{i}"))
    assert fp12 <= fp8


# ── static / rebuild ─────────────────────────────────────────────────────────────

def test_rebuild_replaces_filter():
    a = keyset(3000, "A")
    b = keyset(3000, "B")
    xf = XorFilter(seed=0)
    xf.build(a)
    xf.build(b)
    assert all(xf.contains(k) for k in b)


def test_rebuild_old_keys_mostly_gone():
    a = keyset(3000, "A")
    b = keyset(3000, "B")
    xf = XorFilter(seed=0)
    xf.build(a)
    xf.build(b)
    a_in = sum(1 for k in a if xf.contains(k))
    assert a_in < 3000 * 0.05             # only false-positive-level survival


def test_contains_after_reset_raises():
    xf = XorFilter()
    xf.build(keyset(100))
    xf.reset()
    with pytest.raises(XorFilterError):
        xf.contains("x")


def test_build_dedups():
    xf = XorFilter()
    xf.build(["a", "a", "b", "b", "b", "c"])
    assert len(xf) == 3
    assert xf.contains("a") and xf.contains("b") and xf.contains("c")


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_seed():
    keys = keyset(5000)
    a = XorFilter(seed=7)
    b = XorFilter(seed=7)
    a.build(keys)
    b.build(keys)
    assert a._array == b._array


def test_different_seed_different_array():
    keys = keyset(2000)
    a = XorFilter(seed=1)
    b = XorFilter(seed=2)
    a.build(keys)
    b.build(keys)
    assert a._array != b._array


def test_deterministic_contains():
    keys = keyset(3000)
    a = XorFilter(seed=5)
    b = XorFilter(seed=5)
    a.build(keys)
    b.build(keys)
    probes = [f"p-{i}" for i in range(500)]
    assert all(a.contains(p) == b.contains(p) for p in probes)


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_bits_per_entry():
    assert XorFilter().bits_per_entry == 8


def test_configurable_bits():
    assert XorFilter(bits_per_entry=16).bits_per_entry == 16


def test_invalid_bits_zero_raises():
    with pytest.raises(XorFilterError):
        XorFilter(bits_per_entry=0)


def test_invalid_bits_negative_raises():
    with pytest.raises(XorFilterError):
        XorFilter(bits_per_entry=-8)


def test_invalid_bits_too_large_raises():
    with pytest.raises(XorFilterError):
        XorFilter(bits_per_entry=65)


def test_invalid_bits_bool_raises():
    with pytest.raises(XorFilterError):
        XorFilter(bits_per_entry=True)


def test_invalid_bits_float_raises():
    with pytest.raises(XorFilterError):
        XorFilter(bits_per_entry=2.5)


def test_invalid_seed_float_raises():
    with pytest.raises(XorFilterError):
        XorFilter(bits_per_entry=8, seed=1.5)


def test_error_stores_detail():
    err = XorFilterError(-3)
    assert err.detail == -3


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(XorFilter().stats()) == {
        "bits_per_entry", "built", "n", "array_size", "segment_size", "false_positive_rate",
    }


def test_stats_initial_unbuilt():
    s = XorFilter(bits_per_entry=8).stats()
    assert s["built"] is False and s["n"] == 0 and s["array_size"] == 0


def test_stats_after_build():
    xf = XorFilter()
    xf.build(keyset(500))
    s = xf.stats()
    assert s["built"] is True and s["n"] == 500 and s["array_size"] > 500


def test_stats_false_positive_rate_formula():
    assert XorFilter(bits_per_entry=10).stats()["false_positive_rate"] == 2.0 ** -10


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    xf = XorFilter()
    xf.build(keyset(1000))
    xf.reset()
    assert not xf.built and len(xf) == 0 and xf.array_size == 0


def test_reset_reconfigures_bits():
    xf = XorFilter(bits_per_entry=8)
    xf.reset(bits_per_entry=16)
    assert xf.bits_per_entry == 16


def test_reset_then_rebuild():
    xf = XorFilter(seed=0)
    xf.build(keyset(500, "old"))
    xf.reset()
    new = keyset(800, "new")
    xf.build(new)
    assert all(xf.contains(k) for k in new) and len(xf) == 800


# ── robustness & types & concurrency ─────────────────────────────────────────────

def test_peeling_robust_across_many_sets():
    # The generous per-segment sizing must peel reliably for varied inputs at one seed.
    failures = 0
    for t in range(20):
        f = XorFilter(seed=0)
        try:
            f.build([f"t{t}-k{i}" for i in range(2000)])
        except XorFilterError:            # pragma: no cover
            failures += 1
    assert failures == 0


def test_integer_keys():
    xf = XorFilter()
    xf.build(list(range(1000)))
    assert all(xf.contains(i) for i in range(1000))


def test_mixed_key_types():
    xf = XorFilter()
    keys = ["a", 1, ("t", 2), 3.5, "b"]
    xf.build(keys)
    assert all(xf.contains(k) for k in keys)


def test_concurrent_contains_10_threads():
    xf = XorFilter(seed=0)
    keys = keyset(5000)
    xf.build(keys)
    errors = []
    results = []

    def worker(lo):
        try:
            results.append(all(xf.contains(keys[i]) for i in range(lo, lo + 500)))
        except Exception as exc:          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t * 500,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and all(results)
