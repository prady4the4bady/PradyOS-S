"""Phase 31C — 20 tests for pradyos.core.signal_aggregator.SignalAggregator."""
from __future__ import annotations

import math
import threading
import time

import pytest

from pradyos.core.signal_aggregator import SignalAggregator, SignalPoint


# ── helpers ──────────────────────────────────────────────────────────────────

def _sa(**kw) -> SignalAggregator:
    return SignalAggregator(**kw)


# ── initialisation ────────────────────────────────────────────────────────────

def test_init_no_signals():
    sa = _sa()
    assert sa._signals == {}
    assert sa.list_signals() == []


# ── record ────────────────────────────────────────────────────────────────────

def test_record_returns_signal_point():
    sa = _sa()
    pt = sa.record("cpu", 42.0)
    assert isinstance(pt, SignalPoint)
    assert pt.value == 42.0


def test_record_creates_signal_on_first_record():
    sa = _sa()
    sa.record("mem", 80.0)
    assert "mem" in sa._signals


def test_record_appends_points():
    sa = _sa()
    sa.record("cpu", 10.0)
    sa.record("cpu", 20.0)
    sa.record("cpu", 30.0)
    pts = sa.get("cpu", limit=100)
    assert len(pts) == 3
    assert [p.value for p in pts] == [10.0, 20.0, 30.0]


# ── get ───────────────────────────────────────────────────────────────────────

def test_get_empty_for_unknown_signal():
    sa = _sa()
    assert sa.get("nope") == []


def test_get_returns_oldest_first():
    sa = _sa()
    for v in [1.0, 2.0, 3.0]:
        sa.record("x", v)
    pts = sa.get("x", limit=100)
    assert [p.value for p in pts] == [1.0, 2.0, 3.0]


def test_get_limit_returns_at_most_n():
    sa = _sa()
    for v in range(10):
        sa.record("x", float(v))
    pts = sa.get("x", limit=3)
    assert len(pts) == 3
    # last 3 values: 7, 8, 9
    assert [p.value for p in pts] == [7.0, 8.0, 9.0]


def test_get_all_when_limit_exceeds_count():
    sa = _sa()
    for v in range(5):
        sa.record("x", float(v))
    pts = sa.get("x", limit=999)
    assert len(pts) == 5


# ── list_signals ──────────────────────────────────────────────────────────────

def test_list_signals_sorted_by_name():
    sa = _sa()
    sa.record("zzz", 1.0)
    sa.record("aaa", 2.0)
    sa.record("mmm", 3.0)
    names = [s["name"] for s in sa.list_signals()]
    assert names == ["aaa", "mmm", "zzz"]


def test_list_signals_entry_has_required_keys():
    sa = _sa()
    sa.record("cpu", 50.0)
    entry = sa.list_signals()[0]
    assert "name" in entry
    assert "count" in entry
    assert "latest" in entry


def test_list_signals_latest_reflects_most_recent():
    sa = _sa()
    sa.record("cpu", 10.0)
    sa.record("cpu", 99.0)
    entry = sa.list_signals()[0]
    assert entry["latest"] == 99.0


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_none_for_unknown():
    sa = _sa()
    assert sa.stats("missing") is None


def test_stats_has_required_keys():
    sa = _sa()
    sa.record("s", 5.0)
    s = sa.stats("s")
    for key in ("name", "count", "min", "max", "mean", "stddev"):
        assert key in s, f"Missing key: {key}"


def test_stats_min_max_correct():
    sa = _sa()
    for v in [3.0, 1.0, 4.0, 1.0, 5.0]:
        sa.record("s", v)
    s = sa.stats("s")
    assert s["min"] == 1.0
    assert s["max"] == 5.0


def test_stats_mean_correct():
    sa = _sa()
    for v in [2.0, 4.0, 6.0]:
        sa.record("s", v)
    s = sa.stats("s")
    assert abs(s["mean"] - 4.0) < 1e-9


def test_stats_stddev_multiple_values():
    sa = _sa()
    # values: 2, 4, 4, 4, 5, 5, 7, 9 — population stddev = 2.0
    for v in [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]:
        sa.record("s", v)
    s = sa.stats("s")
    assert abs(s["stddev"] - 2.0) < 1e-6


def test_stats_stddev_single_point_is_zero():
    sa = _sa()
    sa.record("s", 42.0)
    s = sa.stats("s")
    assert s["stddev"] == 0.0


# ── custom timestamp ──────────────────────────────────────────────────────────

def test_custom_timestamp_preserved():
    sa = _sa()
    ts = 1_700_000_000.0
    pt = sa.record("t", 7.0, timestamp=ts)
    assert pt.recorded_at == ts


# ── thread safety ─────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_records():
    sa = _sa(max_total=10000)
    errors: list[Exception] = []

    def worker():
        try:
            sa.record("m", 1.0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    pts = sa.get("m", limit=10000)
    assert len(pts) == 50


# ── count consistency ─────────────────────────────────────────────────────────

def test_list_signals_count_matches_recorded():
    sa = _sa()
    for i in range(7):
        sa.record("q", float(i))
    entry = sa.list_signals()[0]
    assert entry["count"] == 7
