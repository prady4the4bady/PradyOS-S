"""Phase 74 — unit tests for HyperLogLog (approximate distinct-count)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.hyperloglog import HyperLogLog


def _rel_err(estimate: int, truth: int) -> float:
    return abs(estimate - truth) / truth


# ── construction ──────────────────────────────────────────────────────────────

def test_default_precision_and_registers():
    h = HyperLogLog()
    assert h.precision == 14
    assert h.registers == 16384


def test_custom_precision_registers():
    assert HyperLogLog(10).registers == 1024
    assert HyperLogLog(4).registers == 16


def test_invalid_precision_raises():
    for bad in (3, 17, 0, -1, 20):
        with pytest.raises(ValueError):
            HyperLogLog(bad)


# ── basic counting ────────────────────────────────────────────────────────────

def test_empty_estimate_is_zero():
    assert HyperLogLog().estimate() == 0


def test_single_item_estimate_is_one():
    h = HyperLogLog()
    h.add("solo")
    assert h.estimate() == 1


def test_duplicate_add_is_idempotent():
    h = HyperLogLog()
    h.add("x")
    h.add("x")
    h.add("x")
    assert h.estimate() == 1


def test_len_equals_estimate():
    h = HyperLogLog()
    h.add_many(f"k{i}" for i in range(500))
    assert len(h) == h.estimate()


# ── accuracy ──────────────────────────────────────────────────────────────────

def test_accuracy_small():
    h = HyperLogLog()
    h.add_many(f"item-{i}" for i in range(1000))
    assert _rel_err(h.estimate(), 1000) <= 0.03


def test_accuracy_medium():
    h = HyperLogLog()
    h.add_many(f"item-{i}" for i in range(10000))
    assert _rel_err(h.estimate(), 10000) <= 0.03


def test_accuracy_large():
    h = HyperLogLog()
    h.add_many(f"item-{i}" for i in range(50000))
    assert _rel_err(h.estimate(), 50000) <= 0.03


def test_estimate_is_deterministic():
    a, b = HyperLogLog(), HyperLogLog()
    a.add_many(f"k{i}" for i in range(2000))
    b.add_many(f"k{i}" for i in range(2000))
    assert a.estimate() == b.estimate()


def test_low_precision_still_estimates():
    h = HyperLogLog(4)  # tiny: 16 registers, high variance but must not crash
    h.add_many(f"item-{i}" for i in range(1000))
    assert h.estimate() > 0


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_is_union():
    a = HyperLogLog(); a.add_many(f"k{i}" for i in range(10000))
    b = HyperLogLog(); b.add_many(f"k{i}" for i in range(5000, 15000))
    a.merge(b)  # union of [0,10000) and [5000,15000) = [0,15000)
    assert _rel_err(a.estimate(), 15000) <= 0.03


def test_merge_disjoint():
    a = HyperLogLog(); a.add_many(f"a{i}" for i in range(5000))
    b = HyperLogLog(); b.add_many(f"b{i}" for i in range(5000))
    a.merge(b)
    assert _rel_err(a.estimate(), 10000) <= 0.03


def test_merge_is_commutative():
    def fresh_a():
        h = HyperLogLog(); h.add_many(f"k{i}" for i in range(8000)); return h
    def fresh_b():
        h = HyperLogLog(); h.add_many(f"k{i}" for i in range(4000, 12000)); return h
    ab, ba = fresh_a(), fresh_b()
    ab.merge(fresh_b())
    ba.merge(fresh_a())
    assert ab.estimate() == ba.estimate()


def test_merge_identical_does_not_double():
    a = HyperLogLog(); a.add_many(f"k{i}" for i in range(5000))
    before = a.estimate()
    twin = HyperLogLog(); twin.add_many(f"k{i}" for i in range(5000))
    a.merge(twin)
    assert a.estimate() == before


def test_merge_precision_mismatch_raises():
    with pytest.raises(ValueError):
        HyperLogLog(14).merge(HyperLogLog(10))


def test_merge_non_hll_raises():
    with pytest.raises(ValueError):
        HyperLogLog().merge("not an hll")  # type: ignore[arg-type]


# ── clear / fill / stats ──────────────────────────────────────────────────────

def test_clear_resets():
    h = HyperLogLog()
    h.add_many(f"k{i}" for i in range(1000))
    h.clear()
    assert h.estimate() == 0
    assert h.fill_ratio() == 0.0


def test_fill_ratio_zero_when_empty():
    assert HyperLogLog().fill_ratio() == 0.0


def test_fill_ratio_increases():
    h = HyperLogLog()
    before = h.fill_ratio()
    h.add_many(f"k{i}" for i in range(1000))
    assert h.fill_ratio() > before


def test_stats_keys():
    stats = HyperLogLog().stats()
    for key in ("precision", "registers", "estimate", "fill_ratio"):
        assert key in stats


def test_stats_estimate_matches():
    h = HyperLogLog()
    h.add_many(f"k{i}" for i in range(3000))
    assert h.stats()["estimate"] == h.estimate()


# ── heterogeneous keys ────────────────────────────────────────────────────────

def test_non_string_items():
    h = HyperLogLog()
    h.add(42)
    h.add((1, 2, 3))
    h.add("str")
    assert h.estimate() == 3


def test_unicode_items():
    h = HyperLogLog()
    h.add_many(["naïve", "Ω", "café"])
    assert h.estimate() == 3


def test_precision_property_immutable_count():
    h = HyperLogLog(12)
    assert h.precision == 12
    assert h.registers == 4096


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_adds_are_thread_safe():
    h = HyperLogLog()
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(1000):
                h.add(f"k-{base}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert _rel_err(h.estimate(), 10000) <= 0.05  # 10 * 1000 distinct keys
