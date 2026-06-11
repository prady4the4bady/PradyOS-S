"""Phase 104 — unit tests for the Sovereign Augmented Sketch (pradyos.core.augmented_sketch)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.augmented_sketch import AugmentedSketch, AugmentedSketchError


def _stream(seed: int = 1, heavy: int = 1000, hot: int = 100, n_hot: int = 4, total: int = 10000):
    rnd = random.Random(seed)
    s = ["HEAVY"] * heavy
    for i in range(n_hot):
        s += [f"hot{i}"] * hot
    produced, nid = 0, 0
    target = total - heavy - hot * n_hot
    while produced < target:
        c = min(rnd.randint(1, 4), target - produced)
        s += [f"noise{nid}"] * c
        produced += c
        nid += 1
    rnd.shuffle(s)
    return s


# ── construction / basics ──────────────────────────────────────────────────────

def test_default_params():
    a = AugmentedSketch()
    assert a.width == 1024 and a.depth == 4 and a.k == 10 and a.seed == 0


def test_custom_params():
    a = AugmentedSketch(width=256, depth=5, k=3, seed=9)
    assert (a.width, a.depth, a.k, a.seed) == (256, 5, 3, 9)


def test_stats_keys():
    assert set(AugmentedSketch().stats()) == {"width", "depth", "k", "seed", "tracked", "total"}


def test_stats_initial():
    s = AugmentedSketch().stats()
    assert s["tracked"] == 0 and s["total"] == 0


def test_len_is_tracked_count():
    a = AugmentedSketch(k=10)
    for x in ("a", "b", "c"):
        a.add(x)
    assert len(a) == 3


# ── add / query ─────────────────────────────────────────────────────────────────

def test_add_returns_estimate():
    a = AugmentedSketch()
    assert a.add("x") == 1


def test_add_with_delta():
    a = AugmentedSketch()
    assert a.add("x", 50) == 50


def test_add_accumulates():
    a = AugmentedSketch()
    a.add("x", 3)
    assert a.add("x", 4) == 7


def test_query_absent_is_zero():
    assert AugmentedSketch().query("never") == 0


def test_total_tracks_occurrences():
    a = AugmentedSketch()
    a.add("a", 10)
    a.add("b", 5)
    assert a.stats()["total"] == 15


def test_tracked_item_is_exact():
    a = AugmentedSketch(k=10)
    a.add("x", 123)
    assert a.query("x") == 123        # in the augmentation dict → exact


def test_integer_and_mixed_items():
    a = AugmentedSketch()
    a.add(7, 3)
    a.add("7", 1)
    assert a.query(7) == 3            # 7 and "7" are distinct items


# ── heavy-hitter accuracy ───────────────────────────────────────────────────────

def test_detects_heavy_hitters():
    a = AugmentedSketch(k=10, seed=0)
    for x in _stream(seed=1):
        a.add(x)
    items = {it for it, _ in a.top_k(10)}
    assert ({"HEAVY"} | {f"hot{i}" for i in range(4)}) <= items


def test_heavy_hitter_counts_near_exact():
    a = AugmentedSketch(k=10, seed=0)
    for x in _stream(seed=1):
        a.add(x)
    counts = dict(a.top_k(10))
    assert abs(counts["HEAVY"] - 1000) <= 50          # promoted → essentially exact
    assert all(abs(counts[f"hot{i}"] - 100) <= 50 for i in range(4))


# ── Count Sketch base / signed median ───────────────────────────────────────────

def test_sketch_estimate_quality_mid_frequency():
    a = AugmentedSketch(width=2048, depth=5, k=10, seed=0)
    stream = []
    for i in range(40):
        stream += [f"mid{i}"] * 50
    stream += [f"n{i}" for i in range(8000)]
    random.Random(2).shuffle(stream)
    for x in stream:
        a.add(x)
    est = a.sketch_estimate("mid5")
    assert abs(est - 50) <= 0.5 * 50                  # within ~30-50% (sketch error)


def test_signed_median_resists_collision_inflation():
    # Count Sketch base in isolation: A's signed-median estimate stays near its true
    # count despite heavy colliding noise (Count-Min's min could only over-count).
    a = AugmentedSketch(width=64, depth=15, seed=0)
    a._add_to_sketch("A", 100)
    rnd = random.Random(3)
    for i in range(300):
        a._add_to_sketch(f"noise{i}", rnd.randint(10, 40))
    assert 70 <= a.sketch_estimate("A") <= 130        # ≈ 100, not inflated to ~200


def test_sketch_estimate_absent_is_zero():
    assert AugmentedSketch().sketch_estimate("never") == 0


# ── augmentation promotion ──────────────────────────────────────────────────────

def test_promotion_from_sketch_to_exact():
    a = AugmentedSketch(width=512, depth=4, k=3, seed=0)
    for i in range(3):
        a.add(f"dummy{i}", 500)          # fill dict with heavy dummies
    assert "riser" not in a._exact
    for _ in range(600):
        a.add("riser")                   # climbs past the dummies → promoted
    assert "riser" in a._exact and a.query("riser") >= 100


def test_light_item_not_promoted_when_dict_full():
    a = AugmentedSketch(width=512, depth=4, k=3, seed=0)
    for i in range(3):
        a.add(f"dummy{i}", 500)
    a.add("light", 2)                    # nowhere near the dict minimum
    assert "light" not in a._exact


# ── top_k semantics ─────────────────────────────────────────────────────────────

def test_top_k_bounded_by_k():
    a = AugmentedSketch(k=3)
    for i in range(20):
        a.add(f"item{i}", i + 1)
    assert len(a.top_k()) == 3


def test_top_k_sorted_descending():
    a = AugmentedSketch(k=5)
    a.add("a", 30)
    a.add("b", 10)
    a.add("c", 20)
    counts = [c for _, c in a.top_k()]
    assert counts == sorted(counts, reverse=True)


def test_top_k_n_parameter():
    a = AugmentedSketch(k=10)
    for i in range(10):
        a.add(f"i{i}", i + 1)
    assert len(a.top_k(4)) == 4


def test_top_k_keeps_largest():
    a = AugmentedSketch(k=2)
    a.add("small", 1)
    a.add("big", 100)
    a.add("mid", 50)
    assert {it for it, _ in a.top_k()} == {"big", "mid"}


# ── determinism ─────────────────────────────────────────────────────────────────

def test_determinism_same_seed_same_stream():
    stream = _stream(seed=2)
    a = AugmentedSketch(seed=7)
    b = AugmentedSketch(seed=7)
    for x in stream:
        a.add(x)
    for x in stream:
        b.add(x)
    assert a.top_k() == b.top_k() and a._counter == b._counter


def test_different_seed_differs():
    a = AugmentedSketch(seed=1)
    b = AugmentedSketch(seed=2)
    for x in ("a", "b", "c"):
        a._add_to_sketch(x, 10)
        b._add_to_sketch(x, 10)
    assert a._counter != b._counter


# ── validation ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {"width": 0}, {"width": -1}, {"width": True},
    {"depth": 0}, {"k": 0}, {"seed": "x"}, {"seed": 1.5},
])
def test_invalid_config_raises(kwargs):
    with pytest.raises(AugmentedSketchError):
        AugmentedSketch(**kwargs)


def test_add_bad_delta_raises():
    a = AugmentedSketch()
    for bad in (0, -3, True, "5", 1.5):
        with pytest.raises(AugmentedSketchError):
            a.add("x", bad)


def test_error_detail_attribute():
    try:
        AugmentedSketch(k=0)
    except AugmentedSketchError as exc:
        assert exc.detail == 0
    else:
        pytest.fail("expected AugmentedSketchError")


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears():
    a = AugmentedSketch()
    a.add("x", 100)
    a.reset()
    assert a.stats()["total"] == 0 and a.stats()["tracked"] == 0 and a.query("x") == 0


def test_reset_reconfigures():
    a = AugmentedSketch(width=1024)
    a.reset(width=2048, k=5)
    assert a.width == 2048 and a.k == 5


def test_reset_bad_config_raises():
    a = AugmentedSketch()
    with pytest.raises(AugmentedSketchError):
        a.reset(width=0)


def test_reset_restores_determinism():
    stream = _stream(seed=4)
    a = AugmentedSketch(seed=5)
    for x in stream:
        a.add(x)
    first = a.top_k()
    a.reset()
    for x in stream:
        a.add(x)
    assert a.top_k() == first


# ── concurrency ─────────────────────────────────────────────────────────────────

def test_concurrent_adds_no_corruption():
    a = AugmentedSketch(k=10, seed=0)
    stream = _stream(seed=3)
    parts = [stream[i::8] for i in range(8)]

    def worker(part):
        for x in part:
            a.add(x)

    threads = [threading.Thread(target=worker, args=(p,)) for p in parts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(a._exact) <= 10
    assert "HEAVY" in {it for it, _ in a.top_k(10)}
