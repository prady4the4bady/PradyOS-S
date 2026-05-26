"""Phase 15C — SovereignScheduler unit tests (20 tests).

Covers:
  1.  add_job() returns dict with all required keys
  2.  next_run is a float > 0
  3.  get_jobs() returns list
  4.  remove_job() returns True for existing job
  5.  remove_job() returns False for missing job
  6.  enable_job() / disable_job() toggle enabled flag
  7.  tick() fires job when next_run <= now (mock clock)
  8.  tick() does NOT fire disabled jobs
  9.  tick() updates next_run after firing
 10.  tick() publishes "scheduler.job.fired" bus event
 11.  tick() returns list of fired job_ids
 12.  tick() fires multiple jobs in one call
 13.  start() / stop() are idempotent (no crash on double-stop)
 14.  get_jobs() returns a copy (mutation doesn't affect scheduler state)
 15.  add_job() with priority stores correct priority
 16.  add_job() with sla_seconds stores correct sla_seconds
 17.  cron */5 fires every 5 minutes (unit test next_run_after)
 18.  cron 0 * * * * fires at top of hour
 19.  cron 30 9 * * * fires at 09:30 daily
 20.  job_id collision: add_job with same id overwrites existing job
"""

from __future__ import annotations

import datetime
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from pradyos.sovereign.scheduler import SovereignScheduler, next_run_after
from pradyos.core.bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "job_id", "cron_expr", "campaign_spec", "priority",
    "sla_seconds", "next_run", "enabled",
}

_SIMPLE_CRON = "* * * * *"   # every minute
_SIMPLE_SPEC = {"name": "smoke-test"}


def _make_scheduler(
    clock=None,
    bus: EventBus | None = None,
) -> SovereignScheduler:
    """Build a SovereignScheduler with a mock CampaignEngine and isolated bus."""
    engine = MagicMock()
    if bus is None:
        bus = EventBus()
    return SovereignScheduler(campaign_engine=engine, bus=bus, clock=clock)


def _fixed_clock(ts: float):
    """Return a clock callable that always returns ts."""
    return lambda: ts


# ---------------------------------------------------------------------------
# Test 1: add_job() returns dict with all required keys
# ---------------------------------------------------------------------------

def test_add_job_returns_dict_with_required_keys():
    sched = _make_scheduler()
    job = sched.add_job("j1", _SIMPLE_CRON, _SIMPLE_SPEC)
    assert isinstance(job, dict)
    assert _REQUIRED_KEYS.issubset(job.keys()), f"Missing keys: {_REQUIRED_KEYS - job.keys()}"


# ---------------------------------------------------------------------------
# Test 2: next_run is a float > 0
# ---------------------------------------------------------------------------

def test_add_job_next_run_is_positive_float():
    sched = _make_scheduler()
    job = sched.add_job("j2", _SIMPLE_CRON, _SIMPLE_SPEC)
    assert isinstance(job["next_run"], float)
    assert job["next_run"] > 0


# ---------------------------------------------------------------------------
# Test 3: get_jobs() returns list
# ---------------------------------------------------------------------------

def test_get_jobs_returns_list():
    sched = _make_scheduler()
    result = sched.get_jobs()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Test 4: remove_job() returns True for existing job
# ---------------------------------------------------------------------------

def test_remove_job_returns_true_for_existing():
    sched = _make_scheduler()
    sched.add_job("j4", _SIMPLE_CRON, _SIMPLE_SPEC)
    assert sched.remove_job("j4") is True


# ---------------------------------------------------------------------------
# Test 5: remove_job() returns False for missing job
# ---------------------------------------------------------------------------

def test_remove_job_returns_false_for_missing():
    sched = _make_scheduler()
    assert sched.remove_job("nonexistent") is False


# ---------------------------------------------------------------------------
# Test 6: enable_job() / disable_job() toggle enabled flag
# ---------------------------------------------------------------------------

def test_enable_disable_job_toggles_enabled():
    sched = _make_scheduler()
    sched.add_job("j6", _SIMPLE_CRON, _SIMPLE_SPEC)
    sched.disable_job("j6")
    jobs = {j["job_id"]: j for j in sched.get_jobs()}
    assert jobs["j6"]["enabled"] is False

    sched.enable_job("j6")
    jobs = {j["job_id"]: j for j in sched.get_jobs()}
    assert jobs["j6"]["enabled"] is True


