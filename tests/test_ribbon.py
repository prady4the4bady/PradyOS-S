"""Phase 101 — unit tests for the Sovereign Ribbon Filter core (pradyos.core.ribbon)."""
from __future__ import annotations

import math
import threading

import pytest

from pradyos.core.ribbon import RibbonFilter, RibbonFilterError, _LOAD, _W


def _slots_for(n: int) -> int:
    return int(math.ceil(n / _LOAD)) + _W


# ── construction / basics ──────────────────────────────────────────────────────

def test_build_sets_built():
    rf = RibbonFilter()
    assert rf.built is False
    rf.build(["a", "b", "c"])
    assert rf.built is True


def test_len_reflects_distinct_count():
    rf = RibbonFilter()
    rf.build([f"k{i}" for i in range(120)])
    assert len(rf) == 120


def test_build_dedups():
    rf = RibbonFilter()
    rf.build(["a", "a", "b", "b", "b", "c"])
    assert len(rf) == 3


def test_empty_build_is_built_and_contains_nothing():
    rf = RibbonFilter()
    rf.build([])
    assert rf.built is True
    assert len(rf) == 0
    assert rf.contains("anything") is False


def test_default_bits_is_eight():
    assert RibbonFilter().bits_per_entry == 8


# ── membership (no false negatives) ─────────────────────────────────────────────

def test_no_false_negatives_small():
    rf = RibbonFilter(seed=0)
    keys = [f"member-{i}" for i in range(50)]
    rf.build(keys)
    assert all(rf.contains(k) for k in keys)


def test_no_false_negatives_large():
    rf = RibbonFilter(bits_per_entry=8, seed=0)
    keys = [f"key-{i}" for i in range(5000)]
    rf.build(keys)
    assert sum(1 for k in keys if not rf.contains(k)) == 0


def test_contains_operator_in():
    rf = RibbonFilter()
    rf.build(["x", "y", "z"])
    assert "x" in rf


def test_membership_integer_keys():
    rf = RibbonFilter(seed=3)
    rf.build(list(range(500)))
    assert all(rf.contains(i) for i in range(500))


def test_membership_mixed_key_types():
    rf = RibbonFilter()
    keys = [1, 2, "a", "b", ("t", 1), 3.5, None]
    rf.build(keys)
    assert all(rf.contains(k) for k in keys)


def test_contains_before_build_raises():
    rf = RibbonFilter()
    with pytest.raises(RibbonFilterError):
        rf.contains("x")


def test_contains_after_reset_raises():
    rf = RibbonFilter()
    rf.build(["a", "b"])
    rf.reset()
    with pytest.raises(RibbonFilterError):
        rf.contains("a")


# ── false-positive rate ─────────────────────────────────────────────────────────

def test_fpr_8bit_within_bound():
    rf = RibbonFilter(bits_per_entry=8, seed=0)
    rf.build([f"key-{i}" for i in range(5000)])
    non = [f"absent-{i}" for i in range(5000)]
    fpr = sum(1 for k in non if rf.contains(k)) / len(non)
    assert fpr < 0.02            # expected ≈ 2**-8 = 0.0039; generous, non-flaky bound


def test_fpr_16bit_essentially_zero():
    rf = RibbonFilter(bits_per_entry=16, seed=0)
    rf.build([f"key-{i}" for i in range(5000)])
    non = [f"absent-{i}" for i in range(5000)]
    assert sum(1 for k in non if rf.contains(k)) == 0


def test_fpr_decreases_with_more_bits():
    keys = [f"key-{i}" for i in range(3000)]
    non = [f"absent-{i}" for i in range(3000)]

    def fp(bits: int) -> int:
        rf = RibbonFilter(bits_per_entry=bits, seed=0)
        rf.build(keys)
        return sum(1 for k in non if rf.contains(k))

    fp4, fp8, fp16 = fp(4), fp(8), fp(16)
    assert fp4 > fp8 >= fp16


def test_false_positive_rate_formula():
    assert RibbonFilter(bits_per_entry=10).stats()["false_positive_rate"] == 2.0 ** -10


# ── rebuild / replace ───────────────────────────────────────────────────────────

def test_rebuild_replaces():
    rf = RibbonFilter(seed=0)
    rf.build([f"A{i}" for i in range(300)])
    rf.build([f"B{i}" for i in range(300)])
    assert rf.contains("B100") is True
    assert len(rf) == 300


def test_rebuild_changes_n():
    rf = RibbonFilter()
    rf.build([f"k{i}" for i in range(100)])
    rf.build([f"k{i}" for i in range(250)])
    assert len(rf) == 250


# ── determinism / seed sensitivity ──────────────────────────────────────────────

