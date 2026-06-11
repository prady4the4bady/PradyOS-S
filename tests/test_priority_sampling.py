"""Phase 131 — unit tests for PrioritySample / Duffield–Lund–Thorup (pradyos/core/priority_sampling.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.priority_sampling import PrioritySample, PrioritySampleError

CATS = ("a", "b", "c", "d")


def make_items(n, seed, cats=CATS):
    rng = random.Random(seed)
    return [(f"k{i}", rng.randint(1, 100), cats[i % len(cats)]) for i in range(n)]


def build(items, seed=0, k=256):
    s = PrioritySample(capacity=k, seed=seed)
    for key, w, c in items:
        s.add(key, w, c)
    return s


ITEMS = make_items(3000, seed=0)
TRUE_TOTAL = sum(w for _, w, _ in ITEMS)
TRUE_CAT = {c: sum(w for _, w, cc in ITEMS if cc == c) for c in CATS}


# ── unbiasedness (multi-seed means) ────────────────────────────────────────────────────

def test_mean_total_unbiased():
    ratios = [build(ITEMS, sd).total() / TRUE_TOTAL for sd in range(30)]
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.06       # measured ~0.986


def test_single_run_total_loose_bound():
    assert abs(build(ITEMS, 0).total() / TRUE_TOTAL - 1.0) < 0.20


def test_category_subset_unbiased():
    ratios = [build(ITEMS, sd).estimate("a") / TRUE_CAT["a"] for sd in range(30)]
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.10


def test_larger_capacity_tightens_error():
    def typ(k, seeds):
        return sum(abs(build(ITEMS, sd, k=k).total() / TRUE_TOTAL - 1.0)
                   for sd in range(seeds)) / seeds
    assert typ(1024, 15) < typ(256, 15)


# ── exact when N ≤ capacity ──────────────────────────────────────────────────────────────

def test_exact_when_under_capacity():
    small = make_items(50, seed=1)
    s = build(small, 0, k=256)
    assert abs(s.total() - sum(w for _, w, _ in small)) < 1e-6


def test_threshold_zero_when_under_capacity():
    assert build(make_items(50, seed=1), 0, k=256).threshold == 0.0


def test_holds_all_when_under_capacity():
    assert len(build(make_items(50, seed=1), 0, k=256)) == 50


def test_category_exact_when_under_capacity():
    small = make_items(40, seed=2)
    s = build(small, 0, k=256)
    true_a = sum(w for _, w, c in small if c == "a")
    assert abs(s.estimate("a") - true_a) < 1e-6


# ── order independence / determinism ─────────────────────────────────────────────────────

def test_order_independent_total():
    a = build(ITEMS, 7)
    shuffled = ITEMS[:]
    random.Random(123).shuffle(shuffled)
    b = build(shuffled, 7)
    assert abs(a.total() - b.total()) < 1e-6


def test_order_independent_sample_and_threshold():
    a = build(ITEMS, 7)
    shuffled = ITEMS[:]
    random.Random(321).shuffle(shuffled)
    b = build(shuffled, 7)
    assert set(a.sample_keys()) == set(b.sample_keys()) and a.threshold == b.threshold


def test_same_seed_identical():
    assert build(ITEMS, 5).total() == build(ITEMS, 5).total()


def test_different_seed_diverges():
    assert set(build(ITEMS, 1).sample_keys()) != set(build(ITEMS, 2).sample_keys())


# ── structural ─────────────────────────────────────────────────────────────────────────

def test_capacity_cap():
    assert len(build(ITEMS, 1, k=256)) == 256


def test_threshold_positive_when_over_capacity():
    assert build(ITEMS, 1, k=256).threshold > 0.0


def test_num_seen_counts_distinct():
    assert build(ITEMS, 1).num_seen == 3000


def test_total_equals_estimate_none():
    s = build(ITEMS, 3)
    assert s.total() == s.estimate(None)


def test_add_returns_sampled_bool():
    s = PrioritySample(capacity=2, seed=0)
    assert s.add("a", 10.0) is True and s.add("b", 10.0) is True
    res = s.add("c", 1e-9)                                    # tiny weight → unlikely to make the cut
    assert isinstance(res, bool)


def test_sample_keys_subset_of_added():
    s = build(make_items(100, seed=4), 0, k=20)
    added = {f"k{i}" for i in range(100)}
    assert set(s.sample_keys()).issubset(added) and len(s) == 20


def test_empty_total_zero():
    assert PrioritySample().total() == 0.0


def test_empty_estimate_zero():
    assert PrioritySample().estimate("a") == 0.0


# ── add_many ─────────────────────────────────────────────────────────────────────────────

def test_add_many_returns_count():
    assert PrioritySample(seed=0).add_many([("a", 1.0), ("b", 2.0), ("c", 3.0)]) == 3


def test_add_many_with_category():
    s = PrioritySample(seed=0)
    s.add_many([("a", 5.0, "x"), ("b", 5.0, "y")])
    assert s.estimate("x") == 5.0 and s.estimate("y") == 5.0


def test_add_many_bad_shape_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add_many([("a",)])                  # wrong arity


# ── re-add (last-write-wins) ──────────────────────────────────────────────────────────────

def test_readd_keeps_membership_count():
    s = PrioritySample(capacity=10, seed=0)
    for i in range(10):
        s.add(f"k{i}", 5.0)
    s.add("k0", 50.0)                                        # re-add larger
    assert len(s) == 10 and "k0" in s.sample_keys()


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_invalid_capacity_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample(capacity=0)


def test_invalid_seed_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample(seed="zero")


def test_bool_seed_rejected():
    with pytest.raises(PrioritySampleError):
        PrioritySample(seed=True)


def test_negative_weight_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add("a", -5.0)


def test_zero_weight_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add("a", 0.0)


def test_nonnumeric_weight_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add("a", "heavy")


def test_bool_weight_rejected():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add("a", True)


def test_invalid_category_type_raises():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add("a", 1.0, category=123)


def test_bool_key_rejected():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add(True, 1.0)


def test_float_key_rejected():
    with pytest.raises(PrioritySampleError):
        PrioritySample().add(3.14, 1.0)


def test_error_stores_detail():
    err = PrioritySampleError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── reset ──────────────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    s = build(ITEMS, 0)
    assert s.total() > 0.0
    s.reset()
    assert s.total() == 0.0 and len(s) == 0 and s.threshold == 0.0


def test_reset_reconfigures():
    s = PrioritySample(capacity=256, seed=0)
    s.reset(capacity=64, seed=9)
    assert s.capacity == 64 and s.seed == 9


def test_reset_invalid_raises():
    s = PrioritySample(seed=0)
    with pytest.raises(PrioritySampleError):
        s.reset(capacity=0)


# ── introspection ─────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(PrioritySample().stats()) == {
        "capacity", "sampled", "num_seen", "threshold", "total_estimate", "seed"}


def test_properties():
    s = PrioritySample(capacity=128, seed=4)
    assert s.capacity == 128 and s.seed == 4 and s.num_seen == 0


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    s = PrioritySample(capacity=128, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(500):
                s.add(f"k-{base}-{i}", float(i % 50) + 1.0)
        except Exception as exc:                              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(s) == 128 and s.num_seen == 5000
