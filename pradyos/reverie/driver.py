"""REVERIE driver — run the cognition loop on its own, in the background.

:class:`~pradyos.reverie.engine.Reverie` reflects when *asked* (an API call). This
driver makes the reflection **autonomous**: a background heartbeat that, on an
interval, has REVERIE reflect on the OS's own thinking (FORESIGHT calibration +
the skill library) and record an insight + curiosity goal. It is the cognition
counterpart to ASCENT's code-ouroboros heartbeat.

Same discipline as the ASCENT driver:

  * **propose-only** — REVERIE never acts; the Sovereign reads insights and may
    promote a curiosity goal into a real objective.
  * **cheap** — one reflection per tick, regardless of history size.
  * **crash-proof** — a failing tick is logged and swallowed; the heartbeat never
    dies and never takes the web service down.

Wired only by the production entrypoint (``sovereign_web.main``); the default
``create_app()`` used by tests starts no driver and stays deterministic/offline.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi.concurrency import run_in_threadpool

log = logging.getLogger("pradyos.reverie.driver")

_STOP_TIMEOUT_S = 5.0


class ReverieDriver:
    """A background heartbeat that has REVERIE reflect on an interval."""

    def __init__(self, reverie: Any, interval_s: float = 240.0) -> None:
        self._reverie = reverie
        self._interval = max(1.0, float(interval_s))
        self._task: asyncio.Task[None] | None = None
        self._lock = threading.RLock()
        self._ticks = 0
        self._last_goal: str | None = None

    def tick(self) -> dict[str, Any]:
        """Run one reflection pass; return the insight."""
        insight = self._reverie.reflect()
        with self._lock:
            self._ticks += 1
            self._last_goal = insight.get("curiosity_goal")
        return insight

    async def _run(self) -> None:
        log.info("reverie driver started (interval=%ss)", self._interval)
        while True:
            await asyncio.sleep(self._interval)
            try:
                await run_in_threadpool(self.tick)
            except Exception as exc:  # noqa: BLE001 — a bad tick must not kill the heartbeat
                log.warning("reverie driver tick failed: %s", exc)

    def start(self) -> None:
        """Launch the heartbeat as a background task on the running event loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=_STOP_TIMEOUT_S)
            except TimeoutError:
                log.warning("reverie driver stop timed out after %ss; continuing", _STOP_TIMEOUT_S)
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._task is not None and not self._task.done(),
                "ticks": self._ticks,
                "interval_s": self._interval,
                "last_goal": self._last_goal,
            }
