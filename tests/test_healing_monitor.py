"""Phase 37C — 20 tests for pradyos.core.healing_monitor.HealingMonitor."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.healing_monitor import (
    HealingComponent,
    HealingEvent,
    HealingMonitor,
)
from pradyos.core.health_scorecard import HealthScorecard


# ── helpers ───────────────────────────────────────────────────────────────────

def _hs_with(name="svc", score=50.0) -> HealthScorecard:
    hs = HealthScorecard()
    hs.update(name, score)
    return hs


def _noop():
    pass


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    hm = HealingMonitor()
    assert hm._components == {}
    assert hm._repair_fns == {}
    assert len(hm._log) == 0


# ── register ──────────────────────────────────────────────────────────────────

def test_register_returns_component():
    hm = HealingMonitor()
    comp = hm.register("svc", threshold=50.0, action="restart", repair_fn=_noop)
    assert isinstance(comp, HealingComponent)


def test_register_stores_correct_fields():
    hm = HealingMonitor()
    hm.register("svc", threshold=50.0, action="restart", repair_fn=_noop)
    assert hm._components["svc"].threshold == 50.0
    assert hm._components["svc"].action == "restart"
    assert hm._repair_fns["svc"] is _noop


# ── unregister ────────────────────────────────────────────────────────────────

def test_unregister_returns_true():
    hm = HealingMonitor()
    hm.register("svc", 50.0, "restart", _noop)
    assert hm.unregister("svc") is True


def test_unregister_returns_false_unknown():
    hm = HealingMonitor()
    assert hm.unregister("phantom") is False


def test_unregister_removes_from_both_dicts():
    hm = HealingMonitor()
    hm.register("svc", 50.0, "restart", _noop)
    hm.unregister("svc")
    assert "svc" not in hm._components
    assert "svc" not in hm._repair_fns


# ── list_components ───────────────────────────────────────────────────────────

def test_list_components_sorted():
    hm = HealingMonitor()
    hm.register("zzz", 50.0, "restart", _noop)
    hm.register("aaa", 50.0, "restart", _noop)
    hm.register("mmm", 50.0, "restart", _noop)
    names = [c["name"] for c in hm.list_components()]
    assert names == ["aaa", "mmm", "zzz"]


def test_list_components_entries_have_keys():
    hm = HealingMonitor()
    hm.register("svc", 50.0, "restart", _noop)
    entry = hm.list_components()[0]
    for key in ("name", "threshold", "action"):
        assert key in entry


# ── check_and_heal ────────────────────────────────────────────────────────────

def test_check_and_heal_returns_empty_when_no_scorecard():
    hm = HealingMonitor()
    hm.register("svc", 50.0, "restart", _noop)
    assert hm.check_and_heal() == []


def test_check_and_heal_returns_empty_when_score_above_threshold():
    hs = _hs_with("svc", score=80.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=_noop)
    assert hm.check_and_heal() == []


def test_check_and_heal_fires_when_below_threshold():
    hs = _hs_with("svc", score=20.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=_noop)
    events = hm.check_and_heal()
    assert len(events) == 1


def test_check_and_heal_event_has_correct_fields():
    hs = _hs_with("svc", score=20.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=_noop)
    evt = hm.check_and_heal()[0]
    assert isinstance(evt, HealingEvent)
    assert evt.component == "svc"
    assert evt.action_taken == "restart"
    assert evt.score_before == 20.0
    assert evt.healed_at > 0


def test_check_and_heal_skips_unregistered_in_scorecard():
    hs = HealthScorecard()
    # do not update "svc" — score is None
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=_noop)
    assert hm.check_and_heal() == []


def test_check_and_heal_swallows_repair_fn_exceptions():
    def bad_repair():
        raise RuntimeError("boom")

    hs = _hs_with("svc", score=20.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", bad_repair)
    # should not raise
    events = hm.check_and_heal()
    assert len(events) == 1  # still records event despite exception


def test_check_and_heal_appends_to_log():
    hs = _hs_with("svc", score=20.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", _noop)
    hm.check_and_heal()
    assert len(hm._log) == 1


def test_check_and_heal_score_before_is_trigger_score():
    hs = _hs_with("svc", score=30.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", _noop)
    evt = hm.check_and_heal()[0]
    assert evt.score_before == 30.0


def test_repair_fn_is_called():
    called = {"yes": False}

    def repair():
        called["yes"] = True

    hs = _hs_with("svc", score=20.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", repair)
    hm.check_and_heal()
    assert called["yes"] is True


# ── get_log / count ───────────────────────────────────────────────────────────

def test_get_log_returns_last_n():
    hs = _hs_with("svc", score=10.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", _noop)
    for _ in range(5):
        hm.check_and_heal()
    last2 = hm.get_log(limit=2)
    assert len(last2) == 2


def test_count_returns_components_and_events():
    hs = _hs_with("svc", score=10.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", _noop)
    hm.register("db", 50.0, "restart", _noop)
    hm.check_and_heal()
    c = hm.count()
    assert c == {"components": 2, "events": 1}


# ── thread safety ─────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_check_and_heal():
    hs = _hs_with("svc", score=10.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", 50.0, "restart", _noop)
    errors: list[Exception] = []

    def worker():
        try:
            hm.check_and_heal()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(hm._log) == 20
