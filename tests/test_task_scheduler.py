"""Phase 38C — 20 tests for pradyos.core.scheduler.TaskScheduler."""
from __future__ import annotations

import time

import pytest

from pradyos.core.scheduler import ScheduledTask, TaskRun, TaskScheduler


def _noop():
    pass


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    ts = TaskScheduler()
    assert ts._tasks == {}
    assert ts._fns == {}
    assert len(ts._log) == 0


# ── register ──────────────────────────────────────────────────────────────────

def test_register_returns_task():
    ts = TaskScheduler()
    task = ts.register("hb", 1.0, _noop)
    assert isinstance(task, ScheduledTask)


def test_register_sets_next_run_at_to_now_plus_interval():
    ts = TaskScheduler()
    before = time.time()
    task = ts.register("hb", 5.0, _noop)
    after = time.time()
    assert before + 5.0 <= task.next_run_at <= after + 5.0


def test_register_last_run_is_none():
    ts = TaskScheduler()
    task = ts.register("hb", 1.0, _noop)
    assert task.last_run is None


def test_register_overwrites_existing_task():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    ts.register("hb", 60.0, _noop)
    assert ts._tasks["hb"].interval_seconds == 60.0


# ── unregister ────────────────────────────────────────────────────────────────

def test_unregister_returns_true():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    assert ts.unregister("hb") is True


def test_unregister_returns_false_unknown():
    ts = TaskScheduler()
    assert ts.unregister("phantom") is False


def test_unregister_removes_from_both_dicts():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    ts.unregister("hb")
    assert "hb" not in ts._tasks
    assert "hb" not in ts._fns


# ── enable / disable ──────────────────────────────────────────────────────────

def test_enable_disable_return_true_when_found():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    assert ts.disable("hb") is True
    assert ts.enable("hb") is True
    assert ts.disable("nope") is False
    assert ts.enable("nope") is False


def test_disable_prevents_tick_from_running():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    ts.disable("hb")
    # force the task due
    runs = ts.tick(now=time.time() + 9999)
    assert runs == []


# ── list_tasks ────────────────────────────────────────────────────────────────

def test_list_tasks_sorted():
    ts = TaskScheduler()
    ts.register("zzz", 1.0, _noop)
    ts.register("aaa", 1.0, _noop)
    ts.register("mmm", 1.0, _noop)
    names = [t["name"] for t in ts.list_tasks()]
    assert names == ["aaa", "mmm", "zzz"]


def test_list_tasks_entries_have_required_keys():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    entry = ts.list_tasks()[0]
    for k in ("name", "interval_seconds", "next_run_at", "last_run", "enabled"):
        assert k in entry, f"Missing key: {k}"


# ── tick ──────────────────────────────────────────────────────────────────────

def test_tick_empty_when_no_tasks_due():
    ts = TaskScheduler()
    ts.register("hb", 60.0, _noop)
    runs = ts.tick()
    assert runs == []


def test_tick_fires_task_when_due():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    runs = ts.tick(now=time.time() + 9999)
    assert len(runs) == 1
    assert runs[0].task_name == "hb"


def test_tick_updates_last_run_and_next_run_at():
    ts = TaskScheduler()
    ts.register("hb", 5.0, _noop)
    now = time.time() + 9999
    ts.tick(now=now)
    task = ts._tasks["hb"]
    assert task.last_run == now
    assert task.next_run_at == now + 5.0


def test_tick_taskrun_success_true_for_normal_fn():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    run = ts.tick(now=time.time() + 9999)[0]
    assert run.success is True
    assert run.error is None


def test_tick_taskrun_success_false_for_exception():
    def bad():
        raise RuntimeError("boom")

    ts = TaskScheduler()
    ts.register("bad", 1.0, bad)
    run = ts.tick(now=time.time() + 9999)[0]
    assert run.success is False
    assert run.error == "boom"


def test_tick_appends_to_log():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    ts.tick(now=time.time() + 9999)
    ts.tick(now=time.time() + 19999)
    assert len(ts._log) == 2


# ── get_log / count ───────────────────────────────────────────────────────────

def test_get_log_returns_last_n():
    ts = TaskScheduler()
    ts.register("hb", 0.001, _noop)
    for i in range(5):
        ts.tick(now=time.time() + 9999 + i * 10)
    last3 = ts.get_log(limit=3)
    assert len(last3) == 3


def test_count_returns_tasks_and_runs():
    ts = TaskScheduler()
    ts.register("hb", 1.0, _noop)
    ts.register("db", 1.0, _noop)
    ts.tick(now=time.time() + 9999)
    c = ts.count()
    assert c == {"tasks": 2, "runs": 2}
