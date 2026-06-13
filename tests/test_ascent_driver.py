"""Tests for the ASCENT driver — the autonomous self-survey heartbeat."""

from __future__ import annotations

import asyncio

from pradyos.ascent import AscentDriver, AscentLoop, OwnModuleSource

WEAK = "def f(x=[]):\n    try:\n        g()\n    except:\n        pass\n"


class _FakeEvolve:
    def propose(self, path: str, directive: str, before: str = "") -> dict:
        return {
            "path": path,
            "directive": directive,
            "proposed": True,
            "after": "x = 1\n",
            "evaluation": {"verdict": "promote", "risk_before": 6, "risk_after": 1, "path": path},
            "note": "verdict=promote",
        }

    def stats(self) -> dict:
        return {"proposer_configured": True}


# ── OwnModuleSource ─────────────────────────────────────────────────────────────


def test_own_module_source_discovers_pradyos_modules():
    batch = OwnModuleSource(batch=4)()
    assert batch, "expected to discover the agent's own modules"
    assert len(batch) <= 4
    for path, source in batch.items():
        assert path.startswith("pradyos/") and path.endswith(".py")
        assert path != "pradyos/__init__.py"  # __init__ files are skipped
        assert isinstance(source, str) and source


def test_own_module_source_excludes_configured_subpackages():
    # Pull a large batch and confirm excluded sub-packages never appear.
    src = OwnModuleSource(batch=500)
    keys = list(src())
    assert keys  # discovered something
    for prefix in ("pradyos/web/", "pradyos/ascent/", "pradyos/aurora_throne/"):
        assert not any(k.startswith(prefix) for k in keys)


def test_own_module_source_rotates_cursor():
    src = OwnModuleSource(batch=2)
    if len(src._files) <= 2:
        return  # too few modules to demonstrate rotation
    first = set(src())
    second = set(src())
    assert first != second  # cursor advanced to a different window


# ── AscentDriver.tick ───────────────────────────────────────────────────────────


def test_tick_runs_cycle_and_counts():
    loop = AscentLoop(evolve=_FakeEvolve())
    drv = AscentDriver(loop, lambda: {"a.py": WEAK})
    cycles = drv.tick()
    assert len(cycles) == 1 and cycles[0]["decision"] == "apply"
    st = drv.status()
    assert st["ticks"] == 1 and st["last_cycles"] == 1
    assert loop.stats()["cycles"] == 1  # the driver shares the loop the API exposes


def test_tick_empty_source_is_safe():
    loop = AscentLoop(evolve=_FakeEvolve())
    drv = AscentDriver(loop, lambda: {})
    assert drv.tick() == []
    assert drv.status()["ticks"] == 1 and drv.status()["last_cycles"] == 0


def test_tick_uses_max_targets():
    loop = AscentLoop(evolve=_FakeEvolve())
    drv = AscentDriver(loop, lambda: {"a.py": WEAK, "b.py": WEAK}, max_targets=2)
    assert len(drv.tick()) == 2


def test_status_shape_before_start():
    drv = AscentDriver(AscentLoop(), lambda: {}, interval_s=42.0, max_targets=3)
    st = drv.status()
    assert st["running"] is False and st["ticks"] == 0
    assert st["interval_s"] == 42.0 and st["max_targets"] == 3


def test_interval_floor_is_enforced():
    # A sub-second interval is clamped so the heartbeat can't become a tight loop.
    assert AscentDriver(AscentLoop(), lambda: {}, interval_s=0.01).status()["interval_s"] == 1.0


# ── start / stop lifecycle ──────────────────────────────────────────────────────


def test_start_then_stop_lifecycle():
    loop = AscentLoop(evolve=_FakeEvolve())
    drv = AscentDriver(loop, lambda: {"a.py": WEAK}, interval_s=1.0)

    async def scenario():
        drv.start()
        running = drv.status()["running"]
        await drv.stop()
        return running

    running = asyncio.run(scenario())
    assert running is True
    assert drv.status()["running"] is False
