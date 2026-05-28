"""Phase 41C — 20 tests for pradyos.core.heartbeat.HeartbeatLoop.

Uses pytest-asyncio (configured to auto mode in pyproject.toml).
"""
from __future__ import annotations

import asyncio

import pytest

from pradyos.core.heartbeat import HeartbeatConfig, HeartbeatLoop


# ── HeartbeatConfig ───────────────────────────────────────────────────────────

def test_config_defaults():
    c = HeartbeatConfig()
    assert c.interval_seconds == 5.0
    assert c.max_ticks is None


def test_config_to_dict_keys():
    c = HeartbeatConfig(interval_seconds=2.5, max_ticks=10)
    d = c.to_dict()
    assert d == {"interval_seconds": 2.5, "max_ticks": 10}


def test_config_interval_seconds_stored():
    c = HeartbeatConfig(interval_seconds=7.5)
    assert c.interval_seconds == 7.5


def test_config_max_ticks_stored():
    c = HeartbeatConfig(max_ticks=42)
    assert c.max_ticks == 42


# ── HeartbeatLoop init / status ───────────────────────────────────────────────

def test_init_not_running():
    hb = HeartbeatLoop()
    assert hb._running is False
    assert hb._tick_count == 0


def test_status_running_false_initially():
    hb = HeartbeatLoop()
    assert hb.status()["running"] is False


def test_status_has_required_keys():
    hb = HeartbeatLoop()
    s = hb.status()
    for k in ("running", "tick_count", "interval_seconds"):
        assert k in s


def test_status_tick_count_zero_initially():
    hb = HeartbeatLoop()
    assert hb.status()["tick_count"] == 0


# ── async lifecycle ───────────────────────────────────────────────────────────

async def test_start_sets_running_true():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.001, max_ticks=1))
    await hb.start()
    assert hb._running is True
    # Wait for natural completion
    if hb._task is not None:
        await hb._task


async def test_stop_sets_running_false():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.01, max_ticks=None))
    await hb.start()
    await asyncio.sleep(0.005)
    await hb.stop()
    assert hb.status()["running"] is False


async def test_cannot_be_double_started():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.01, max_ticks=None))
    await hb.start()
    first_task = hb._task
    await hb.start()  # should be no-op
    assert hb._task is first_task
    await hb.stop()


async def test_max_ticks_runs_exactly_n_times():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.001, max_ticks=3))
    await hb.start()
    await hb._task
    assert hb._tick_count == 3


async def test_max_ticks_1_stops_after_one_tick():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.001, max_ticks=1))
    await hb.start()
    await hb._task
    assert hb._tick_count == 1
    assert hb._running is False


async def test_max_ticks_5_completes():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.001, max_ticks=5))
    await hb.start()
    await hb._task
    assert hb._tick_count == 5


# ── control_plane interaction ─────────────────────────────────────────────────

class _StubCP:
    def __init__(self):
        self.tick_called = 0

    def tick(self):
        self.tick_called += 1
        return {"ticks": [], "healed": [], "reactions": []}


async def test_tick_called_each_loop():
    cp = _StubCP()
    hb = HeartbeatLoop(control_plane=cp,
                       config=HeartbeatConfig(interval_seconds=0.001, max_ticks=3))
    await hb.start()
    await hb._task
    assert cp.tick_called == 3


async def test_tick_count_increments_per_tick():
    cp = _StubCP()
    hb = HeartbeatLoop(control_plane=cp,
                       config=HeartbeatConfig(interval_seconds=0.001, max_ticks=4))
    await hb.start()
    await hb._task
    assert hb._tick_count == 4


async def test_no_control_plane_no_error():
    hb = HeartbeatLoop(control_plane=None,
                       config=HeartbeatConfig(interval_seconds=0.001, max_ticks=2))
    await hb.start()
    await hb._task
    assert hb._tick_count == 2


async def test_swallows_control_plane_exceptions():
    class BadCP:
        def tick(self):
            raise RuntimeError("boom")

    hb = HeartbeatLoop(control_plane=BadCP(),
                       config=HeartbeatConfig(interval_seconds=0.001, max_ticks=2))
    await hb.start()
    await hb._task  # should not raise
    assert hb._tick_count == 2


async def test_status_tick_count_after_n_ticks():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.001, max_ticks=4))
    await hb.start()
    await hb._task
    assert hb.status()["tick_count"] == 4


async def test_tick_count_does_not_reset_on_stop():
    cp = _StubCP()
    hb = HeartbeatLoop(control_plane=cp,
                       config=HeartbeatConfig(interval_seconds=0.001, max_ticks=3))
    await hb.start()
    await hb._task
    await hb.stop()
    assert hb._tick_count == 3
