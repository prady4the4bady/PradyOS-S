"""Phase 68C — 20 tests for pradyos.core.job_scheduler.Scheduler."""
from __future__ import annotations

import time

import pytest

from pradyos.core.job_scheduler import Job, Scheduler


# ── init / schedule ──────────────────────────────────────────────────────────

def test_init_has_zero_count():
    s = Scheduler()
    assert s.count() == 0


def test_schedule_returns_job():
    s = Scheduler()
    job = s.schedule("ping", run_at=time.time())
    assert isinstance(job, Job)
    assert job.name == "ping"


def test_schedule_status_is_pending():
    s = Scheduler()
    job = s.schedule("ping", run_at=time.time())
    assert job.status == "pending"


def test_schedule_next_run_at_equals_run_at():
    s = Scheduler()
    t = time.time() + 60
    job = s.schedule("ping", run_at=t)
    assert job.next_run_at == t
    assert job.run_at == t


# ── get ─────────────────────────────────────────────────────────────────────

def test_get_returns_job():
    s = Scheduler()
    job = s.schedule("ping", run_at=time.time())
    assert s.get(job.job_id) is job


def test_get_unknown_returns_none():
    s = Scheduler()
    assert s.get("phantom") is None


# ── cancel ──────────────────────────────────────────────────────────────────

def test_cancel_pending_returns_true_and_sets_cancelled():
    s = Scheduler()
    job = s.schedule("ping", run_at=time.time() + 999)
    assert s.cancel(job.job_id) is True
    assert job.status == "cancelled"


def test_cancel_non_pending_returns_false():
    s = Scheduler()
    s.register_handler("ping", lambda p: {"ok": True})
    job = s.schedule("ping", run_at=time.time() - 1)
    s.tick()  # job is now completed
    assert s.cancel(job.job_id) is False


def test_cancel_unknown_returns_false():
    s = Scheduler()
    assert s.cancel("phantom") is False


# ── tick ────────────────────────────────────────────────────────────────────

def test_tick_executes_due_job_calls_handler():
    s = Scheduler()
    seen = []
    s.register_handler("ping", lambda p: (seen.append(p) or {"ok": True}))
    s.schedule("ping", run_at=time.time() - 1, payload={"x": 1})
    s.tick()
    assert seen == [{"x": 1}]


def test_tick_sets_status_completed_on_success():
    s = Scheduler()
    s.register_handler("ping", lambda p: {"ok": True})
    job = s.schedule("ping", run_at=time.time() - 1)
    s.tick()
    assert job.status == "completed"


def test_tick_sets_result_from_handler_return():
    s = Scheduler()
    s.register_handler("ping", lambda p: {"value": 42})
    job = s.schedule("ping", run_at=time.time() - 1)
    s.tick()
    assert job.result == {"value": 42}


def test_tick_sets_failed_on_exception():
    s = Scheduler()

    def boom(p):
        raise RuntimeError("kaboom")

    s.register_handler("ping", boom)
    job = s.schedule("ping", run_at=time.time() - 1)
    s.tick()
    assert job.status == "failed"


def test_tick_sets_error_string_on_exception():
    s = Scheduler()

    def boom(p):
        raise RuntimeError("specific message")

    s.register_handler("ping", boom)
    job = s.schedule("ping", run_at=time.time() - 1)
    s.tick()
    assert "specific message" in job.error


def test_tick_no_handler_sets_failed_with_message():
    s = Scheduler()
    job = s.schedule("missing", run_at=time.time() - 1)
    s.tick()
    assert job.status == "failed"
    assert job.error == "no handler registered"


# ── repeating jobs ──────────────────────────────────────────────────────────

def test_tick_repeating_job_reschedules_after_completion():
    s = Scheduler()
    s.register_handler("hb", lambda p: {"ok": True})
    job = s.schedule("hb", run_at=time.time() - 1, interval_seconds=60.0)
    s.tick()
    assert job.status == "pending"  # rescheduled


def test_tick_repeating_job_next_run_at_advanced_by_interval():
    s = Scheduler()
    s.register_handler("hb", lambda p: {"ok": True})
    job = s.schedule("hb", run_at=time.time() - 1, interval_seconds=60.0)
    now = time.time()
    s.tick(now=now)
    assert job.next_run_at == now + 60.0


# ── time filtering ──────────────────────────────────────────────────────────

def test_tick_future_job_not_executed():
    s = Scheduler()
    s.register_handler("ping", lambda p: {"ok": True})
    job = s.schedule("ping", run_at=time.time() + 999)
    executed = s.tick()
    assert executed == []
    assert job.status == "pending"


# ── list / count ────────────────────────────────────────────────────────────

def test_list_jobs_filter_by_status():
    s = Scheduler()
    s.register_handler("ok", lambda p: {"ok": True})
    s.register_handler("bad", lambda p: (_ for _ in ()).throw(RuntimeError("x")))
    s.schedule("ok", run_at=time.time() - 1)
    s.schedule("bad", run_at=time.time() - 1)
    pending = s.schedule("ok", run_at=time.time() + 999)
    s.tick()
    completed = s.list_jobs(status="completed")
    failed = s.list_jobs(status="failed")
    pending_only = s.list_jobs(status="pending")
    assert len(completed) == 1
    assert len(failed) == 1
    assert pending_only[0].job_id == pending.job_id


def test_count_by_status_correct():
    s = Scheduler()
    s.register_handler("ok", lambda p: {"ok": True})
    s.schedule("ok", run_at=time.time() - 1)
    s.schedule("ok", run_at=time.time() - 1)
    s.schedule("ok", run_at=time.time() + 999)  # stays pending
    s.tick()
    assert s.count() == 3
    assert s.count(status="completed") == 2
    assert s.count(status="pending") == 1
