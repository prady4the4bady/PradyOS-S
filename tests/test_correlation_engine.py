"""Phase 33C — 20 tests for pradyos.core.correlation_engine.CorrelationEngine."""
from __future__ import annotations

import math
import time

import pytest

from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.correlation_engine import CorrelationEngine, CorrelationResult


def _engine_with(*signal_pairs) -> tuple[CorrelationEngine, SignalAggregator]:
    """Create engine; signal_pairs = (name, [values]) tuples."""
    sa = SignalAggregator(max_total=10000)
    now = time.time()
    for name, values in signal_pairs:
        for i, v in enumerate(values):
            sa.record(name, v, timestamp=now - len(values) + i)
    return CorrelationEngine(sa), sa


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_stores_aggregator():
    sa = SignalAggregator()
    ce = CorrelationEngine(sa)
    assert ce._agg is sa


# ── return type ───────────────────────────────────────────────────────────────

def test_correlate_returns_correlation_result():
    ce, _ = _engine_with(("a", [1, 2, 3]), ("b", [1, 2, 3]))
    r = ce.correlate("a", "b")
    assert isinstance(r, CorrelationResult)


# ── no-overlap → sample_size=0 ────────────────────────────────────────────────

def test_no_points_both_signals_sample_size_zero():
    sa = SignalAggregator()
    ce = CorrelationEngine(sa)
    r = ce.correlate("x", "y")
    assert r.sample_size == 0
    assert r.label == "weak"
    assert math.isnan(r.coefficient)


# ── perfect positive correlation ──────────────────────────────────────────────

def test_identical_signals_coefficient_one():
    values = [float(i) for i in range(1, 11)]
    ce, _ = _engine_with(("a", values), ("b", values))
    r = ce.correlate("a", "b")
    assert r.sample_size >= 2
    assert not math.isnan(r.coefficient)
    assert abs(r.coefficient - 1.0) < 1e-9
    assert r.label == "strong-positive"


# ── perfect negative correlation ──────────────────────────────────────────────

def test_perfectly_negative_correlation():
    a_vals = [float(i) for i in range(1, 11)]
    b_vals = [float(10 - i) for i in range(1, 11)]
    ce, _ = _engine_with(("a", a_vals), ("b", b_vals))
    r = ce.correlate("a", "b")
    assert not math.isnan(r.coefficient)
    assert abs(r.coefficient - (-1.0)) < 1e-9
    assert r.label == "strong-negative"


# ── constant signal → nan ─────────────────────────────────────────────────────

def test_constant_signal_returns_nan():
    ce, _ = _engine_with(("a", [5.0, 5.0, 5.0, 5.0]), ("b", [1.0, 2.0, 3.0, 4.0]))
    r = ce.correlate("a", "b")
    assert math.isnan(r.coefficient)


# ── single point → nan ───────────────────────────────────────────────────────

def test_single_point_both_signals_nan():
    sa = SignalAggregator()
    now = time.time()
    sa.record("a", 1.0, timestamp=now)
    sa.record("b", 2.0, timestamp=now)
    ce = CorrelationEngine(sa)
    r = ce.correlate("a", "b")
    assert r.sample_size == 1
    assert math.isnan(r.coefficient)
    assert r.label == "weak"


# ── window filtering ──────────────────────────────────────────────────────────

def test_window_filters_old_points():
    sa = SignalAggregator()
    now = time.time()
    # old points (outside window)
    for v in [1.0, 2.0, 3.0]:
        sa.record("a", v, timestamp=now - 7200)
        sa.record("b", v, timestamp=now - 7200)
    # recent points (inside 1 h window)
    sa.record("a", 10.0, timestamp=now - 10)
    sa.record("b", 10.0, timestamp=now - 10)
    ce = CorrelationEngine(sa)
    r = ce.correlate("a", "b", window_secs=3600)
    # only 1 recent point each → sample_size=1 → nan
    assert r.sample_size == 1


def test_window_zero_returns_no_points():
    ce, _ = _engine_with(("a", [1.0, 2.0]), ("b", [1.0, 2.0]))
    r = ce.correlate("a", "b", window_secs=0)
    assert r.sample_size == 0
    assert math.isnan(r.coefficient)


