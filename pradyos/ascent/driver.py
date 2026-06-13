"""ASCENT driver — make the self-improvement loop run on its own, in real time.

:class:`~pradyos.ascent.loop.AscentLoop` decides *what* to harden and gates a
candidate, but it has to be *asked* (an API call). The driver is what makes the
loop **autonomous**: a background heartbeat that, on an interval, hands the loop
a rotating batch of the agent's OWN module sources and runs a cycle — so the
booted OS continuously surveys itself and queues hardening proposals for the
Sovereign with no human in the loop.

It is deliberately conservative:

  * **read-only** — it reads its own ``*.py`` sources; ASCENT never writes code,
    so the driver can only ever *queue* a promote or *escalate* to the Sovereign.
  * **bounded** — a fixed-size batch per tick, rotating through the package, so
    one tick is cheap regardless of how large the codebase grows.
  * **crash-proof** — a failing tick is logged and swallowed; the heartbeat never
    dies and never takes the web service down with it.

The driver shares the *same* :class:`AscentLoop` the HTTP surface exposes, so its
autonomous cycles show up live at ``/api/v1/ascent/*``. It is wired only by the
production entrypoint (``sovereign_web.main``); the default ``create_app()`` used
by tests starts no driver and stays deterministic/offline.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi.concurrency import run_in_threadpool

log = logging.getLogger("pradyos.ascent.driver")

# Sub-packages whose modules are huge or I/O-shaped and not useful self-hardening
# targets for an unattended pass (the web adapters are thin; the TUI is large).
_DEFAULT_EXCLUDE = ("web", "aurora_throne", "ascent")


class OwnModuleSource:
    """A rotating provider of the agent's own module sources.

    Each call returns a fresh ``{relative_path: source}`` batch, advancing a
    cursor so successive ticks survey different modules and, over time, the whole
    package. Sources are read fresh each call (so a self-modification that lands
    on disk is picked up on the next pass).
    """

    def __init__(
        self,
        root: Path | str | None = None,
        batch: int = 6,
        exclude: tuple[str, ...] = _DEFAULT_EXCLUDE,
    ) -> None:
        if root is None:
            import pradyos

            root = Path(pradyos.__file__).resolve().parent
        self._root = Path(root)
        self._base = self._root.parent  # so relative paths read "pradyos/<...>.py"
        self._batch = max(1, int(batch))
        self._exclude = exclude
        self._files = self._discover()
        self._pos = 0
        self._lock = threading.RLock()

    def _discover(self) -> list[Path]:
        out: list[Path] = []
        for path in sorted(self._root.rglob("*.py")):
            parts = path.relative_to(self._root).parts
            if "__pycache__" in parts or parts[-1] == "__init__.py":
                continue
            if parts and parts[0] in self._exclude:
                continue
            out.append(path)
        return out

    def __call__(self) -> dict[str, str]:
        with self._lock:
            if not self._files:
                return {}
            n = len(self._files)
            window = [self._files[(self._pos + i) % n] for i in range(min(self._batch, n))]
            self._pos = (self._pos + self._batch) % n
        out: dict[str, str] = {}
        for path in window:
            try:
                out[str(path.relative_to(self._base)).replace("\\", "/")] = path.read_text(
                    encoding="utf-8"
                )
            except OSError as exc:  # a vanished/unreadable file must not break the tick
                log.debug("ascent driver: could not read %s: %s", path, exc)
        return out


class AscentDriver:
    """A background heartbeat that runs ASCENT cycles on the agent's own code."""

    def __init__(
        self,
        ascent: Any,
        source_provider: Any,
        interval_s: float = 300.0,
        max_targets: int = 1,
    ) -> None:
        self._ascent = ascent
        self._source = source_provider
        self._interval = max(1.0, float(interval_s))
        self._max_targets = max(1, int(max_targets))
        self._task: asyncio.Task[None] | None = None
        self._lock = threading.RLock()
        self._ticks = 0
        self._last_cycles = 0

    def tick(self) -> list[dict[str, Any]]:
        """Run one autonomous survey→cycle pass over a fresh batch of own modules."""
        candidates = self._source()
        cycles: list[dict[str, Any]] = []
        if candidates:
            cycles = self._ascent.run_cycle(candidates, max_targets=self._max_targets)
        with self._lock:
            self._ticks += 1
            self._last_cycles = len(cycles)
        return cycles

    async def _run(self) -> None:
        log.info(
            "ascent driver started (interval=%ss, batch max_targets=%s)",
            self._interval,
            self._max_targets,
        )
        while True:
            await asyncio.sleep(self._interval)
            try:
                # tick() runs the (possibly LLM-backed) cycle — keep it off the loop.
                await run_in_threadpool(self.tick)
            except Exception as exc:  # noqa: BLE001 — a bad tick must not kill the heartbeat
                log.warning("ascent driver tick failed: %s", exc)

    def start(self) -> None:
        """Launch the heartbeat as a background task on the running event loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._task is not None and not self._task.done(),
                "ticks": self._ticks,
                "last_cycles": self._last_cycles,
                "interval_s": self._interval,
                "max_targets": self._max_targets,
            }
