"""Phase 95 — unit tests for LossyCount (pradyos/core/lossy_count.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.lossy_count import LossyCount, LossyCountError


def zipf_stream(seed=1):
    stream = []
    for i in range(1, 101):
        stream += [f"z{i}"] * (10000 // i)
    random.Random(seed).shuffle(stream)
    return stream


def zipf_truth():
    return {f"z{i}": 10000 // i for i in range(1, 101)}


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_tracks_n():
    lc = LossyCount()
    lc.update("a")
    lc.update("b", 3)
    assert lc.n == 4


def test_estimate_unseen_is_zero():
    assert LossyCount().estimate("nothing") == 0


def test_len_tracks_n():
    lc = LossyCount()
    lc.update("a", 5)
    assert len(lc) == 5


def test_entries_tracks_table_size():
    lc = LossyCount(epsilon=0.01)
    lc.update("a")
    lc.update("b")
    assert lc.entries == 2


# ── frequency accuracy & guarantees ──────────────────────────────────────────────

def test_single_element_estimate():
    lc = LossyCount(epsilon=0.001)
    for _ in range(5000):
        lc.update("x")
    assert lc.estimate("x") == 5000


def test_update_with_count():
    lc = LossyCount(epsilon=0.001)
    lc.update("x", 250)
    assert lc.estimate("x") == 250


def test_uniform_below_threshold_is_empty():
    lc = LossyCount(epsilon=0.001)
    stream = [f"u{i % 100}" for i in range(10_000)]
    random.Random(0).shuffle(stream)
    for e in stream:
        lc.update(e)
    assert lc.heavy_hitters(0.05) == []          # each element is 1% — below 5%


def test_uniform_low_threshold_returns_all():
    lc = LossyCount(epsilon=0.001)
    stream = [f"u{i % 100}" for i in range(10_000)]
    random.Random(0).shuffle(stream)
    for e in stream:
        lc.update(e)
    assert len(lc.heavy_hitters(0.005)) == 100   # all retained, returned at 0.5%


def test_zipf_no_false_negatives():
    lc = LossyCount(epsilon=0.001)
    stream = zipf_stream()
    for e in stream:
        lc.update(e)
    n = len(stream)
    truth = zipf_truth()
    must = {e for e, f in truth.items() if f >= 0.05 * n}
    got = {h["element"] for h in lc.heavy_hitters(0.05)}
    assert must.issubset(got)


def test_zipf_ranked_descending():
    lc = LossyCount(epsilon=0.001)
    for e in zipf_stream():
        lc.update(e)
    hh = lc.heavy_hitters(0.05)
    assert [h["element"] for h in hh[:3]] == ["z1", "z2", "z3"]
    freqs = [h["frequency"] for h in hh]
    assert freqs == sorted(freqs, reverse=True)


def test_single_element_in_heavy_hitters():
    lc = LossyCount(epsilon=0.001)
    stream = ["x"] * 5000 + [f"o{i}" for i in range(5000)]
    random.Random(2).shuffle(stream)
    for e in stream:
        lc.update(e)
    assert "x" in {h["element"] for h in lc.heavy_hitters(0.3)}


def test_no_false_positives_above_threshold():
    lc = LossyCount(epsilon=0.001)
    stream = zipf_stream()
    for e in stream:
        lc.update(e)
    n = len(stream)
    truth = zipf_truth()
    for h in lc.heavy_hitters(0.05):
        assert truth[h["element"]] >= (0.05 - 0.001) * n


def test_estimate_underestimates_within_delta():
    lc = LossyCount(epsilon=0.001)
    stream = zipf_stream()
    for e in stream:
        lc.update(e)
    n = len(stream)
    truth = zipf_truth()
    for i in range(1, 101):
        e = f"z{i}"
        est = lc.estimate(e)
        if est:                                  # retained
            assert est <= truth[e]               # never over-counts
            assert truth[e] - est <= 0.001 * n   # under-count bounded by ε·n


# ── sweep / space ────────────────────────────────────────────────────────────────

def test_sweep_invariant():
    lc = LossyCount(epsilon=0.001)
    for e in zipf_stream():
        lc.update(e)
    b = lc.stats()["current_bucket"]
    assert all(v[0] + v[1] > b for v in lc._d.values())


def test_space_bound_sublinear():
    lc = LossyCount(epsilon=0.001)
    stream = zipf_stream()
    for e in stream:
        lc.update(e)
    assert lc.entries < len(stream)
    assert lc.entries < (1 / 0.001) * math.log(max(0.001 * len(stream), 2))


def test_rare_elements_swept():
    lc = LossyCount(epsilon=0.01)                # w = 100
    # 5000 singletons interleaved with a dominant element → singletons get swept
    stream = []
    for i in range(5000):
        stream += ["DOMINANT", f"rare{i}"]
    for e in stream:
        lc.update(e)
    assert lc.entries < 5000                     # far fewer than the 5001 distinct elements
    assert lc.estimate("DOMINANT") > 0


# ── no-deletion guard ─────────────────────────────────────────────────────────────

def test_negative_count_raises():
    with pytest.raises(LossyCountError):
        LossyCount().update("x", -1)


def test_negative_count_error_mentions_deletion():
    with pytest.raises(LossyCountError, match="deletion"):
        LossyCount().update("x", -5)


def test_zero_count_is_noop():
    lc = LossyCount()
    lc.update("x", 0)
    assert lc.n == 0 and lc.estimate("x") == 0


def test_non_int_count_raises():
    with pytest.raises(LossyCountError):
        LossyCount().update("x", 1.5)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_seed_ignored():
    a = LossyCount(epsilon=0.001, seed=1)
    b = LossyCount(epsilon=0.001, seed=999)
    for e in zipf_stream():
        a.update(e)
        b.update(e)
    assert a._d == b._d


def test_deterministic_same_stream():
    a = LossyCount(epsilon=0.001)
    b = LossyCount(epsilon=0.001)
    stream = zipf_stream()
    for e in stream:
        a.update(e)
        b.update(e)
    assert all(a.estimate(f"z{i}") == b.estimate(f"z{i}") for i in range(1, 101))


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_epsilon():
    assert LossyCount().epsilon == 0.001


def test_configurable_epsilon():
    assert LossyCount(epsilon=0.01).epsilon == 0.01


def test_bucket_width_is_ceil_inverse_epsilon():
    assert LossyCount(epsilon=0.001).bucket_width == 1000
    assert LossyCount(epsilon=0.003).bucket_width == math.ceil(1 / 0.003)


def test_invalid_epsilon_zero_raises():
    with pytest.raises(LossyCountError):
        LossyCount(epsilon=0.0)


def test_invalid_epsilon_one_raises():
    with pytest.raises(LossyCountError):
        LossyCount(epsilon=1.0)


def test_invalid_epsilon_negative_raises():
    with pytest.raises(LossyCountError):
        LossyCount(epsilon=-0.1)


def test_invalid_epsilon_bool_raises():
    with pytest.raises(LossyCountError):
        LossyCount(epsilon=True)


def test_seed_accepted_but_unused():
    lc = LossyCount(epsilon=0.001, seed="anything")
    lc.update("x")
    assert lc.estimate("x") == 1                 # seed has no effect


def test_lossy_count_error_stores_detail():
    err = LossyCountError(-3)
    assert err.detail == -3
    assert "invalid lossy counting operation" in str(err)


# ── heavy_hitters validation ─────────────────────────────────────────────────────

def test_heavy_hitters_invalid_support_zero():
    with pytest.raises(LossyCountError):
        LossyCount().heavy_hitters(0.0)


def test_heavy_hitters_invalid_support_above_one():
    with pytest.raises(LossyCountError):
        LossyCount().heavy_hitters(1.5)


def test_heavy_hitters_structure():
    lc = LossyCount(epsilon=0.01)
    for _ in range(500):
        lc.update("a")
    hh = lc.heavy_hitters(0.5)
    assert hh and set(hh[0]) == {"element", "frequency"}


def test_heavy_hitters_empty_when_no_data():
    assert LossyCount().heavy_hitters(0.1) == []


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(LossyCount().stats()) == {
        "epsilon", "n", "bucket_width", "entries", "current_bucket",
    }


def test_stats_initial():
    s = LossyCount(epsilon=0.01).stats()
    assert s == {"epsilon": 0.01, "n": 0, "bucket_width": 100,
                 "entries": 0, "current_bucket": 0}


def test_stats_tracks():
    lc = LossyCount(epsilon=0.001)
    for _ in range(2500):
        lc.update("a")
    s = lc.stats()
    assert s["n"] == 2500 and s["current_bucket"] == math.ceil(2500 / 1000)


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    lc = LossyCount(epsilon=0.001)
    for _ in range(1000):
        lc.update("a")
    lc.reset()
    assert lc.n == 0 and lc.entries == 0 and lc.estimate("a") == 0


def test_reset_reconfigures_epsilon():
    lc = LossyCount(epsilon=0.001)
    lc.reset(epsilon=0.01)
    assert lc.epsilon == 0.01 and lc.bucket_width == 100


def test_reset_then_reuse():
    lc = LossyCount(epsilon=0.001)
    lc.update("a", 50)
    lc.reset()
    lc.update("b", 70)
    assert lc.estimate("b") == 70 and lc.estimate("a") == 0


# ── element types & concurrency ──────────────────────────────────────────────────

def test_integer_elements():
    lc = LossyCount(epsilon=0.001)
    for _ in range(300):
        lc.update(42)
    assert lc.estimate(42) == 300


def test_concurrent_updates_10_threads():
    lc = LossyCount(epsilon=0.001)
    errors = []

    def worker(tag):
        try:
            for _ in range(300):
                lc.update("shared")
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert lc.n == 3000
    assert lc.estimate("shared") == 3000
