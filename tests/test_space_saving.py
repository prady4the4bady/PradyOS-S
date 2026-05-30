"""Phase 87 — unit tests for SpaceSaving (pradyos/core/space_saving.py)."""
from __future__ import annotations

import random
import threading
from collections import Counter

import pytest

from pradyos.core.space_saving import SpaceSaving, SpaceSavingError


# ── basic correctness ──────────────────────────────────────────────────────────

def test_add_single_item():
    s = SpaceSaving(k=4)
    s.add("a")
    assert s.count("a") == 1


def test_count_unmonitored_is_zero():
    assert SpaceSaving(k=4).count("ghost") == 0


def test_add_many_returns_count():
    s = SpaceSaving(k=4)
    assert s.add_many(["a", "b", "c"]) == 3


def test_len_tracks_monitored():
    s = SpaceSaving(k=10)
    s.add_many(["a", "b", "a"])
    assert len(s) == 2


def test_total_tracks_stream_length():
    s = SpaceSaving(k=2)
    s.add_many(["a", "b", "c", "d", "e"])
    assert s.total == 5


def test_contains_dunder_true_and_false():
    s = SpaceSaving(k=4)
    s.add("a")
    assert "a" in s
    assert "b" not in s


def test_repeated_item_increments():
    s = SpaceSaving(k=4)
    s.add_many(["x", "x", "x"])
    assert s.count("x") == 3


# ── deterministic eviction (k=2 : a,b,a,c) ──────────────────────────────────────

def test_deterministic_eviction_scenario():
    s = SpaceSaving(k=2)
    s.add_many(["a", "b", "a", "c"])
    assert s.count("a") == 2
    assert s.count("c") == 2
    assert s.count("b") == 0          # b had the min count → evicted by c


def test_evicted_item_drops_out():
    s = SpaceSaving(k=2)
    s.add_many(["a", "b", "a", "c"])
    assert "b" not in s


def test_reassigned_item_carries_error():
    s = SpaceSaving(k=2)
    s.add_many(["a", "b", "a", "c"])
    # c took b's slot at min_count=1 → its count over-estimates the truth by error=1
    assert s.error("c") == 1
    assert s.count("c") - 1 == s.error("c")   # est - true(=1) == error


def test_exact_count_has_zero_error():
    s = SpaceSaving(k=4)
    s.add_many(["a", "a", "a"])       # never evicted → exact
    assert s.error("a") == 0


# ── top-K ordering ───────────────────────────────────────────────────────────────

def test_top_orders_by_count_desc():
    s = SpaceSaving(k=5)
    s.add_many(["x"] * 5 + ["y"] * 3 + ["z"] * 1)
    assert [e["item"] for e in s.top()] == ["x", "y", "z"]


def test_top_n_slices():
    s = SpaceSaving(k=5)
    s.add_many(["x"] * 5 + ["y"] * 3 + ["z"] * 1)
    assert [e["item"] for e in s.top(2)] == ["x", "y"]


def test_top_zero_is_empty():
    s = SpaceSaving(k=5)
    s.add_many(["x", "y"])
    assert s.top(0) == []


def test_top_none_returns_all_monitored():
    s = SpaceSaving(k=5)
    s.add_many(["x", "y", "z"])
    assert len(s.top()) == 3


def test_top_n_larger_than_monitored():
    s = SpaceSaving(k=5)
    s.add_many(["x", "y"])
    assert len(s.top(99)) == 2


def test_top_tie_keeps_first_monitored_order():
    s = SpaceSaving(k=5)
    s.add("a")
    s.add("b")                        # both count 1 → 'a' first (stable)
    assert [e["item"] for e in s.top()] == ["a", "b"]


def test_top_entry_structure():
    s = SpaceSaving(k=5)
    s.add("a")
    assert set(s.top()[0]) == {"item", "count", "error"}


# ── heavy-hitter guarantee & error bound ─────────────────────────────────────────

def _skewed_stream(seed=42):
    stream = ["HEAVY1"] * 3000 + ["HEAVY2"] * 1500 + ["HEAVY3"] * 800
    rnd = random.Random(seed)
    stream += [f"noise{rnd.randint(0, 500)}" for _ in range(4000)]
    rnd.shuffle(stream)
    return stream


def test_heavy_hitter_guarantee_skewed():
    stream = _skewed_stream()
    n, k = len(stream), 10
    s = SpaceSaving(k=k)
    s.add_many(stream)
    truth = Counter(stream)
    monitored = {e["item"] for e in s.top()}
    heavy = [it for it, f in truth.items() if f > n / k]
    assert heavy, "test fixture should contain items above n/k"
    assert all(it in monitored for it in heavy)


def test_dominant_items_rank_at_top():
    s = SpaceSaving(k=10)
    s.add_many(_skewed_stream())
    assert [e["item"] for e in s.top(3)] == ["HEAVY1", "HEAVY2", "HEAVY3"]