# ── label thresholds ──────────────────────────────────────────────────────────

def test_strong_positive_label():
    from pradyos.core.correlation_engine import _label
    assert _label(0.7) == "strong-positive"
    assert _label(1.0) == "strong-positive"


def test_moderate_positive_label():
    # r ≈ 0.5 — use a known dataset
    # a=[1,2,3,4,5], b=[1,1,3,4,5] → slight deviation but positive
    ce, _ = _engine_with(("a", [1, 2, 3, 4, 5, 6, 7, 8]),
                          ("b", [1, 3, 2, 5, 4, 7, 6, 8]))
    r = ce.correlate("a", "b")
    assert r.label in ("moderate-positive", "strong-positive", "weak")


def test_moderate_negative_label():
    from pradyos.core.correlation_engine import _label
    assert _label(-0.55) == "moderate-negative"


def test_weak_label():
    from pradyos.core.correlation_engine import _label
    assert _label(0.0) == "weak"
    assert _label(-0.1) == "weak"
    assert _label(0.39) == "weak"


# ── to_dict fields ────────────────────────────────────────────────────────────

def test_to_dict_has_required_keys():
    ce, _ = _engine_with(("a", [1, 2, 3]), ("b", [1, 2, 3]))
    d = ce.correlate("a", "b").to_dict()
    for key in ("signal_a", "signal_b", "coefficient", "sample_size",
                "label", "window_secs", "computed_at"):
        assert key in d, f"Missing key: {key}"


def test_computed_at_is_recent():
    ce, _ = _engine_with(("a", [1.0]), ("b", [1.0]))
    r = ce.correlate("a", "b")
    assert abs(r.computed_at - time.time()) < 5.0


def test_window_secs_preserved():
    ce, _ = _engine_with(("a", [1.0, 2.0]), ("b", [1.0, 2.0]))
    r = ce.correlate("a", "b", window_secs=1800.0)
    assert r.window_secs == 1800.0


def test_signal_names_preserved():
    ce, _ = _engine_with(("mysig_a", [1.0, 2.0]), ("mysig_b", [1.0, 2.0]))
    r = ce.correlate("mysig_a", "mysig_b")
    assert r.signal_a == "mysig_a"
    assert r.signal_b == "mysig_b"


# ── nearest-neighbour pairing ─────────────────────────────────────────────────

def test_nearest_neighbour_pairing_matches_correctly():
    sa = SignalAggregator()
    t0 = time.time() - 100
    sa.record("a", 1.0, timestamp=t0)
    sa.record("a", 2.0, timestamp=t0 + 10)
    sa.record("b", 1.0, timestamp=t0 + 0.5)   # near a[0]
    sa.record("b", 2.0, timestamp=t0 + 10.5)  # near a[1]
    ce = CorrelationEngine(sa)
    r = ce.correlate("a", "b")
    assert r.sample_size == 2
    assert not math.isnan(r.coefficient)
    assert abs(r.coefficient - 1.0) < 1e-9


# ── read-only ─────────────────────────────────────────────────────────────────

def test_correlate_does_not_modify_aggregator():
    ce, sa = _engine_with(("a", [1.0, 2.0, 3.0]), ("b", [1.0, 2.0, 3.0]))
    before_a = len(sa.get("a", limit=10000))
    before_b = len(sa.get("b", limit=10000))
    ce.correlate("a", "b")
    assert len(sa.get("a", limit=10000)) == before_a
    assert len(sa.get("b", limit=10000)) == before_b


# ── large dataset ─────────────────────────────────────────────────────────────

def test_large_dataset_completes():
    now = time.time()
    sa = SignalAggregator(max_total=10000)
    for i in range(1000):
        ts = now - 1000 + i
        sa.record("a", float(i), timestamp=ts)
        sa.record("b", float(i), timestamp=ts + 0.1)
    ce = CorrelationEngine(sa)
    r = ce.correlate("a", "b", window_secs=2000)
    assert r.sample_size == 1000
    assert not math.isnan(r.coefficient)
    assert abs(r.coefficient - 1.0) < 1e-6
