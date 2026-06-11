"""Phase 129 — unit tests for FMSketch / Flajolet–Martin PCSA (pradyos/core/fm_sketch.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.fm_sketch import FMSketch, FMSketchError


def build(n, seed=0, m=64, nb=32, off=0):
    s = FMSketch(num_bitmaps=m, num_bits=nb, seed=seed)
    s.add_many(f"e-{i}" for i in range(off, off + n))
    return s


def mean_ratio(n, seeds, m=64):
    return sum(build(n, sd, m).estimate() / n for sd in range(seeds)) / seeds


def typical_error(n, seeds, m=64):
    return sum(abs(build(n, sd, m).estimate() / n - 1.0) for sd in range(seeds)) / seeds


# ── estimation accuracy (multi-seed means — robust, not single-run-fragile) ───────────

def test_mean_estimate_unbiased_n5000():
    assert abs(mean_ratio(5000, 30) - 1.0) < 0.08          # measured ~1.025


def test_mean_estimate_unbiased_n50000():
    assert abs(mean_ratio(50000, 8) - 1.0) < 0.08          # measured ~1.037


def test_single_run_within_loose_bound():
    est = build(10000, seed=0).estimate()
    assert abs(est / 10000 - 1.0) < 0.35                   # generous ~3.5×SE single-run bound


def test_larger_m_tightens_error():
    assert typical_error(5000, 20, m=256) < typical_error(5000, 20, m=64)


# ── structural ─────────────────────────────────────────────────────────────────────────

def test_empty_estimate_zero():
    assert FMSketch().estimate() == 0.0


def test_empty_count_zero():
    assert FMSketch().count() == 0


def test_count_rounds_to_int():
    c = build(5000, 0).count()
    assert isinstance(c, int) and c > 0


def test_len_equals_count():
    s = build(5000, 0)
    assert len(s) == s.count()


def test_add_increases_from_zero():
    s = FMSketch(seed=0)
    assert s.estimate() == 0.0
    s.add("hello")
    assert s.estimate() > 0.0


def test_monotone_more_items_higher_estimate():
    assert build(20000, 3).estimate() > build(2000, 3).estimate()


def test_idempotent_on_duplicate_adds():
    s = build(3000, 1)
    e1 = s.estimate()
    s.add_many(f"e-{i}" for i in range(3000))              # same items again
    assert s.estimate() == e1                              # bitmaps unchanged → identical


def test_add_many_returns_count():
    s = FMSketch(seed=0)
    assert s.add_many(["a", "b", "c"]) == 3


def test_small_n_overestimates_as_documented():
    # Classic FM/PCSA small-range bias — not a defect; the empty sketch is exactly 0.
    assert build(1, 0).estimate() > 1.0


# ── determinism ──────────────────────────────────────────────────────────────────────

def test_same_seed_identical_estimate():
    assert build(8000, 5).estimate() == build(8000, 5).estimate()


def test_different_seed_diverges():
    assert build(5000, 1)._bitmaps != build(5000, 2)._bitmaps


# ── merge ───────────────────────────────────────────────────────────────────────────────

def test_merge_union_disjoint():
    a = build(5000, 7, off=0)
    b = build(5000, 7, off=5000)
    a.merge(b)
    assert abs(a.estimate() / 10000 - 1.0) < 0.20


def test_merge_self_idempotent():
    a = build(5000, 7)
    before = a.estimate()
    a.merge(a)                                             # OR with itself → no change
    assert a.estimate() == before


def test_merge_subset_keeps_estimate():
    a = build(8000, 7, off=0)
    b = build(3000, 7, off=0)                              # subset of a's items
    before = a.estimate()
    a.merge(b)
    assert abs(a.estimate() - before) < 1e-9              # subset adds no new bits


def test_merge_config_mismatch_raises():
    with pytest.raises(FMSketchError):
        FMSketch(num_bitmaps=64).merge(FMSketch(num_bitmaps=128))


def test_merge_seed_mismatch_raises():
    with pytest.raises(FMSketchError):
        FMSketch(seed=1).merge(FMSketch(seed=2))


def test_merge_non_fmsketch_raises():
    with pytest.raises(FMSketchError):
        FMSketch().merge("not a sketch")


# ── validation ────────────────────────────────────────────────────────────────────────

def test_num_bitmaps_not_power_of_two_raises():
    with pytest.raises(FMSketchError):
        FMSketch(num_bitmaps=100)


def test_num_bitmaps_too_large_raises():
    with pytest.raises(FMSketchError):
        FMSketch(num_bitmaps=131072)


def test_num_bits_zero_raises():
    with pytest.raises(FMSketchError):
        FMSketch(num_bits=0)


def test_num_bits_too_large_raises():
    with pytest.raises(FMSketchError):
        FMSketch(num_bits=33)


def test_invalid_seed_raises():
    with pytest.raises(FMSketchError):
        FMSketch(seed="zero")


def test_bool_seed_rejected():
    with pytest.raises(FMSketchError):
        FMSketch(seed=True)


def test_bool_num_bitmaps_rejected():
    with pytest.raises(FMSketchError):
        FMSketch(num_bitmaps=True)


def test_error_stores_detail():
    err = FMSketchError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── type handling ─────────────────────────────────────────────────────────────────────

def test_str_bytes_int_accepted():
    s = FMSketch(seed=0)
    s.add("text"); s.add(b"raw"); s.add(42)
    assert s.estimate() > 0.0


def test_bool_item_rejected():
    with pytest.raises(FMSketchError):
        FMSketch().add(True)


def test_float_item_rejected():
    with pytest.raises(FMSketchError):
        FMSketch().add(3.14)


# ── reset ──────────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = build(5000, 0)
    assert s.estimate() > 0.0
    s.reset()
    assert s.estimate() == 0.0


def test_reset_reconfigures():
    s = FMSketch(num_bitmaps=64, num_bits=32, seed=0)
    s.reset(num_bitmaps=256, num_bits=24, seed=9)
    assert s.num_bitmaps == 256 and s.num_bits == 24 and s.seed == 9


def test_reset_invalid_raises():
    s = FMSketch(seed=0)
    with pytest.raises(FMSketchError):
        s.reset(num_bitmaps=100)


# ── introspection ─────────────────────────────────────────────────────────────────────

def test_standard_error_scales():
    assert abs(FMSketch(num_bitmaps=256).standard_error - 0.78 / 16) < 1e-9


def test_stats_keys():
    assert set(FMSketch().stats()) == {
        "num_bitmaps", "num_bits", "estimate", "standard_error", "seed"}


def test_properties():
    s = FMSketch(num_bitmaps=128, num_bits=24, seed=4)
    assert s.num_bitmaps == 128 and s.num_bits == 24 and s.seed == 4


# ── concurrency ───────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    s = FMSketch(num_bitmaps=64, num_bits=32, seed=0)
    errors = []

    def worker(base):
        try:
            s.add_many(f"e-{base}-{i}" for i in range(2000))
        except Exception as exc:                            # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert abs(s.estimate() / 20000 - 1.0) < 0.25          # 10×2000 distinct observed