def test_dominant_estimates_are_exact():
    s = SpaceSaving(k=10)
    s.add_many(_skewed_stream())
    # the three dominant items are never evicted → reported exactly, error 0
    assert s.count("HEAVY1") == 3000 and s.error("HEAVY1") == 0


def test_heavy_hitter_with_k_one():
    # k=1 keeps only the running "leader"; the overall most frequent must end on top.
    s = SpaceSaving(k=1)
    s.add_many(["a", "b", "a", "a", "c", "a"])
    assert s.top(1)[0]["item"] == "a"


def test_sum_of_counts_equals_total_invariant():
    s = SpaceSaving(k=8)
    rnd = random.Random(7)
    stream = [rnd.choice("abcdefghijklmnop") for _ in range(5000)]
    s.add_many(stream)
    assert sum(e["count"] for e in s.top()) == s.total == 5000


def test_overestimate_bounded_by_error_and_min_count():
    stream = _skewed_stream(seed=99)
    s = SpaceSaving(k=12)
    s.add_many(stream)
    truth = Counter(stream)
    min_count = s.stats()["min_count"]
    for e in s.top():
        assert e["count"] - truth[e["item"]] <= e["error"] <= min_count


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_k_is_ten():
    assert SpaceSaving().k == 10


def test_k_configurable():
    assert SpaceSaving(k=3).k == 3


def test_invalid_k_zero_raises():
    with pytest.raises(SpaceSavingError):
        SpaceSaving(k=0)


def test_invalid_k_negative_raises():
    with pytest.raises(SpaceSavingError):
        SpaceSaving(k=-5)


def test_invalid_k_bool_raises():
    with pytest.raises(SpaceSavingError):
        SpaceSaving(k=True)


def test_invalid_k_float_raises():
    with pytest.raises(SpaceSavingError):
        SpaceSaving(k=2.5)


def test_space_saving_error_stores_detail():
    err = SpaceSavingError(-3)
    assert err.detail == -3
    assert "invalid space-saving configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(SpaceSaving(k=4).stats()) == {"k", "monitored", "total", "min_count"}


def test_stats_initial_empty():
    s = SpaceSaving(k=4).stats()
    assert s == {"k": 4, "monitored": 0, "total": 0, "min_count": 0}


def test_stats_min_count_is_eviction_threshold():
    s = SpaceSaving(k=2)
    s.add_many(["a", "b", "a", "c"])   # counts 2 and 2 → min_count 2
    assert s.stats()["min_count"] == 2


def test_stats_total_and_monitored():
    s = SpaceSaving(k=3)
    s.add_many(["a", "b", "a", "c", "d"])
    st = s.stats()
    assert st["total"] == 5 and st["monitored"] == 3


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = SpaceSaving(k=4)
    s.add_many(["a", "b", "c"])
    s.reset()
    assert len(s) == 0 and s.total == 0 and s.stats()["min_count"] == 0


def test_reset_resizes_k():
    s = SpaceSaving(k=4)
    s.reset(k=2)
    assert s.k == 2


def test_reset_invalid_k_raises():
    s = SpaceSaving(k=4)
    with pytest.raises(SpaceSavingError):
        s.reset(k=0)


def test_reset_then_reuse():
    s = SpaceSaving(k=4)
    s.add_many(["a", "a"])
    s.reset()
    s.add("b")
    assert s.count("b") == 1 and s.count("a") == 0


# ── item types & robustness ──────────────────────────────────────────────────────

def test_integer_items():
    s = SpaceSaving(k=4)
    s.add_many([1, 1, 2, 3])
    assert s.count(1) == 2


def test_mixed_hashable_types():
    s = SpaceSaving(k=8)
    s.add_many(["a", 1, ("t", 2), "a"])
    assert s.count("a") == 2 and s.count(("t", 2)) == 1


def test_unhashable_item_raises_without_corrupting_total():
    s = SpaceSaving(k=4)
    s.add("ok")
    before = s.total
    with pytest.raises(TypeError):
        s.add(["unhashable"])
    assert s.total == before          # invariant preserved despite the failure


# ── concurrency ──────────────────────────────────────────────────────────────────

def test_concurrent_adds_10_threads():
    s = SpaceSaving(k=16)              # 10 distinct items, no eviction
    errors = []

    def worker(tag):
        try:
            for _ in range(100):
                s.add(f"t{tag}")
        except Exception as exc:       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert s.total == 1000
    assert all(s.count(f"t{i}") == 100 for i in range(10))


def test_concurrent_adds_preserve_sum_invariant_under_eviction():
    s = SpaceSaving(k=4)              # small k → heavy eviction under contention
    errors = []

    def worker(base):
        try:
            for i in range(200):
                s.add(f"k{(base + i) % 50}")
        except Exception as exc:       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert s.total == 8 * 200
    assert sum(e["count"] for e in s.top()) == s.total    # invariant holds under threads
