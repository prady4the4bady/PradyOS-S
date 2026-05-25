"""IMPERIUM KernelWatchdog — detects and heals stuck running tasks.

Runs a background thread that periodically checks the checkpoint for tasks
in RUNNING state.  If a task has been running longer than ``max_stuck_s``
seconds, it is marked FAILED with reason ``watchdog_timeout`` and a
``task.watchdog_timeout`` event is published to the bus.

Windows-safe: threading only, no fork, no AF_UNIX, all paths via pathlib.

Environment overrides (useful for tests):
    WATCHDOG_MAX_STUCK_S        float, default 300.0
    WATCHDOG_CHECK_INTERVAL_S   float, default 30.0
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

log = logging.getLogger("pradyos.imperium.watchdog")


class KernelWatchdog:
    """Background thread that marks stuck RUNNING tasks as FAILED.

    Parameters
    ----------
    kernel:
        The IMPERIUM kernel object.  Must expose:
            ``checkpoint``  — object with ``.load()`` returning
                              ``dict[task_id, dict]`` where each dict has
                              ``"state"`` and ``"started_at"`` keys.
            ``mark_failed(task_id, reason)``  — callable that transitions
                              the task to FAILED state.
            ``bus``  — :class:`~pradyos.core.bus.EventBus`  (optional; may be None)
    max_stuck_s:
        How long a RUNNING task may run before being declared stuck.
        Overridden by ``WATCHDOG_MAX_STUCK_S`` env var at construction time.
    check_interval_s:
        How often to run the stuck-task scan.
        Overridden by ``WATCHDOG_CHECK_INTERVAL_S`` env var at construction time.
    """

    def __init__(
        self,
        kernel: Any,
        max_stuck_s: float = 300.0,
        check_interval_s: float = 30.0,
    ) -> None:
        self.kernel = kernel
        self.max_stuck_s: float = float(
            os.environ.get("WATCHDOG_MAX_STUCK_S", max_stuck_s)
        )
        self.check_interval_s: float = float(
            os.environ.get("WATCHDOG_CHECK_INTERVAL_S", check_interval_s)
        )

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the background watchdog thread."""
        if self._thread is not None and self._thread.is_alive():
            log.warning("KernelWatchdog.start() called but thread already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="pradyos-watchdog",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "KernelWatchdog started (max_stuck=%.0fs, interval=%.0fs)",
            self.max_stuck_s,
            self.check_interval_s,
        )

    def stop(self) -> None:
        """Signal the watchdog thread to exit and wait for it (max 5 s)."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        log.info("KernelWatchdog stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Run the watch loop until stop() is called."""
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                log.error("KernelWatchdog tick error: %s", exc)
            # Wait for next interval (or stop signal)
            self._stop_event.wait(timeout=self.check_interval_s)

    def _tick(self) -> None:
        """One scan pass: find stuck tasks and mark them failed."""
        now = time.time()
        try:
            tasks: dict[str, dict[str, Any]] = self.kernel.checkpoint.load()
        except Exception as exc:  # noqa: BLE001
            log.warning("KernelWatchdog: checkpoint.load() failed: %s", exc)
            return

        for task_id, task in tasks.items():
            if task.get("state") != "RUNNING":
                continue
            started_at = task.get("started_at")
            if started_at is None:
                continue
            running_for = now - float(started_at)
            if running_for < self.max_stuck_s:
                continue

            log.warning(
                "KernelWatchdog: task %s stuck (running %.0fs > limit %.0fs) — marking FAILED",
                task_id,
                running_for,
                self.max_stuck_s,
            )
            try:
                self.kernel.mark_failed(task_id, reason="watchdog_timeout")
            except Exception as exc:  # noqa: BLE001
                log.error("KernelWatchdog: mark_failed(%s) error: %s", task_id, exc)
                continue

            # Publish bus event (bus may be None or may not exist on kernel)
            bus = getattr(self.kernel, "bus", None)
            if bus is not None:
                try:
                    bus.publish(
                        "task.watchdog_timeout",
                        {"task_id": task_id, "running_for_s": running_for},
                    )
                except Exception as exc:  # noqa: BLE001
                    log.debug("KernelWatchdog: bus.publish failed: %s", exc)
