"""Phase 40C — 20 tests for pradyos.core.control_plane.ControlPlane."""
from __future__ import annotations

import time

import pytest

from pradyos.core.control_plane import VERSION, ControlPlane
from pradyos.core.health_scorecard import HealthScorecard
from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.scheduler import TaskScheduler
from pradyos.core.memory_store import MemoryStore
from pradyos.core.healing_monitor import HealingMonitor
from pradyos.core.snapshot_store import SnapshotStore
from pradyos.core.reactor import ReactorEngine
from pradyos.core.state_manager import StateManager
from pradyos.core.watchpoint import WatchpointSystem
from pradyos.core.correlation_engine import CorrelationEngine
from pradyos.core.integration_bus import SovereignBus


EXPECTED_MODULES = {
    "health_scorecard", "signal_aggregator", "task_scheduler",
    "memory_store", "healing_monitor", "snapshot_store",
    "reactor_engine", "state_manager", "watchpoint_system",
    "correlation_engine", "integration_bus",
}


# ── init / uptime ─────────────────────────────────────────────────────────────

def test_init_all_none():
    cp = ControlPlane()
    assert cp._modules == {
        "health_scorecard": None, "signal_aggregator": None,
        "task_scheduler": None, "memory_store": None,
        "healing_monitor": None, "snapshot_store": None,
        "reactor_engine": None, "state_manager": None,
        "watchpoint_system": None, "correlation_engine": None,
        "integration_bus": None,
    }


def test_uptime_positive_immediately():
    cp = ControlPlane()
    time.sleep(0.001)
    assert cp.uptime() > 0


# ── status ────────────────────────────────────────────────────────────────────

def test_status_os_version_is_0_40_0():
    cp = ControlPlane()
    assert cp.status()["os_version"] == "0.40.0"
    assert VERSION == "0.40.0"


def test_status_uptime_seconds_positive():
    cp = ControlPlane()
    time.sleep(0.001)
    assert cp.status()["uptime_seconds"] > 0


def test_status_has_modules_key():
    cp = ControlPlane()
    assert "modules" in cp.status()


def test_status_modules_has_all_11_keys():
    cp = ControlPlane()
    mods = cp.status()["modules"]
    assert set(mods.keys()) == EXPECTED_MODULES


def test_status_module_present_false_when_not_passed():
    cp = ControlPlane()
    for name in EXPECTED_MODULES:
        assert cp.status()["modules"][name]["present"] is False


def test_status_module_present_true_when_passed():
    cp = ControlPlane(memory_store=MemoryStore())
    assert cp.status()["modules"]["memory_store"]["present"] is True


def test_status_summary_empty_when_not_present():
    cp = ControlPlane()
    for name in EXPECTED_MODULES:
        assert cp.status()["modules"][name]["summary"] == {}


def test_status_summary_dict_when_present_and_introspectable():
    cp = ControlPlane(task_scheduler=TaskScheduler())
    summary = cp.status()["modules"]["task_scheduler"]["summary"]
    assert isinstance(summary, dict)
    assert summary != {}


# ── _safe_summary ─────────────────────────────────────────────────────────────

def test_safe_summary_none_module_returns_empty():
    cp = ControlPlane()
    assert cp._safe_summary(None, "anything") == {}


def test_safe_summary_returns_dict_when_method_works():
    cp = ControlPlane()
    ts = TaskScheduler()
    result = cp._safe_summary(ts, "count")
    assert isinstance(result, dict)
    assert "tasks" in result


def test_safe_summary_returns_error_when_method_raises():
    class Bad:
        def broken(self):
            raise RuntimeError("kaboom")

    cp = ControlPlane()
    result = cp._safe_summary(Bad(), "broken")
    assert "error" in result
    assert "kaboom" in result["error"]


# ── tick ──────────────────────────────────────────────────────────────────────

def test_tick_returns_dict_with_required_keys():
    cp = ControlPlane()
    t = cp.tick()
    for key in ("ticks", "healed", "reactions"):
        assert key in t


def test_tick_empty_lists_when_no_modules():
    cp = ControlPlane()
    t = cp.tick()
    assert t["ticks"] == []
    assert t["healed"] == []
    assert t["reactions"] == []


def test_tick_ticks_scheduler_when_present():
    ts = TaskScheduler()
    ts.register("hb", 0.001, lambda: None)
    cp = ControlPlane(task_scheduler=ts)
    # Force task due by shifting next_run_at
    ts._tasks["hb"].next_run_at = time.time() - 10
    t = cp.tick()
    assert len(t["ticks"]) == 1


def test_tick_heals_when_healing_monitor_present():
    hs = HealthScorecard()
    hs.update("svc", 10.0)
    hm = HealingMonitor(health_scorecard=hs)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=lambda: None)
    cp = ControlPlane(healing_monitor=hm)
    t = cp.tick()
    assert len(t["healed"]) == 1


def test_tick_swallows_exceptions():
    class BrokenReactor:
        def react(self, _entry):
            raise RuntimeError("boom")

    cp = ControlPlane(reactor_engine=BrokenReactor())
    t = cp.tick()
    assert t["reactions"] == []


def test_tick_reactions_is_list_when_reactor_present():
    re = ReactorEngine()
    cp = ControlPlane(reactor_engine=re)
    t = cp.tick()
    assert isinstance(t["reactions"], list)


# ── real-modules integration ──────────────────────────────────────────────────

def test_real_modules_task_scheduler_summary_uses_count():
    ts = TaskScheduler()
    ts.register("hb", 1.0, lambda: None)
    cp = ControlPlane(task_scheduler=ts)
    summary = cp.status()["modules"]["task_scheduler"]["summary"]
    assert isinstance(summary, dict)
    assert summary["tasks"] == 1
