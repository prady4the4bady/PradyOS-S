"""Phase 106 — unit tests for the Sovereign Moment Sketch (pradyos.core.moment_sketch)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.moment_sketch import MomentSketch, MomentSketchError


def _uniform(seed: int = 42, n: int = 10000, lo: float = 0.0, hi: float = 1000.0):
    rnd = random.Random(seed)
    return [rnd.uniform(lo, hi) for _ in range(n)]


def _true_pct(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(p * len(s)))]


def _loaded(seed: int = 42, k: int = 15):
    ms = MomentSketch(k=k, seed=0)
    for v in _uniform(seed):
        ms.add(v)
    return ms


# ── construction / params ──────────────────────────────────────────────────────────

def test_default_params():
    ms = MomentSketch()
    assert ms.k == 15 and ms.seed == 0


def test_custom_params():
    ms = MomentSketch(k=10, seed=7)
    assert ms.k == 10 and ms.seed == 7


def test_len_starts_zero():
    assert len(MomentSketch()) == 0


def test_stats_keys():
    assert set(MomentSketch().stats()) == {"k", "seed", "total_count", "min_val", "max_val", "moments"}


def test_stats_initial():
    s = MomentSketch(k=8).stats()
    assert s["total_count"] == 0 and s["min_val"] is None and s["max_val"] is None
    assert len(s["moments"]) == 8


@pytest.mark.parametrize("bad", [0, -1, 1.5, "x", None, True])
def test_bad_k_raises(bad):
    with pytest.raises(MomentSketchError):
        MomentSketch(k=bad)


@pytest.mark.parametrize("bad", [1.5, "x", None, True])
def test_bad_seed_raises(bad):
    with pytest.raises(MomentSketchError):
        MomentSketch(seed=bad)


def test_error_carries_detail():
    err = MomentSketchError(-5)
    assert err.detail == -5


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_increments_count():
    ms = MomentSketch()
    ms.add(3.0)
    ms.add(5.0)
    assert ms.total_count == 2 and len(ms) == 2


def test_add_updates_min_max():
    ms = MomentSketch()
    for v in (5.0, 2.0, 9.0, 1.0):
        ms.add(v)
    s = ms.stats()
    assert s["min_val"] == 1.0 and s["max_val"] == 9.0


def test_add_accepts_int():
    ms = MomentSketch()
    ms.add(4)
    assert ms.total_count == 1


def test_add_negative_values():
    ms = MomentSketch()
    for v in (-10.0, -5.0, 0.0, 5.0):
        ms.add(v)
    assert ms.stats()["min_val"] == -10.0 and ms.stats()["max_val"] == 5.0


@pytest.mark.parametrize("bad", ["x", None, True, [1]])
def test_add_bad_value_raises(bad):
    with pytest.raises(MomentSketchError):
        MomentSketch().add(bad)


def test_add_many():
    ms = MomentSketch()
    ms.add_many([1.0, 2.0, 3.0])
    assert ms.total_count == 3


def test_add_many_non_iterable_raises():
    with pytest.raises(MomentSketchError):
        MomentSketch().add_many(123)


# ── moment correctness ───────────────────────────────────────────────────────────

def test_c0_is_exact_count():
    ms = _loaded()
    assert ms.stats()["moments"][0] == 10000.0


def test_c1_over_c0_is_mean():
    data = _uniform(seed=3)
    ms = MomentSketch(k=15)
    for v in data:
        ms.add(v)
    moments = ms.stats()["moments"]
    sample_mean = sum(data) / len(data)
    assert abs(moments[1] / moments[0] - sample_mean) / sample_mean <= 0.01


def test_power_sums_match_definition():
    ms = MomentSketch(k=4)
    for v in (2.0, 3.0):
        ms.add(v)
    m = ms.stats()["moments"]
    assert m[0] == 2.0
    assert m[1] == 5.0          # 2 + 3
    assert m[2] == 13.0         # 4 + 9
    assert m[3] == 35.0         # 8 + 27


# ── quantile ───────────────────────────────────────────────────────────────────────

def test_quantile_empty_raises():
    with pytest.raises(MomentSketchError):
        MomentSketch().quantile(0.5)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5, "x", None, True])
def test_quantile_bad_q_raises(bad):
    ms = MomentSketch()
    ms.add(1.0)
    with pytest.raises(MomentSketchError):
        ms.quantile(bad)


def test_quantile_uniform_p50():
    assert 475 <= _loaded().quantile(0.50) <= 525


def test_quantile_tail_p99_within_5pct():
    p99 = _loaded().quantile(0.99)
    assert 990 * 0.95 <= p99 <= 990 * 1.05


def test_quantile_monotonic():
    ms = _loaded()
    q25, q50, q75, q99 = (ms.quantile(0.25), ms.quantile(0.50),
                          ms.quantile(0.75), ms.quantile(0.99))
    assert q25 <= q50 <= q75 <= q99


def test_quantile_within_bounds():
    ms = _loaded()
    lo, hi = ms.stats()["min_val"], ms.stats()["max_val"]
    for q in (0.01, 0.5, 0.99):
        assert lo <= ms.quantile(q) <= hi


def test_quantile_single_value():
    ms = MomentSketch()
    for _ in range(50):
        ms.add(42.0)
    assert ms.quantile(0.5) == pytest.approx(42.0)


def test_quantile_skewed_exponential():
    rnd = random.Random(1)
    data = [rnd.expovariate(1 / 100) for _ in range(10000)]
    ms = MomentSketch(k=15)
    for v in data:
        ms.add(v)
    true_p50 = _true_pct(data, 0.50)
    assert abs(ms.quantile(0.50) - true_p50) / true_p50 <= 0.10


# ── merge ──────────────────────────────────────────────────────────────────────────

def test_merge_combines_counts():
    a = MomentSketch(k=10)
    b = MomentSketch(k=10)
    for v in range(30):
        a.add(float(v))
    for v in range(70):
        b.add(float(v))
    a.merge(b)
    assert a.total_count == 100


def test_merge_power_sums_add():
    a = MomentSketch(k=4)
    b = MomentSketch(k=4)
    a.add(2.0)
    b.add(3.0)
    a.merge(b)
    m = a.stats()["moments"]
    assert m[0] == 2.0 and m[1] == 5.0 and m[2] == 13.0


def test_merge_bounds():
    a = MomentSketch(k=5)
    b = MomentSketch(k=5)
    a.add(10.0)
    b.add(-3.0)
    b.add(99.0)
    a.merge(b)
    assert a.stats()["min_val"] == -3.0 and a.stats()["max_val"] == 99.0


def test_merge_p50_accuracy():
    rnd = random.Random(7)
    all_vals = []
    a = MomentSketch(k=15)
    b = MomentSketch(k=15)
    for _ in range(5000):
        x = rnd.uniform(0, 499)
        a.add(x)
        all_vals.append(x)
    for _ in range(5000):
        x = rnd.uniform(500, 999)
        b.add(x)
        all_vals.append(x)
    a.merge(b)
    true_p50 = _true_pct(all_vals, 0.50)
    assert abs(a.quantile(0.50) - true_p50) / true_p50 <= 0.05


def test_merge_different_k_raises():
    with pytest.raises(MomentSketchError):
        MomentSketch(k=10).merge(MomentSketch(k=12))


def test_merge_non_sketch_raises():
    with pytest.raises(MomentSketchError):
        MomentSketch().merge({"not": "a sketch"})


def test_merge_returns_self():
    a = MomentSketch(k=5)
    a.add(1.0)
    assert a.merge(MomentSketch(k=5)) is a


def test_merge_does_not_mutate_other():
    a = MomentSketch(k=8)
    b = MomentSketch(k=8)
    for v in range(100):
        b.add(float(v))
    before = list(b.stats()["moments"])
    a.merge(b)
    assert b.stats()["moments"] == before


def test_merge_state_roundtrip():
    src = MomentSketch(k=12)
    for v in _uniform(seed=9, n=2000):
        src.add(v)
    dst = MomentSketch(k=12)
    dst.merge_state(src.stats())
    assert dst.total_count == src.total_count
    assert dst.stats()["moments"] == src.stats()["moments"]


def test_from_state_reconstructs():
    src = MomentSketch(k=6)
    for v in (1.0, 2.0, 3.0):
        src.add(v)
    clone = MomentSketch.from_state(src.stats())
    assert clone.stats()["moments"] == src.stats()["moments"]
    assert clone.k == 6


def test_from_state_bad_input_raises():
    with pytest.raises(MomentSketchError):
        MomentSketch.from_state({"no": "moments"})


# ── determinism ──────────────────────────────────────────────────────────────────────

def test_determinism_same_moments_and_quantiles():
    data = _uniform(seed=99)
    a = MomentSketch(k=15, seed=0)
    b = MomentSketch(k=15, seed=0)
    for v in data:
        a.add(v)
    for v in data:
        b.add(v)
    assert a.stats()["moments"] == b.stats()["moments"]
    assert all(a.quantile(q) == b.quantile(q) for q in (0.1, 0.25, 0.5, 0.75, 0.9))


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    ms = _loaded()
    ms.reset()
    assert ms.total_count == 0 and ms.stats()["min_val"] is None


def test_reset_reconfigures():
    ms = MomentSketch(k=15)
    ms.reset(k=8, seed=3)
    assert ms.k == 8 and ms.seed == 3 and len(ms.stats()["moments"]) == 8


def test_reset_bad_config_raises():
    ms = MomentSketch()
    with pytest.raises(MomentSketchError):
        ms.reset(k=0)


def test_reset_then_usable():
    ms = _loaded()
    ms.reset(k=10)
    for v in range(100):
        ms.add(float(v))
    assert 0 <= ms.quantile(0.5) <= 99


# ── thread-safety ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    ms = MomentSketch(k=10)

    def worker():
        rnd = random.Random()
        for _ in range(500):
            ms.add(rnd.uniform(0, 1000))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ms.total_count == 8 * 500


# ── stats integration ───────────────────────────────────────────────────────────────

def test_stats_after_load():
    ms = _loaded()
    s = ms.stats()
    assert s["total_count"] == 10000 and s["k"] == 15 and len(s["moments"]) == 15
