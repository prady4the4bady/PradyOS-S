"""Tests for the Frequency-Aware Attention sketch (Count-Sketch + exponential decay)."""

from __future__ import annotations

import threading

import pytest

from pradyos.core.attention_sketch import AttentionSketch, AttentionSketchError


def _a(**kw) -> AttentionSketch:
    return AttentionSketch(seed=0, **kw)


# ── construction / validation ─────────────────────────────────────────────────


def test_default_construction():
    s = _a().stats()
    assert s["total_tokens"] == 0 and s["decay_factor"] == 0.99 and s["unique_tracked"] == 0


def test_custom_construction():
    s = AttentionSketch(width=512, depth=3, decay_factor=0.9, sensitivity=0.05, seed=2).stats()
    assert s["count_sketch"]["width"] == 512 and s["decay_factor"] == 0.9 and s["sensitivity"] == 0.05


@pytest.mark.parametrize("bad", [0, -1, "x"])
def test_invalid_width(bad):
    with pytest.raises(AttentionSketchError):
        AttentionSketch(width=bad)


@pytest.mark.parametrize("bad", [0, -2])
def test_invalid_depth(bad):
    with pytest.raises(AttentionSketchError):
        AttentionSketch(depth=bad)


@pytest.mark.parametrize("bad", [0.0, -0.5, 1.5, 2])
def test_invalid_decay_factor(bad):
    with pytest.raises(AttentionSketchError):
        AttentionSketch(decay_factor=bad)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_invalid_sensitivity(bad):
    with pytest.raises(AttentionSketchError):
        AttentionSketch(sensitivity=bad)


def test_invalid_capacity():
    with pytest.raises(AttentionSketchError):
        AttentionSketch(capacity=0)


# ── attend / weight ───────────────────────────────────────────────────────────


def test_attend_requires_list():
    with pytest.raises(AttentionSketchError):
        _a().attend("not-a-list")


def test_attend_empty_list_is_noop():
    a = _a()
    a.attend([])
    assert a.stats()["total_tokens"] == 0


def test_heavy_token_has_high_weight():
    a = _a()
    a.attend(["agi"] * 1000 + ["noise"])
    assert a.weight("agi") > 0.5


def test_rare_token_has_low_weight():
    a = _a()
    a.attend(["agi"] * 1000 + ["rare"])
    assert a.weight("rare") < 0.05


def test_unseen_token_zero_weight():
    a = _a()
    a.attend(["a", "b"])
    assert a.weight("never_seen") == 0.0


def test_weight_in_unit_interval():
    a = _a()
    a.attend(["x"] * 500 + ["y"] * 5 + ["z"])
    for t in ("x", "y", "z", "missing"):
        assert 0.0 <= a.weight(t) <= 1.0


def test_attend_coerces_non_string():
    a = _a()
    a.attend([1, 1, 1])  # type: ignore[list-item]
    assert a.weight("1") > 0.0


def test_attend_counts_total():
    a = _a()
    a.attend(["a", "b", "c"])
    a.attend(["d"])
    assert a.stats()["total_tokens"] == 4


# ── top_concepts ───────────────────────────────────────────────────────────────


def test_top_concepts_orders_by_weight():
    a = _a()
    a.attend(["big"] * 100 + ["mid"] * 10 + ["small"] * 1)
    top = a.top_concepts(3)
    assert [t for t, _ in top] == ["big", "mid", "small"]


def test_top_concepts_respects_k():
    a = _a()
    a.attend([f"t{i}" for i in range(20)])
    assert len(a.top_concepts(5)) == 5


def test_top_concepts_validation():
    with pytest.raises(AttentionSketchError):
        _a().top_concepts(0)


def test_top_concepts_empty():
    assert _a().top_concepts(5) == []


def test_top_concepts_weights_descending():
    a = _a()
    a.attend(["a"] * 50 + ["b"] * 20 + ["c"] * 5)
    weights = [w for _, w in a.top_concepts(3)]
    assert weights == sorted(weights, reverse=True)


# ── decay ──────────────────────────────────────────────────────────────────────


def test_decay_decreases_weight():
    a = _a()
    a.attend(["x"] * 50)
    before = a.weight("x")
    a.decay()
    assert a.weight("x") < before


def test_repeated_decay_monotonic():
    a = _a()
    a.attend(["x"] * 50)
    w = a.weight("x")
    for _ in range(5):
        a.decay()
        nxt = a.weight("x")
        assert nxt < w
        w = nxt


def test_decay_counts_steps():
    a = _a()
    a.decay()
    a.decay()
    assert a.stats()["decay_steps"] == 2


def test_attend_after_decay_restores():
    a = _a()
    a.attend(["x"] * 10)
    for _ in range(5):
        a.decay()
    faded = a.weight("x")
    a.attend(["x"] * 100)
    assert a.weight("x") > faded


# ── determinism / thread safety / reset / stats ────────────────────────────────


def test_determinism_same_seed():
    a1, a2 = AttentionSketch(seed=9), AttentionSketch(seed=9)
    for a in (a1, a2):
        a.attend(["alpha", "beta", "alpha", "gamma", "alpha"])
    assert a1.top_concepts(3) == a2.top_concepts(3)
    assert a1.weight("alpha") == a2.weight("alpha")


def test_concurrent_attend_no_loss():
    a = AttentionSketch(capacity=100_000, seed=0)

    def worker(b):
        for i in range(200):
            a.attend([f"k{b}-{i}"])

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert a.stats()["total_tokens"] == 1600


def test_capacity_evicts_low_weight():
    a = AttentionSketch(capacity=5, seed=0)
    a.attend(["keep"] * 100)  # high weight
    a.attend([f"t{i}" for i in range(20)])  # many freq-1 tokens
    assert a.stats()["unique_tracked"] <= 5
    assert any(t == "keep" for t, _ in a.top_concepts(5))


def test_reset_clears():
    a = _a()
    a.attend(["x"] * 10)
    a.decay()
    a.reset()
    s = a.stats()
    assert s["total_tokens"] == 0 and s["unique_tracked"] == 0 and s["decay_steps"] == 0
    assert a.weight("x") == 0.0


def test_stats_shape():
    a = _a()
    a.attend(["a", "b"])
    s = a.stats()
    for k in ("total_tokens", "unique_tracked", "decay_steps", "scale", "count_sketch"):
        assert k in s
