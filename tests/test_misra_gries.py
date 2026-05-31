"""Phase 99 — unit tests for MisraGries (pradyos/core/misra_gries.py).

Note on the heavy-hitter guarantee: Misra-Gries retains every element with true
frequency > n/(k+1), so ``heavy_hitters(support)`` has no false negatives among
elements with true frequency ≥ support·n **only when support > 1/(k+1)**. The
no-false-negative tests therefore use a ``k`` large enough for the chosen support;
the rigorous "freq > n/(k+1) ⇒ retained" guarantee is tested separately for any k.
"""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.misra_gries import MisraGries, MisraGriesError


def zipf_stream(seed=0):
    truth = {f"e{i}": 10000 // i for i in range(1, 201)}
    stream = []
    for e, c in truth.items():
        stream += [e] * c
    random.Random(seed).shuffle(stream)
    return stream, truth


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_tracks_n():
    mg = MisraGries(5)
    mg.update("a")
    mg.update("b", 3)
    assert mg.n == 4


def test_estimate_unseen_is_zero():
    assert MisraGries(5).estimate("never_seen") == 0


def test_len_tracks_n():
    mg = MisraGries(5)
    mg.update("a", 10)
    assert len(mg) == 10


def test_counters_property():
    mg = MisraGries(10)
    for e in "abc":
        mg.update(e)
    assert mg.counters == 3


# ── heavy hitters & guarantees ───────────────────────────────────────────────────

def test_zipf_no_false_negatives():
    stream, truth = zipf_stream()
    n = len(stream)
    mg = MisraGries(k=20)                       # support 0.05 > 1/(k+1) = 0.0476
    for e in stream:
        mg.update(e)
    must = {e for e, f in truth.items() if f >= 0.05 * n}
    got = {h["element"] for h in mg.heavy_hitters(0.05)}
    assert must.issubset(got)


def test_rigorous_retention_guarantee():
    # For ANY k: every element with true freq > n/(k+1) is retained in the summary.
    stream, truth = zipf_stream()
    n = len(stream)
    mg = MisraGries(k=10)
    for e in stream:
        mg.update(e)
    guaranteed = {e for e, f in truth.items() if f > n / (mg.k + 1)}
    assert all(mg.estimate(e) > 0 for e in guaranteed)


def test_undercount_bounded_by_threshold():
    stream, truth = zipf_stream()
    n = len(stream)
    mg = MisraGries(k=20)
    for e in stream:
        mg.update(e)
    bound = n / (mg.k + 1)
    for h in mg.heavy_hitters(0.05):
        assert truth[h["element"]] - h["count"] <= bound


def test_estimate_never_overcounts():
    stream, truth = zipf_stream()
    mg = MisraGries(k=30)
    for e in stream:
        mg.update(e)
    for e in truth:
        assert mg.estimate(e) <= truth[e]      # MG only ever under-counts


def test_zipf_top_ranked():
    stream, _truth = zipf_stream()
    mg = MisraGries(k=50)
    for e in stream:
        mg.update(e)
    hh = mg.heavy_hitters(0.05)
    assert [h["element"] for h in hh[:3]] == ["e1", "e2", "e3"]


def test_heavy_hitters_sorted_descending():
    stream, _truth = zipf_stream()
    mg = MisraGries(k=50)
    for e in stream:
        mg.update(e)
    counts = [h["count"] for h in mg.heavy_hitters(0.05)]
    assert counts == sorted(counts, reverse=True)


def test_heavy_hitters_structure():
    mg = MisraGries(5)
    mg.update("a", 100)
    hh = mg.heavy_hitters(0.5)
    assert hh and set(hh[0]) == {"element", "count"}


def test_heavy_hitters_empty_when_no_data():
    assert MisraGries(5).heavy_hitters(0.1) == []


# ── decrement-all (the distinctive Misra-Gries step) ─────────────────────────────

def test_decrement_all_empties_full_table():
    mg = MisraGries(2)
    mg.update("a")
    mg.update("b")
    mg.update("c")                             # miss → decrement a,b by 1 → both drop
    assert mg.estimate("a") == 0 and mg.estimate("b") == 0 and mg.estimate("c") == 0


def test_decrement_all_partial():
    mg = MisraGries(2)
    mg.update("a", 5)
    mg.update("b", 3)
    mg.update("c", 2)                          # miss with count 2 → a=3, b=1
    assert mg.estimate("a") == 3 and mg.estimate("b") == 1 and mg.estimate("c") == 0


def test_counter_cap():
    mg = MisraGries(20)
    rnd = random.Random(1)
    worst = 0
    for _ in range(10_000):
        mg.update(rnd.choice("abcdefghijklmnopqrstuvwxyz0123456789"))
        worst = max(worst, mg.counters)
    assert worst <= 20


def test_monitored_item_increments():
    mg = MisraGries(5)
    mg.update("a")
    mg.update("a")
    mg.update("a", 3)
    assert mg.estimate("a") == 5


def test_free_slot_insert():
    mg = MisraGries(5)
    for e in "abc":
        mg.update(e)
    assert mg.estimate("b") == 1 and mg.counters == 3


def test_estimate_with_count():
    mg = MisraGries(5)
    mg.update("x", 250)
    assert mg.estimate("x") == 250


# ── deletion guard ────────────────────────────────────────────────────────────────

def test_count_zero_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(5).update("x", 0)


def test_count_negative_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(5).update("x", -1)


def test_deletion_message():
    with pytest.raises(MisraGriesError, match="does not support deletion"):
        MisraGries(5).update("x", -5)


def test_non_int_count_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(5).update("x", 1.5)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_seed_ignored():
    a = MisraGries(10, seed=1)
    b = MisraGries(10, seed=999)
    stream, _ = zipf_stream()
    for e in stream[:5000]:
        a.update(e)
        b.update(e)
    assert a._counters == b._counters


def test_deterministic_same_stream():
    a = MisraGries(15)
    b = MisraGries(15)
    stream, _ = zipf_stream()
    for e in stream:
        a.update(e)
        b.update(e)
    assert all(a.estimate(f"e{i}") == b.estimate(f"e{i}") for i in range(1, 201))


# ── configuration & validation ───────────────────────────────────────────────────

def test_k_one_allowed():
    mg = MisraGries(1)
    mg.update("a")
    assert mg.counters <= 1


def test_invalid_k_zero_raises():
    with pytest.raises(MisraGriesError, match="k must be at least 1"):
        MisraGries(0)


def test_invalid_k_negative_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(-5)


def test_invalid_k_bool_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(True)


def test_invalid_k_float_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(2.5)


def test_error_stores_detail():
    err = MisraGriesError(-3)
    assert err.detail == -3


def test_heavy_hitters_support_zero_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(5).heavy_hitters(0)


def test_heavy_hitters_support_above_one_raises():
    with pytest.raises(MisraGriesError):
        MisraGries(5).heavy_hitters(1.5)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(MisraGries(5).stats()) == {"k", "n", "counters", "threshold"}


def test_stats_initial():
    assert MisraGries(7).stats() == {"k": 7, "n": 0, "counters": 0, "threshold": 0.0}


def test_stats_threshold_tracks():
    mg = MisraGries(9)
    for _ in range(100):
        mg.update("a")
    assert mg.stats()["threshold"] == 100 / 10


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    mg = MisraGries(5)
    for _ in range(50):
        mg.update("a")
    mg.reset()
    assert mg.n == 0 and mg.counters == 0 and mg.estimate("a") == 0


def test_reset_reconfigures_k():
    mg = MisraGries(5)
    mg.reset(k=20)
    assert mg.k == 20


def test_reset_then_reuse():
    mg = MisraGries(5)
    mg.update("a", 10)
    mg.reset()
    mg.update("b", 7)
    assert mg.estimate("b") == 7 and mg.estimate("a") == 0


# ── element types & concurrency ──────────────────────────────────────────────────

def test_integer_elements():
    mg = MisraGries(5)
    for _ in range(300):
        mg.update(42)
    assert mg.estimate(42) == 300


def test_concurrent_updates_10_threads():
    mg = MisraGries(50)
    errors = []

    def worker(tag):
        try:
            for _ in range(300):
                mg.update("shared")
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert mg.n == 3000
    assert mg.estimate("shared") == 3000