# ---------------------------------------------------------------------------
# Test 7: tick() fires job when next_run <= now (mock clock)
# ---------------------------------------------------------------------------

def test_tick_fires_job_when_next_run_lte_now():
    # Set clock far in the future so next_run is definitely in the past
    far_future = time.time() + 86400 * 365 * 10  # 10 years ahead
    # Add a job using a clock set to the far future so next_run is in the past
    # relative to the tick clock
    sched = _make_scheduler(clock=_fixed_clock(far_future))
    sched.add_job("j7", _SIMPLE_CRON, _SIMPLE_SPEC)
    # Manually set next_run to a timestamp well before "now"
    sched._jobs["j7"]["next_run"] = far_future - 1000
    fired = sched.tick()
    assert "j7" in fired


# ---------------------------------------------------------------------------
# Test 8: tick() does NOT fire disabled jobs
# ---------------------------------------------------------------------------

def test_tick_does_not_fire_disabled_jobs():
    far_future = time.time() + 86400 * 365 * 10
    sched = _make_scheduler(clock=_fixed_clock(far_future))
    sched.add_job("j8", _SIMPLE_CRON, _SIMPLE_SPEC)
    sched._jobs["j8"]["next_run"] = far_future - 1000
    sched.disable_job("j8")
    fired = sched.tick()
    assert "j8" not in fired


# ---------------------------------------------------------------------------
# Test 9: tick() updates next_run after firing
# ---------------------------------------------------------------------------

def test_tick_updates_next_run_after_firing():
    far_future = time.time() + 86400 * 365 * 10
    sched = _make_scheduler(clock=_fixed_clock(far_future))
    sched.add_job("j9", _SIMPLE_CRON, _SIMPLE_SPEC)
    # Force next_run into the past so tick() fires it
    trigger_ts = far_future - 1000
    sched._jobs["j9"]["next_run"] = trigger_ts
    sched.tick()
    new_next_run = sched._jobs["j9"]["next_run"]
    # After firing, next_run must advance past the trigger point
    assert new_next_run > trigger_ts


# ---------------------------------------------------------------------------
# Test 10: tick() publishes "scheduler.job.fired" bus event
# ---------------------------------------------------------------------------

def test_tick_publishes_scheduler_job_fired_event():
    far_future = time.time() + 86400 * 365 * 10
    bus = EventBus()
    received: list[dict] = []

    def _capture(topic, payload):
        received.append({"topic": topic, "payload": payload})

    bus.subscribe("scheduler.job.fired", _capture)
    sched = _make_scheduler(clock=_fixed_clock(far_future), bus=bus)
    sched.add_job("j10", _SIMPLE_CRON, _SIMPLE_SPEC)
    sched._jobs["j10"]["next_run"] = far_future - 1000
    sched.tick()

    assert len(received) == 1
    assert received[0]["topic"] == "scheduler.job.fired"


# ---------------------------------------------------------------------------
# Test 11: tick() returns list of fired job_ids
# ---------------------------------------------------------------------------

def test_tick_returns_list_of_fired_job_ids():
    far_future = time.time() + 86400 * 365 * 10
    sched = _make_scheduler(clock=_fixed_clock(far_future))
    sched.add_job("j11", _SIMPLE_CRON, _SIMPLE_SPEC)
    sched._jobs["j11"]["next_run"] = far_future - 500
    result = sched.tick()
    assert isinstance(result, list)
    assert "j11" in result


# ---------------------------------------------------------------------------
# Test 12: tick() fires multiple jobs in one call
# ---------------------------------------------------------------------------

def test_tick_fires_multiple_jobs():
    far_future = time.time() + 86400 * 365 * 10
    sched = _make_scheduler(clock=_fixed_clock(far_future))
    for jid in ["jA", "jB", "jC"]:
        sched.add_job(jid, _SIMPLE_CRON, {"name": jid})
        sched._jobs[jid]["next_run"] = far_future - 100
    fired = sched.tick()
    assert set(fired) == {"jA", "jB", "jC"}


# ---------------------------------------------------------------------------
# Test 13: start() / stop() are idempotent (no crash on double-stop)
# ---------------------------------------------------------------------------

