"""Phase 93 — unit tests for ThetaSketch (pradyos/core/theta_sketch.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.theta_sketch import ThetaError, ThetaSketch


def distinct(prefix, n, start=0):
    return [f"{prefix}{i}" for i in range(start, start + n)]


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_increments_n():
    s = ThetaSketch()
    for x in ["a", "b", "c"]:
        s.update(x)
    assert len(s) == 3


def test_update_many_returns_count():
    s = ThetaSketch()
    assert s.update_many(distinct("x", 100)) == 100


def test_estimate_empty_is_zero():
    assert ThetaSketch().estimate() == 0


def test_retained_count_empty():
    assert ThetaSketch().retained_count == 0


# ── cardinality accuracy ─────────────────────────────────────────────────────────

def test_distinct_count_accuracy():
    s = ThetaSketch(k=4096, seed=0)
    s.update_many(distinct("item-", 10_000))
    assert abs(s.estimate() - 10_000) / 10_000 < 0.05


def test_duplicates_do_not_inflate():
    s = ThetaSketch(k=4096, seed=0)
    for _ in range(10_000):
        s.update("same")
    assert s.estimate() == 1
    assert s.retained_count == 1 and len(s) == 10_000


def test_mixed_duplicates_count_distinct():
    s = ThetaSketch(k=4096, seed=0)
    items = distinct("d", 5000)
    s.update_many(items)
    s.update_many(items)                       # every item twice
    assert abs(s.estimate() - 5000) / 5000 < 0.06
    assert len(s) == 10_000


def test_exact_regime_below_k():
    s = ThetaSketch(k=4096, seed=0)
    s.update_many(distinct("e", 100))
    assert s.is_exact is True
    assert s.estimate() == 100


def test_exact_just_below_threshold():
    s = ThetaSketch(k=64, seed=0)
    s.update_many(distinct("u", 63))           # k-1 distinct → still exact
    assert s.is_exact is True and s.estimate() == 63


def test_not_exact_at_or_above_k():
    s = ThetaSketch(k=64, seed=0)
    s.update_many(distinct("u", 500))
    assert s.is_exact is False
    assert s.retained_count == 64


def test_larger_k_tighter_error():
    data = distinct("acc", 20_000)
    coarse = ThetaSketch(k=256, seed=0)
    fine = ThetaSketch(k=8192, seed=0)
    coarse.update_many(data)
    fine.update_many(data)
    assert abs(fine.estimate() - 20_000) <= abs(coarse.estimate() - 20_000)


# ── merge / union ────────────────────────────────────────────────────────────────

def test_merge_no_overlap():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    a.update_many(distinct("s", 5000, start=0))
    b.update_many(distinct("s", 5000, start=5000))
    a.merge(b)
    assert abs(a.estimate() - 10_000) / 10_000 < 0.05


def test_merge_full_overlap():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    items = distinct("o", 5000)
    a.update_many(items)
    b.update_many(items)
    a.merge(b)
    assert abs(a.estimate() - 5000) / 5000 < 0.06


def test_merge_combines_n():
    a = ThetaSketch(k=4096)
    b = ThetaSketch(k=4096)
    a.update_many(distinct("a", 3000))
    b.update_many(distinct("b", 4000))
    a.merge(b)
    assert len(a) == 7000


def test_union_estimate_non_destructive():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    a.update_many(distinct("s", 5000, start=0))
    b.update_many(distinct("s", 5000, start=5000))
    before = a.estimate()
    u = a.union_estimate(b)
    assert a.estimate() == before              # a unchanged
    assert abs(u - 10_000) / 10_000 < 0.05


def test_merge_empty_into_populated():
    a = ThetaSketch(k=4096, seed=0)
    a.update_many(distinct("p", 2000))
    before = a.estimate()
    a.merge(ThetaSketch(k=4096, seed=0))
    assert a.estimate() == before


def test_merge_populated_into_empty():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    b.update_many(distinct("q", 3000))
    a.merge(b)
    assert abs(a.estimate() - 3000) / 3000 < 0.06


def test_merge_non_theta_raises():
    with pytest.raises(ThetaError):
        ThetaSketch().merge("not a sketch")


# ── intersection ─────────────────────────────────────────────────────────────────

def test_intersection_estimate():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    a.update_many(distinct("x", 5000, start=0))
    b.update_many(distinct("x", 5000, start=2500))    # overlap = 2500
    inter = a.intersection_estimate(b)
    assert abs(inter - 2500) / 2500 < 0.10


def test_intersection_disjoint_near_zero():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    a.update_many(distinct("x", 4000, start=0))
    b.update_many(distinct("x", 4000, start=10_000))
    assert a.intersection_estimate(b) / 4000 < 0.05


def test_intersection_full_overlap():
    a = ThetaSketch(k=4096, seed=0)
    b = ThetaSketch(k=4096, seed=0)
    items = distinct("y", 4000)
    a.update_many(items)
    b.update_many(items)
    assert abs(a.intersection_estimate(b) - 4000) / 4000 < 0.08


def test_intersection_non_theta_raises():
    with pytest.raises(ThetaError):
        ThetaSketch().intersection_estimate(42)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_seed():
    a = ThetaSketch(k=512, seed=7)
    b = ThetaSketch(k=512, seed=7)
    data = distinct("d", 5000)
    a.update_many(data)
    b.update_many(data)
    assert a._set == b._set
    assert a.stats()["theta"] == b.stats()["theta"]


def test_different_seed_differs():
    a = ThetaSketch(k=512, seed=1)
    b = ThetaSketch(k=512, seed=2)
    data = distinct("d", 5000)
    a.update_many(data)
    b.update_many(data)
    assert a._set != b._set


# ── theta / retained ─────────────────────────────────────────────────────────────

def test_theta_is_one_below_k():
    s = ThetaSketch(k=4096, seed=0)
    s.update_many(distinct("t", 100))
    assert s.stats()["theta"] == 1.0


def test_theta_below_one_when_full():
    s = ThetaSketch(k=256, seed=0)
    s.update_many(distinct("t", 5000))
    assert 0.0 < s.stats()["theta"] < 1.0


def test_retained_count_caps_at_k():
    s = ThetaSketch(k=1024, seed=0)
    s.update_many(distinct("t", 10_000))
    assert s.retained_count == 1024


def test_is_exact_transitions_at_k():
    s = ThetaSketch(k=50, seed=0)
    s.update_many(distinct("t", 49))
    assert s.is_exact is True
    s.update_many(distinct("t", 200, start=49))
    assert s.is_exact is False


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_k():
    assert ThetaSketch().k == 4096


def test_configurable_k():
    assert ThetaSketch(k=1024).k == 1024


def test_invalid_k_zero_raises():
    with pytest.raises(ThetaError):
        ThetaSketch(k=0)


def test_invalid_k_one_raises():
    with pytest.raises(ThetaError):
        ThetaSketch(k=1)


def test_invalid_k_bool_raises():
    with pytest.raises(ThetaError):
        ThetaSketch(k=True)


def test_invalid_k_float_raises():
    with pytest.raises(ThetaError):
        ThetaSketch(k=2.5)


def test_invalid_seed_float_raises():
    with pytest.raises(ThetaError):
        ThetaSketch(k=4096, seed=1.5)


def test_theta_error_stores_detail():
    err = ThetaError(-3)
    assert err.detail == -3
    assert "invalid theta sketch configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(ThetaSketch().stats()) == {
        "k", "n", "theta", "retained_count", "is_exact", "estimate",
    }


def test_stats_initial():
    s = ThetaSketch(k=1024).stats()
    assert s == {"k": 1024, "n": 0, "theta": 1.0, "retained_count": 0,
                 "is_exact": True, "estimate": 0}


def test_stats_tracks_inserts():
    s = ThetaSketch(k=4096)
    s.update_many(distinct("s", 500))
    st = s.stats()
    assert st["n"] == 500 and st["retained_count"] == 500 and st["is_exact"] is True


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = ThetaSketch()
    s.update_many(distinct("s", 1000))
    s.reset()
    assert s.estimate() == 0 and len(s) == 0 and s.retained_count == 0


def test_reset_reconfigures_k():
    s = ThetaSketch(k=4096)
    s.reset(k=256)
    assert s.k == 256


def test_reset_then_reuse():
    s = ThetaSketch(k=4096, seed=0)
    s.update_many(distinct("a", 500))
    s.reset()
    s.update_many(distinct("b", 100))
    assert s.estimate() == 100


# ── element types & concurrency ──────────────────────────────────────────────────

def test_integer_elements():
    s = ThetaSketch(k=4096, seed=0)
    s.update_many(range(5000))
    assert abs(s.estimate() - 5000) / 5000 < 0.06


def test_estimate_is_numeric():
    s = ThetaSketch(k=256, seed=0)
    s.update_many(distinct("s", 5000))
    assert isinstance(s.estimate(), float) and s.estimate() > 0


def test_concurrent_updates_10_threads():
    s = ThetaSketch(k=4096, seed=0)
    errors = []

    def worker(tag):
        try:
            for i in range(500):
                s.update(f"t{tag}-{i}")
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(s) == 5000
    assert abs(s.estimate() - 5000) / 5000 < 0.06
