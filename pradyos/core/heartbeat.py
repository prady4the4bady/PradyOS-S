from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass


@dataclass
class HeartbeatConfig:
    interval_seconds: float = 5.0
    max_ticks: int | None = None

    def to_dict(self) -> dict:
        return {
            "interval_seconds": self.interval_seconds,
            "max_ticks": self.max_ticks,
        }


class HeartbeatLoop:
    def __init__(
        self,
        control_plane=None,
        config: HeartbeatConfig | None = None,
    ) -> None:
        self._cp = control_plane
        self._config = (
            config if config is not None else HeartbeatConfig(interval_seconds=5.0, max_ticks=None)
        )
        self._running = False
        self._tick_count = 0
        self._task: asyncio.Task | None = None
        self._lock = threading.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            try:
                await asyncio.wait_for(
                    self._task,
                    timeout=self._config.interval_seconds + 1,
                )
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _loop(self) -> None:
        while self._running:
            if self._cp is not None:
                try:
                    self._cp.tick()
                except Exception:
                    pass

            with self._lock:
                self._tick_count += 1

            if self._config.max_ticks is not None and self._tick_count >= self._config.max_ticks:
                self._running = False
                break

            await asyncio.sleep(self._config.interval_seconds)

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "tick_count": self._tick_count,
                "interval_seconds": self._config.interval_seconds,
            }
