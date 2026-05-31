"""Phase 94 — unit tests for CountSketch (pradyos/core/count_sketch.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.count_sketch import CountSketch, CountSketchError


def zipf_stream(seed=0):
    rnd = random.Random(seed)
    stream = ["HEAVY0"] * 3000 + ["HEAVY1"] * 1500 + ["HEAVY2"] * 1000
    stream += [f"light{rnd.randint(0, 800)}" for _ in range(4500)]
    rnd.shuffle(stream)
    return stream


# ── basic ────────────────────────────────────────────────────────────────────────

def test_update_tracks_total():
    cs = CountSketch()
    cs.update("a")
    cs.update("b", 3)
    assert cs.total_count == 4


def test_estimate_unseen_in_empty_is_zero():
    assert CountSketch().estimate("nothing") == 0


def test_len_tracks_total():
    cs = CountSketch()
    cs.update("a", 5)
    assert len(cs) == 5


def test_unique_elements_tracks_distinct():
    cs = CountSketch()
    cs.update("a")
    cs.update("a")
    cs.update("b")
    assert cs.unique_elements == 2


# ── unbiased accuracy ────────────────────────────────────────────────────────────

def test_single_element_unbiased():
    cs = CountSketch(depth=5, width=2048, seed=1)
    for _ in range(10_000):
        cs.update("solo")
    assert cs.estimate("solo") == 10_000


def test_update_with_count():
    cs = CountSketch(depth=5, width=2048, seed=0)
    cs.update("x", 250)
    assert cs.estimate("x") == 250


def test_unbiased_amid_noise():
    cs = CountSketch(depth=5, width=2048, seed=0)
    for _ in range(1000):
        cs.update("target")
    for i in range(5000):
        cs.update(f"noise{i}")              # distinct singletons
    assert abs(cs.estimate("target") - 1000) < 50      # no systematic inflation


def test_two_elements_estimates_close():
    cs = CountSketch(depth=5, width=2048, seed=0)
    for _ in range(500):
        cs.update("a")
    for _ in range(300):
        cs.update("b")
    assert abs(cs.estimate("a") - 500) <= 20
    assert abs(cs.estimate("b") - 300) <= 20


# ── heavy hitters ────────────────────────────────────────────────────────────────

def test_heavy_hitters_identifies_top_elements():
    cs = CountSketch(depth=5, width=2048, seed=0)
    for e in zipf_stream():
        cs.update(e)
    elems = {h["element"] for h in cs.heavy_hitters(0.01)}
    assert {"HEAVY0", "HEAVY1", "HEAVY2"}.issubset(elems)


def test_heavy_hitters_ranked_descending():
    cs = CountSketch(depth=5, width=2048, seed=0)
    for e in zipf_stream():
        cs.update(e)
    hh = cs.heavy_hitters(0.01)
    assert [h["element"] for h in hh[:3]] == ["HEAVY0", "HEAVY1", "HEAVY2"]
    estimates = [h["estimate"] for h in hh]
    assert estimates == sorted(estimates, reverse=True)


def test_heavy_hitters_structure():
    cs = CountSketch(seed=0)
    cs.update("a", 100)
    hh = cs.heavy_hitters(0.0)
    assert hh and set(hh[0]) == {"element", "estimate"}


def test_heavy_hitters_empty_when_below_threshold():
    cs = CountSketch(depth=5, width=2048, seed=0)
    for e in zipf_stream():
        cs.update(e)
    assert cs.heavy_hitters(0.99) == []        # nothing is 99% of the stream


def test_heavy_hitters_empty_sketch():
    assert CountSketch().heavy_hitters(0.1) == []


def test_heavy_hitters_invalid_threshold_raises():
    with pytest.raises(CountSketchError):
        CountSketch().heavy_hitters("half")


# ── deletion / negative counts ───────────────────────────────────────────────────

def test_deletion_via_negative_count():
    cs = CountSketch(depth=5, width=2048, seed=2)
    for _ in range(1000):
        cs.update("x")
    cs.update("x", -300)
    assert cs.estimate("x") == 700


def test_delete_to_zero():
    cs = CountSketch(depth=5, width=2048, seed=0)
    cs.update("x", 500)
    cs.update("x", -500)
    assert cs.estimate("x") == 0


def test_negative_estimate_for_unseen_colliding_element():
    # Documented trade-off: an unseen element colliding with negative updates reads < 0.
    cs = CountSketch(depth=5, width=2048, seed=4,
                     bucket_fn=lambda i, e: 0, sign_fn=lambda i, e: 0)
    cs.update("inserted", -10)
    assert cs.estimate("never-seen") == -10


def test_count_total_reflects_deletions():
    cs = CountSketch(seed=0)
    cs.update("x", 1000)
    cs.update("x", -400)
    assert cs.total_count == 600


# ── collision tolerance (injected hash) ──────────────────────────────────────────

def test_median_recovers_under_row0_collision():
    # Every element collides into bucket 0 of row 0; other rows spread them out.
    cs = CountSketch(depth=5, width=2048, seed=3, bucket_fn=lambda i, x: 0 if i == 0 else x)
    for x in range(2048):
        cs.update(x)
    assert all(cs.estimate(x) == 1 for x in range(0, 2048, 97))


def test_collision_single_row_does_not_dominate():
    cs = CountSketch(depth=5, width=4096, seed=5, bucket_fn=lambda i, x: 0 if i == 0 else x)
    for x in range(1000):
        cs.update(x, 2)
    assert cs.estimate(500) == 2               # median ignores the collided row 0


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism_same_seed():
    a = CountSketch(depth=5, width=512, seed=7)
    b = CountSketch(depth=5, width=512, seed=7)
    for i in range(3000):
        a.update(f"e{i % 400}")
        b.update(f"e{i % 400}")
    assert a._table == b._table


def test_different_seed_differs():
    a = CountSketch(depth=5, width=512, seed=1)
    b = CountSketch(depth=5, width=512, seed=2)
    for i in range(2000):
        a.update(f"e{i}")
        b.update(f"e{i}")
    assert a._table != b._table


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_depth_and_width():
    cs = CountSketch()
    assert cs.depth == 5 and cs.width == 2048


def test_configurable_depth_width():
    cs = CountSketch(depth=3, width=1024)
    assert cs.depth == 3 and cs.width == 1024


def test_invalid_depth_zero_raises():
    with pytest.raises(CountSketchError):
        CountSketch(depth=0)


def test_invalid_width_zero_raises():
    with pytest.raises(CountSketchError):
        CountSketch(width=0)


def test_invalid_depth_bool_raises():
    with pytest.raises(CountSketchError):
        CountSketch(depth=True)


def test_invalid_width_float_raises():
    with pytest.raises(CountSketchError):
        CountSketch(width=2.5)


def test_invalid_seed_float_raises():
    with pytest.raises(CountSketchError):
        CountSketch(seed=1.5)


def test_update_non_int_count_raises():
    with pytest.raises(CountSketchError):
        CountSketch().update("x", 1.5)


def test_count_sketch_error_stores_detail():
    err = CountSketchError(-3)
    assert err.detail == -3
    assert "invalid count sketch configuration" in str(err)


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(CountSketch().stats()) == {
        "depth", "width", "total_count", "unique_elements", "table_cells",
    }


def test_stats_initial():
    s = CountSketch(depth=4, width=256).stats()
    assert s == {"depth": 4, "width": 256, "total_count": 0,
                 "unique_elements": 0, "table_cells": 1024}


def test_stats_table_cells():
    assert CountSketch(depth=7, width=300).stats()["table_cells"] == 2100


def test_stats_tracks():
    cs = CountSketch(seed=0)
    cs.update("a", 5)
    cs.update("b", 3)
    st = cs.stats()
    assert st["total_count"] == 8 and st["unique_elements"] == 2


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    cs = CountSketch(seed=0)
    cs.update("a", 100)
    cs.reset()
    assert cs.total_count == 0 and cs.unique_elements == 0 and cs.estimate("a") == 0


def test_reset_reconfigures():
    cs = CountSketch(depth=5, width=2048)
    cs.reset(depth=3, width=512)
    assert cs.depth == 3 and cs.width == 512


def test_reset_invalid_raises():
    cs = CountSketch()
    with pytest.raises(CountSketchError):
        cs.reset(width=0)


def test_reset_then_reuse():
    cs = CountSketch(depth=5, width=2048, seed=0)
    cs.update("a", 50)
    cs.reset()
    cs.update("b", 70)
    assert cs.estimate("b") == 70 and cs.estimate("a") == 0


# ── element types & concurrency ──────────────────────────────────────────────────

def test_integer_elements():
    cs = CountSketch(depth=5, width=2048, seed=0)
    for _ in range(300):
        cs.update(42)
    assert cs.estimate(42) == 300


def test_concurrent_updates_10_threads():
    cs = CountSketch(depth=5, width=4096, seed=0)
    errors = []

    def worker(tag):
        try:
            for _ in range(200):
                cs.update(f"shared")
        except Exception as exc:              # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert cs.total_count == 2000
    assert cs.estimate("shared") == 2000
