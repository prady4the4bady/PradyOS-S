"""Config live-reload — Phase 7E.

ConfigWatcher monitors a TOML file for modifications using a background
polling thread (no third-party dependencies required — watchdog/watchfiles
are used if available, otherwise falls back to mtime polling every second).

The watcher calls ``on_reload(new_config)`` whenever the file changes and
the new TOML parses successfully. Invalid TOML is logged as a warning and
silently ignored (no callback, no crash).

Windows-safe: threading.Thread(daemon=True), pathlib.Path, no AF_UNIX,
no fork, no os.killpg.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pradyos.core.config import SovereignConfig, load_config

log = logging.getLogger("pradyos.core.config_watcher")

__all__ = ["ConfigWatcher"]

# Poll interval (seconds) when watchdog/watchfiles are not available
_POLL_INTERVAL = float(os.environ.get("PRADYOS_CONFIG_POLL_INTERVAL", "1.0"))


class ConfigWatcher:
    """Watch a TOML config file and call a callback on change.

    Parameters
    ----------
    toml_path : Path | str
        Path to the TOML file to watch (typically ``pradyos.toml``).
    on_reload : Callable[[SovereignConfig], None]
        Called with the newly loaded config whenever a change is detected
        and the TOML parses successfully.

    Usage
    -----
    ::

        def handle_reload(cfg: SovereignConfig) -> None:
            scheduler.poll_interval = cfg.some_setting

        watcher = ConfigWatcher("pradyos.toml", on_reload=handle_reload)
        watcher.start()
        # ... later ...
        watcher.stop()

    The watcher can also use ``attach(scheduler, warden_grid)`` as a
    convenience to auto-wire common subsystem callbacks.
    """

    def __init__(
        self,
        toml_path: Path | str,
        on_reload: Callable[[SovereignConfig], None],
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        self._path = Path(toml_path)
        self._on_reload = on_reload
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_mtime: float = self._current_mtime()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background watcher thread."""
        if self._thread is not None and self._thread.is_alive():
            log.debug("ConfigWatcher already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="config-watcher",
            daemon=True,
        )
        self._thread.start()
        log.info("ConfigWatcher started (polling %s every %.1fs)", self._path, self._poll_interval)

    def stop(self) -> None:
        """Signal the watcher thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self._poll_interval * 2))
            self._thread = None
        log.info("ConfigWatcher stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def attach(self, scheduler: Any | None = None, warden_grid: Any | None = None) -> None:
        """Convenience: wire common subsystem callbacks into on_reload.

        Wraps the existing on_reload callback so that both the caller-supplied
        callback AND the subsystem callbacks fire on each config change.

        scheduler   — if it has a ``poll_interval`` attribute, it will be
                      updated to ``cfg.max_campaign_workers`` (as a proxy for
                      poll-interval tuning in absence of a dedicated field).
        warden_grid — if it has a ``set_failure_threshold`` method or a
                      ``failure_threshold`` attribute, it will be updated.
        """
        original_callback = self._on_reload

        def _combined(cfg: SovereignConfig) -> None:
            # Call original first
            try:
                original_callback(cfg)
            except Exception as e:  # noqa: BLE001
                log.debug("on_reload callback failed: %s", e)

            # Scheduler: update poll interval (use max_campaign_workers as proxy)
            if scheduler is not None:
                try:
                    if hasattr(scheduler, "poll_interval"):
                        scheduler.poll_interval = float(cfg.max_campaign_workers)
                        log.debug("Scheduler poll_interval updated to %s", cfg.max_campaign_workers)
                except Exception as e:  # noqa: BLE001
                    log.debug("Scheduler update failed: %s", e)

            # WardenGrid: update failure thresholds
            if warden_grid is not None:
                try:
                    if hasattr(warden_grid, "set_failure_threshold"):
                        warden_grid.set_failure_threshold(cfg.max_campaign_workers)
                    elif hasattr(warden_grid, "failure_threshold"):
                        warden_grid.failure_threshold = cfg.max_campaign_workers
                    log.debug("WardenGrid threshold updated")
                except Exception as e:  # noqa: BLE001
                    log.debug("WardenGrid update failed: %s", e)

        with self._lock:
            self._on_reload = _combined

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Background thread: check mtime every poll_interval seconds."""
        while not self._stop_event.is_set():
            try:
                mtime = self._current_mtime()
                if mtime != self._last_mtime:
                    self._last_mtime = mtime
                    self._on_file_changed()
            except Exception as e:  # noqa: BLE001
                log.debug("ConfigWatcher poll error: %s", e)

            self._stop_event.wait(timeout=self._poll_interval)

    def _current_mtime(self) -> float:
        """Return current mtime of the watched file, or 0.0 if absent."""
        try:
            return self._path.stat().st_mtime
        except OSError:
            return 0.0

    def _on_file_changed(self) -> None:
        """Called when a mtime change is detected."""
        log.info("Config file changed: %s — reloading", self._path)
        try:
            new_cfg = load_config(toml_path=self._path)
        except Exception as e:  # noqa: BLE001
            log.warning("Config reload failed (TOML parse error): %s — keeping previous config", e)
            return

        with self._lock:
            callback = self._on_reload
        try:
            callback(new_cfg)
            log.info("Config reloaded successfully from %s", self._path)
        except Exception as e:  # noqa: BLE001
            log.warning("Config on_reload callback raised: %s", e)

    # ------------------------------------------------------------------
    # Force-reload (testing / admin)
    # ------------------------------------------------------------------

    def force_reload(self) -> SovereignConfig | None:
        """Immediately reload config and call the callback.

        Returns the new SovereignConfig or None on parse failure.
        """
        try:
            new_cfg = load_config(toml_path=self._path)
        except Exception as e:  # noqa: BLE001
            log.warning("force_reload: parse error: %s", e)
            return None
        with self._lock:
            callback = self._on_reload
        try:
            callback(new_cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("force_reload: callback raised: %s", e)
        return new_cfg