def test_determinism_same_seed():
    keys = [f"k{i}" for i in range(400)]
    a = RibbonFilter(seed=7)
    a.build(keys)
    b = RibbonFilter(seed=7)
    b.build(keys)
    assert a._slots == b._slots


def test_different_seed_differs():
    keys = [f"k{i}" for i in range(400)]
    a = RibbonFilter(seed=7)
    a.build(keys)
    b = RibbonFilter(seed=8)
    b.build(keys)
    assert a._slots != b._slots


def test_seed_property():
    assert RibbonFilter(seed=42).seed == 42


# ── construction robustness (GF(2) solve never stalls at our load) ──────────────

def test_construction_robust_across_varied_sets():
    import random
    failures = 0
    for t in range(20):
        rnd = random.Random(1000 + t)
        n = rnd.choice([1, 2, 3, 5, 10, 50, 200, 1000, 3000, 7000])
        ks = [f"s{t}-{rnd.random()}-{j}" for j in range(n)]
        try:
            rf = RibbonFilter(bits_per_entry=8, seed=0)
            rf.build(ks)
        except RibbonFilterError:
            failures += 1
            continue
        if any(not rf.contains(k) for k in ks):
            failures += 1
    assert failures == 0


def test_construction_tiny_inputs():
    for n in (1, 2, 3, 4):
        rf = RibbonFilter(seed=0)
        ks = [f"tiny-{i}" for i in range(n)]
        rf.build(ks)
        assert all(rf.contains(k) for k in ks)


# ── sizing / overhead ───────────────────────────────────────────────────────────

def test_slots_formula():
    rf = RibbonFilter()
    rf.build([f"k{i}" for i in range(200)])
    assert rf.slots == _slots_for(200)


def test_overhead_below_xor_theoretical():
    rf = RibbonFilter(seed=0)
    rf.build([f"k{i}" for i in range(10000)])
    # Ribbon's defining advantage: below the XOR filter's 1.23x theoretical bound
    # (and far below our XOR peeling build's ~3.69x).
    assert rf.slots / 10000 < 1.23


def test_slots_property_zero_when_unbuilt():
    assert RibbonFilter().slots == 0


def test_ribbon_width_exposed():
    assert RibbonFilter().ribbon_width == _W == 64


# ── validation ──────────────────────────────────────────────────────────────────

def test_bad_bits_zero_raises():
    with pytest.raises(RibbonFilterError):
        RibbonFilter(bits_per_entry=0)


def test_bad_bits_negative_raises():
    with pytest.raises(RibbonFilterError):
        RibbonFilter(bits_per_entry=-3)


def test_bad_bits_too_large_raises():
    with pytest.raises(RibbonFilterError):
        RibbonFilter(bits_per_entry=65)


def test_bad_bits_bool_raises():
    with pytest.raises(RibbonFilterError):
        RibbonFilter(bits_per_entry=True)


def test_bad_seed_raises():
    with pytest.raises(RibbonFilterError):
        RibbonFilter(seed="nope")


def test_error_detail_attribute():
    try:
        RibbonFilter(bits_per_entry=0)
    except RibbonFilterError as exc:
        assert exc.detail == 0
    else:
        pytest.fail("expected RibbonFilterError")


def test_reset_bad_bits_raises():
    rf = RibbonFilter()
    with pytest.raises(RibbonFilterError):
        rf.reset(bits_per_entry=0)


# ── stats / reset ───────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(RibbonFilter().stats()) == {
        "bits_per_entry", "built", "n", "slots",
        "ribbon_width", "load_factor", "false_positive_rate",
    }


def test_stats_unbuilt():
    s = RibbonFilter().stats()
    assert s["built"] is False and s["n"] == 0 and s["slots"] == 0 and s["load_factor"] == 0.0


def test_stats_after_build():
    rf = RibbonFilter()
    rf.build([f"k{i}" for i in range(300)])
    s = rf.stats()
    assert s["built"] is True and s["n"] == 300 and s["slots"] > 300
    assert 0.0 < s["load_factor"] <= 1.0


def test_reset_clears():
    rf = RibbonFilter()
    rf.build(["a", "b", "c"])
    rf.reset()
    assert rf.built is False and len(rf) == 0 and rf.slots == 0


def test_reset_reconfigures_bits_and_seed():
    rf = RibbonFilter(bits_per_entry=8, seed=0)
    rf.reset(bits_per_entry=16, seed=5)
    assert rf.bits_per_entry == 16 and rf.seed == 5


# ── concurrency ─────────────────────────────────────────────────────────────────

def test_concurrent_contains_no_false_negatives():
    rf = RibbonFilter(seed=0)
    keys = [f"k{i}" for i in range(1000)]
    rf.build(keys)
    errors: list[str] = []

    def worker() -> None:
        for k in keys:
            if not rf.contains(k):
                errors.append(k)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
