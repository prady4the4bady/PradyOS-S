"""Phase 130 — unit tests for AMSSketch / tug-of-war F₂ sketch (pradyos/core/ams_sketch.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.ams_sketch import AMSSketch, AMSError


def rand_freq(n=300, lo=1, hi=20, seed=0, prefix="k"):
    rng = random.Random(seed)
    return {f"{prefix}{i}": rng.randint(lo, hi) for i in range(n)}


def build(freq, seed=0, width=64, depth=7):
    s = AMSSketch(width=width, depth=depth, seed=seed)
    for k, v in freq.items():
        s.update(k, v)
    return s


def exact_f2(freq):
    return sum(v * v for v in freq.values())


FREQ = rand_freq()
F2 = exact_f2(FREQ)


# ── F₂ accuracy (multi-seed means) ────────────────────────────────────────────────────

def test_mean_f2_unbiased():
    ratios = [build(FREQ, sd).f2() / F2 for sd in range(30)]
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.08      # measured ~1.016


def test_single_run_f2_loose_bound():
    assert abs(build(FREQ, 0).f2() / F2 - 1.0) < 0.30


def test_larger_width_tightens_error():
    def typ(width, seeds):
        return sum(abs(build(FREQ, sd, width=width).f2() / F2 - 1.0)
                   for sd in range(seeds)) / seeds
    assert typ(256, 15) < typ(64, 15)


def test_l2_norm_is_sqrt_f2():
    s = build(FREQ, 1)
    assert math.isclose(s.l2_norm(), s.f2() ** 0.5, rel_tol=1e-12)


def test_l2_norm_accurate():
    assert abs(build(FREQ, 1).l2_norm() / (F2 ** 0.5) - 1.0) < 0.20


def test_second_moment_alias():
    s = build(FREQ, 1)
    assert s.second_moment() == s.f2()


# ── inner product ──────────────────────────────────────────────────────────────────────

def test_inner_product_accurate():
    g = rand_freq(seed=99)
    ip = sum(FREQ[k] * g[k] for k in FREQ if k in g)
    ratios = [build(FREQ, sd).inner_product(build(g, sd)) / ip for sd in range(30)]
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.12


def test_inner_product_self_equals_f2():
    s = build(FREQ, 3)
    assert math.isclose(s.inner_product(s), s.f2(), rel_tol=1e-12)


def test_inner_product_disjoint_mean_near_zero():
    a = rand_freq(n=300, seed=1, prefix="a")
    b = rand_freq(n=300, seed=2, prefix="b")           # disjoint key space → exact IP = 0
    norm = (exact_f2(a) * exact_f2(b)) ** 0.5
    mean_ip = sum(build(a, sd).inner_product(build(b, sd)) for sd in range(30)) / 30
    assert abs(mean_ip) < 0.15 * norm


def test_inner_product_mismatch_raises():
    with pytest.raises(AMSError):
        AMSSketch(width=64).inner_product(AMSSketch(width=32))


def test_inner_product_non_sketch_raises():
    with pytest.raises(AMSError):
        AMSSketch().inner_product("nope")


# ── merge ───────────────────────────────────────────────────────────────────────────────

def test_merge_linearity():
    g = rand_freq(seed=99)
    combined = dict(FREQ)
    for k, v in g.items():
        combined[k] = combined.get(k, 0) + v
    f2c = exact_f2(combined)
    ratios = []
    for sd in range(20):
        a = build(FREQ, sd)
        a.merge(build(g, sd))
        ratios.append(a.f2() / f2c)
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.10


def test_merge_self_quadruples_f2():
    s = build(FREQ, 4)
    before = s.f2()
    s.merge(s)                                          # counters double → X² quadruples
    assert math.isclose(s.f2(), 4 * before, rel_tol=1e-9)


def test_merge_mismatch_raises():
    with pytest.raises(AMSError):
        AMSSketch(seed=1).merge(AMSSketch(seed=2))


def test_merge_non_sketch_raises():
    with pytest.raises(AMSError):
        AMSSketch().merge(123)


# ── turnstile / structural ──────────────────────────────────────────────────────────────

def test_empty_f2_zero():
    assert AMSSketch().f2() == 0.0


def test_empty_l2_zero():
    assert AMSSketch().l2_norm() == 0.0


def test_turnstile_cancellation():
    s = AMSSketch(seed=0)
    for k, v in FREQ.items():
        s.update(k, v)
    for k, v in FREQ.items():
        s.update(k, -v)
    assert s.f2() == 0.0


def test_single_negative_count_f2():
    s = AMSSketch(seed=0)
    s.update("x", -7)
    assert math.isclose(s.f2(), 49.0, rel_tol=1e-9)     # f=-7 → f²=49


def test_f2_non_negative():
    assert build(FREQ, 9).f2() >= 0.0


def test_default_count_accumulates():
    s = AMSSketch(seed=0)
    for _ in range(3):
        s.update("a")                                   # f("a") = 3
    assert math.isclose(s.f2(), 9.0, rel_tol=1e-9)


def test_update_many_returns_count():
    assert AMSSketch(seed=0).update_many(["a", "b", "c"]) == 3


def test_update_many_matches_individual():
    keys = [f"k{i}" for i in range(50)]
    a = AMSSketch(seed=0)
    a.update_many(keys)
    b = AMSSketch(seed=0)
    for k in keys:
        b.update(k, 1)
    assert a._counters == b._counters


# ── determinism ──────────────────────────────────────────────────────────────────────

def test_same_seed_identical_f2():
    assert build(FREQ, 5).f2() == build(FREQ, 5).f2()


def test_different_seed_diverges():
    assert build(FREQ, 1)._counters != build(FREQ, 2)._counters


# ── validation ────────────────────────────────────────────────────────────────────────

def test_invalid_width_raises():
    with pytest.raises(AMSError):
        AMSSketch(width=0)


def test_invalid_depth_raises():
    with pytest.raises(AMSError):
        AMSSketch(depth=0)


def test_too_many_counters_raises():
    with pytest.raises(AMSError):
        AMSSketch(width=4096, depth=64)                 # 262144 > 65536


def test_invalid_seed_raises():
    with pytest.raises(AMSError):
        AMSSketch(seed="zero")


def test_bool_seed_rejected():
    with pytest.raises(AMSError):
        AMSSketch(seed=True)


def test_non_int_count_raises():
    with pytest.raises(AMSError):
        AMSSketch().update("a", 1.5)


def test_error_stores_detail():
    err = AMSError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── type handling ─────────────────────────────────────────────────────────────────────

def test_str_bytes_int_keys():
    s = AMSSketch(seed=0)
    s.update("text"); s.update(b"raw"); s.update(42)
    assert s.f2() > 0.0


def test_bool_key_rejected():
    with pytest.raises(AMSError):
        AMSSketch().update(True)


def test_float_key_rejected():
    with pytest.raises(AMSError):
        AMSSketch().update(3.14)


# ── reset ──────────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = build(FREQ, 0)
    assert s.f2() > 0.0
    s.reset()
    assert s.f2() == 0.0


def test_reset_reconfigures():
    s = AMSSketch(width=64, depth=7, seed=0)
    s.reset(width=128, depth=5, seed=9)
    assert s.width == 128 and s.depth == 5 and s.seed == 9 and s.num_counters == 640


def test_reset_invalid_raises():
    s = AMSSketch(seed=0)
    with pytest.raises(AMSError):
        s.reset(width=0)


# ── introspection ─────────────────────────────────────────────────────────────────────

def test_standard_error_scales():
    assert math.isclose(AMSSketch(width=128).standard_error, (2 / 128) ** 0.5, rel_tol=1e-12)


def test_num_counters():
    assert AMSSketch(width=64, depth=7).num_counters == 448


def test_stats_keys():
    assert set(AMSSketch().stats()) == {
        "width", "depth", "f2", "l2_norm", "standard_error", "seed"}


def test_properties():
    s = AMSSketch(width=32, depth=5, seed=4)
    assert s.width == 32 and s.depth == 5 and s.seed == 4


# ── concurrency ───────────────────────────────────────────────────────────────────────

def test_concurrent_updates():
    s = AMSSketch(width=32, depth=5, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(200):
                s.update(f"k-{base}-{i}", 1)
        except Exception as exc:                         # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and s.f2() > 0.0