def test_start_stop_idempotent():
    sched = _make_scheduler()
    sched.start(interval_seconds=10.0)
    sched.start(interval_seconds=10.0)  # double start — no-op
    sched.stop()
    sched.stop()  # double stop — must not raise


# ---------------------------------------------------------------------------
# Test 14: get_jobs() returns a copy (mutation doesn't affect scheduler)
# ---------------------------------------------------------------------------

def test_get_jobs_returns_copy():
    sched = _make_scheduler()
    sched.add_job("j14", _SIMPLE_CRON, _SIMPLE_SPEC)
    jobs = sched.get_jobs()
    assert len(jobs) == 1
    # Mutate the returned copy
    jobs[0]["priority"] = 99999
    # Internal state must be unchanged
    internal = sched._jobs["j14"]
    assert internal["priority"] != 99999


# ---------------------------------------------------------------------------
# Test 15: add_job() with priority stores correct priority
# ---------------------------------------------------------------------------

def test_add_job_stores_priority():
    sched = _make_scheduler()
    job = sched.add_job("j15", _SIMPLE_CRON, _SIMPLE_SPEC, priority=3)
    assert job["priority"] == 3
    assert sched._jobs["j15"]["priority"] == 3


# ---------------------------------------------------------------------------
# Test 16: add_job() with sla_seconds stores correct sla_seconds
# ---------------------------------------------------------------------------

def test_add_job_stores_sla_seconds():
    sched = _make_scheduler()
    job = sched.add_job("j16", _SIMPLE_CRON, _SIMPLE_SPEC, sla_seconds=120.0)
    assert job["sla_seconds"] == 120.0
    assert sched._jobs["j16"]["sla_seconds"] == 120.0


# ---------------------------------------------------------------------------
# Test 17: cron */5 fires every 5 minutes (unit test next_run_after)
# ---------------------------------------------------------------------------

def test_cron_every_5_minutes():
    # Pick a known base time: 2024-01-01 00:00:00 UTC (unix 1704067200)
    base = 1704067200.0  # 2024-01-01 00:00 UTC exactly
    # Because next_run_after advances to the NEXT minute if on an exact boundary,
    # use base - 1 so we start just before :00
    nxt = next_run_after("*/5 * * * *", base - 1)
    dt = datetime.datetime.utcfromtimestamp(nxt)
    assert dt.minute % 5 == 0

    # Verify the gap to the one after that is exactly 5 minutes
    nxt2 = next_run_after("*/5 * * * *", nxt + 1)
    assert abs((nxt2 - nxt) - 300) < 60  # within 1 minute of 300s


# ---------------------------------------------------------------------------
# Test 18: cron 0 * * * * fires at top of hour
# ---------------------------------------------------------------------------

def test_cron_top_of_hour():
    # 2024-01-01 00:30:00 UTC
    base = 1704069000.0
    nxt = next_run_after("0 * * * *", base)
    dt = datetime.datetime.utcfromtimestamp(nxt)
    assert dt.minute == 0


# ---------------------------------------------------------------------------
# Test 19: cron 30 9 * * * fires at 09:30 daily
# ---------------------------------------------------------------------------

def test_cron_daily_at_0930():
    # 2024-01-01 08:00:00 UTC
    base = 1704067200.0 + 8 * 3600  # 08:00 UTC
    nxt = next_run_after("30 9 * * *", base)
    dt = datetime.datetime.utcfromtimestamp(nxt)
    assert dt.hour == 9
    assert dt.minute == 30


# ---------------------------------------------------------------------------
# Test 20: job_id collision — add_job with same id overwrites existing job
# ---------------------------------------------------------------------------

def test_add_job_collision_overwrites():
    sched = _make_scheduler()
    sched.add_job("jX", _SIMPLE_CRON, {"name": "first"}, priority=1)
    sched.add_job("jX", "0 * * * *", {"name": "second"}, priority=9)
    jobs = {j["job_id"]: j for j in sched.get_jobs()}
    assert len(jobs) == 1
    assert jobs["jX"]["campaign_spec"]["name"] == "second"
    assert jobs["jX"]["priority"] == 9
    assert jobs["jX"]["cron_expr"] == "0 * * * *"
