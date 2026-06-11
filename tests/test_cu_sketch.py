"""Phase 123 — unit tests for CUSketch (pradyos/core/cu_sketch.py)."""
from __future__ import annotations

import hashlib
import random
import threading

import pytest

from pradyos.core.cu_sketch import CUSketch, CUSketchError


class _NaiveCM:
    """Plain Count-Min (all-counter increment) sharing CUSketch hashing, for comparison."""
    def __init__(self, w, d, seed):
        self.w, self.d, self.seed, self.c = w, d, seed, [0] * (w * d)

    def _idx(self, item):
        dg = hashlib.blake2b(repr((self.seed, item)).encode(), digest_size=16).digest()
        h1 = int.from_bytes(dg[:8], "big")
        h2 = int.from_bytes(dg[8:], "big") | 1
        return [r * self.w + ((h1 + r * h2) % self.w) for r in range(self.d)]

    def add(self, item, amt=1):
        for c in self._idx(item):
            self.c[c] += amt

    def estimate(self, item):
        return min(self.c[c] for c in self._idx(item))


def _stream():
    s = []
    for i in range(5000):
        s.extend([f"k{i}"] * ((i % 5) + 1))
    random.Random(7).shuffle(s)
    return s


# ── correctness ─────────────────────────────────────────────────────────────────

def test_empty_estimate_zero():
    assert CUSketch(width=256, seed=0).estimate("x") == 0


def test_never_undercounts():
    stream = _stream()
    truth = {}
    cu = CUSketch(width=256, depth=4, seed=0)
    for k in stream:
        cu.add(k)
        truth[k] = truth.get(k, 0) + 1
    assert all(cu.estimate(k) >= v for k, v in truth.items())


def test_cu_at_most_count_min():
    stream = _stream()
    cu = CUSketch(width=256, depth=4, seed=0)
    cm = _NaiveCM(256, 4, 0)
    truth = {}
    for k in stream:
        cu.add(k)
        cm.add(k)
        truth[k] = truth.get(k, 0) + 1
    assert all(cu.estimate(k) <= cm.estimate(k) for k in truth)


def test_cu_tighter_than_count_min_on_average():
    stream = _stream()
    cu = CUSketch(width=256, depth=4, seed=0)
    cm = _NaiveCM(256, 4, 0)
    truth = {}
    for k in stream:
        cu.add(k)
        cm.add(k)
        truth[k] = truth.get(k, 0) + 1
    cu_err = sum(cu.estimate(k) - v for k, v in truth.items()) / len(truth)
    cm_err = sum(cm.estimate(k) - v for k, v in truth.items()) / len(truth)
    assert cu_err < cm_err


def test_exact_at_low_load():
    cu = CUSketch(width=8192, depth=4, seed=0)
    counts = {f"x{i}": (i % 7) + 1 for i in range(50)}
    for k, c in counts.items():
        cu.add(k, c)
    assert all(cu.estimate(k) == c for k, c in counts.items())


def test_heavy_hitter_accurate():
    cu = CUSketch(width=512, depth=4, seed=0)
    for _ in range(10000):
        cu.add("HOT")
    for i in range(20000):
        cu.add(f"cold{i % 5000}")
    assert abs(cu.estimate("HOT") - 10000) / 10000 < 0.02


# ── amount / total ─────────────────────────────────────────────────────────────────

def test_amount_increments():
    cu = CUSketch(width=8192, depth=4, seed=0)
    cu.add("k", 5)
    cu.add("k", 3)
    assert cu.estimate("k") == 8 and cu.total == 8


def test_default_amount_one():
    cu = CUSketch(width=8192, depth=4, seed=0)
    cu.add("k")
    assert cu.estimate("k") == 1


def test_total_tracks_mass():
    cu = CUSketch(width=512, seed=0)
    for i in range(100):
        cu.add(f"k{i}", 2)
    assert cu.total == 200


# ── determinism ──────────────────────────────────────────────────────────────────

def test_determinism():
    stream = _stream()[:5000]
    x = CUSketch(width=1024, depth=4, seed=5)
    y = CUSketch(width=1024, depth=4, seed=5)
    for k in stream:
        x.add(k)
        y.add(k)
    assert x._counters == y._counters
    assert all(x.estimate(f"k{i}") == y.estimate(f"k{i}") for i in range(100))


def test_different_seed_diverges():
    stream = _stream()[:5000]
    x = CUSketch(width=512, depth=4, seed=1)
    y = CUSketch(width=512, depth=4, seed=2)
    for k in stream:
        x.add(k)
        y.add(k)
    assert x._counters != y._counters


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_width_raises():
    with pytest.raises(CUSketchError):
        CUSketch(width=0)


def test_invalid_depth_raises():
    with pytest.raises(CUSketchError):
        CUSketch(depth=0)


def test_invalid_seed_raises():
    with pytest.raises(CUSketchError):
        CUSketch(seed="nope")


def test_bool_width_rejected():
    with pytest.raises(CUSketchError):
        CUSketch(width=True)


def test_add_zero_amount_raises():
    with pytest.raises(CUSketchError):
        CUSketch(width=512, seed=0).add("k", 0)


def test_add_negative_amount_raises():
    with pytest.raises(CUSketchError):
        CUSketch(width=512, seed=0).add("k", -1)


def test_add_non_int_amount_raises():
    with pytest.raises(CUSketchError):
        CUSketch(width=512, seed=0).add("k", 2.5)


def test_error_stores_detail():
    err = CUSketchError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    cu = CUSketch(width=4096, depth=5, seed=7)
    assert cu.width == 4096 and cu.depth == 5 and cu.seed == 7


def test_stats_keys():
    assert set(CUSketch(width=512, seed=0).stats()) == {
        "width", "depth", "total", "num_counters", "seed"}


def test_stats_values():
    cu = CUSketch(width=1024, depth=4, seed=3)
    for i in range(20):
        cu.add(f"k{i}")
    s = cu.stats()
    assert s["width"] == 1024 and s["depth"] == 4 and s["total"] == 20
    assert s["num_counters"] == 4096 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    cu = CUSketch(width=512, depth=4, seed=0)
    for i in range(100):
        cu.add(f"k{i}")
    cu.reset()
    assert cu.total == 0 and cu.estimate("k0") == 0


def test_reset_reconfigures():
    cu = CUSketch(width=512, depth=4, seed=0)
    cu.reset(width=2048, depth=6, seed=9)
    assert cu.width == 2048 and cu.depth == 6 and cu.seed == 9


def test_reset_invalid_raises():
    cu = CUSketch(width=512, seed=0)
    with pytest.raises(CUSketchError):
        cu.reset(width=0)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    cu = CUSketch(width=8192, depth=4, seed=0)
    errors = []

    def worker(base):
        try:
            for i in range(200):
                cu.add(f"t{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert cu.total == 2000
    # every distinct key was added once ⇒ never-undercount holds
    assert all(cu.estimate(f"t{b}-{i}") >= 1 for b in range(10) for i in range(0, 200, 20))
