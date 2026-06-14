"""Tests for the ReverieDriver — the background cognition heartbeat."""

from __future__ import annotations

from pradyos.foresight import ForesightEngine
from pradyos.reverie import Reverie, ReverieDriver
from pradyos.skills import SkillLibrary


def _reverie() -> Reverie:
    return Reverie(foresight=ForesightEngine(), skills=SkillLibrary())


def test_tick_runs_a_reflection_and_records_goal():
    drv = ReverieDriver(_reverie(), interval_s=1)
    insight = drv.tick()
    assert "curiosity_goal" in insight
    st = drv.status()
    assert st["ticks"] == 1
    assert st["last_goal"] == insight["curiosity_goal"]
    assert st["running"] is False  # never started as a task


def test_repeated_ticks_accumulate():
    rev = _reverie()
    drv = ReverieDriver(rev, interval_s=1)
    drv.tick()
    drv.tick()
    assert drv.status()["ticks"] == 2
    assert len(rev.insights(99)) == 2


def test_interval_is_floored_to_one_second():
    drv = ReverieDriver(_reverie(), interval_s=0.0)
    assert drv.status()["interval_s"] >= 1.0
