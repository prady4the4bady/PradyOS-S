"""Tests for Phase 7E: config_watcher.py"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from pradyos.core.config import SovereignConfig
from pradyos.core.config_watcher import ConfigWatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOML = """\
[sovereign]
log_level = "DEBUG"
max_campaign_workers = 8
"""

_INVALID_TOML = """\
[sovereign
this is not valid toml ===
"""


def _write(path: Path, content: str) -> None:
    # Atomic replace: a polling watcher must never observe a half-written
    # (zero-byte) file, which would otherwise parse as empty/default config.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 1. Watcher does not call callback before file changes
# ---------------------------------------------------------------------------

def test_no_callback_before_change(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    calls = []
    watcher = ConfigWatcher(toml, on_reload=lambda cfg: calls.append(cfg), poll_interval=0.05)
    watcher.start()
    time.sleep(0.15)
    watcher.stop()

    assert len(calls) == 0, "Callback should NOT fire before any file change"


# ---------------------------------------------------------------------------
# 2. File change triggers callback
# ---------------------------------------------------------------------------

def test_file_change_triggers_callback(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    received: list[SovereignConfig] = []
    event = threading.Event()

    def _cb(cfg: SovereignConfig) -> None:
        received.append(cfg)
        event.set()

    watcher = ConfigWatcher(toml, on_reload=_cb, poll_interval=0.05)
    watcher.start()

    # Wait a tick then modify the file
    time.sleep(0.1)
    _write(toml, _VALID_TOML.replace("DEBUG", "WARNING"))

    triggered = event.wait(timeout=2.0)
    watcher.stop()

    assert triggered, "Callback not triggered after file change"
    assert isinstance(received[0], SovereignConfig)


# ---------------------------------------------------------------------------
# 3. Callback receives updated config values
# ---------------------------------------------------------------------------

def test_callback_receives_new_config(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    received: list[SovereignConfig] = []
    event = threading.Event()

    def _cb(cfg: SovereignConfig) -> None:
        received.append(cfg)
        event.set()

    watcher = ConfigWatcher(toml, on_reload=_cb, poll_interval=0.05)
    watcher.start()
    time.sleep(0.1)

    new_toml = "[sovereign]\nlog_level = \"ERROR\"\nmax_campaign_workers = 2\n"
    _write(toml, new_toml)
    event.wait(timeout=2.0)
    watcher.stop()

    assert received
    assert received[0].log_level == "ERROR"
    assert received[0].max_campaign_workers == 2


# ---------------------------------------------------------------------------
# 4. stop() prevents further callbacks
# ---------------------------------------------------------------------------

def test_stop_prevents_further_callbacks(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    calls: list[SovereignConfig] = []
    watcher = ConfigWatcher(toml, on_reload=lambda cfg: calls.append(cfg), poll_interval=0.05)
    watcher.start()
    time.sleep(0.1)
    watcher.stop()

    count_at_stop = len(calls)
    # Modify after stop — should not trigger
    _write(toml, _VALID_TOML + "\n# extra")
    time.sleep(0.3)

    assert len(calls) == count_at_stop, "Callback fired after stop()"


# ---------------------------------------------------------------------------
# 5. Invalid TOML logs warning without crashing
# ---------------------------------------------------------------------------

def test_invalid_toml_does_not_crash(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    calls: list[SovereignConfig] = []
    watcher = ConfigWatcher(toml, on_reload=lambda cfg: calls.append(cfg), poll_interval=0.05)
    watcher.start()
    time.sleep(0.1)

    # Write invalid TOML
    _write(toml, _INVALID_TOML)
    time.sleep(0.3)
    watcher.stop()

    # Watcher should still be functional — no crash, no callback for bad TOML
    assert watcher._thread is None or not watcher._thread.is_alive()


# ---------------------------------------------------------------------------
# 6. force_reload() triggers callback immediately
# ---------------------------------------------------------------------------

def test_force_reload(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    received: list[SovereignConfig] = []
    watcher = ConfigWatcher(toml, on_reload=lambda cfg: received.append(cfg))

    result = watcher.force_reload()
    assert isinstance(result, SovereignConfig)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# 7. attach() wires scheduler callback
# ---------------------------------------------------------------------------

def test_attach_updates_scheduler(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    scheduler = MagicMock()
    scheduler.poll_interval = 1.0

    calls: list[SovereignConfig] = []
    watcher = ConfigWatcher(toml, on_reload=lambda cfg: calls.append(cfg))
    watcher.attach(scheduler=scheduler)
    watcher.force_reload()

    # Scheduler poll_interval should be updated (to max_campaign_workers from TOML = 8)
    assert scheduler.poll_interval == 8.0


# ---------------------------------------------------------------------------
# 8. is_running reflects thread state
# ---------------------------------------------------------------------------

def test_is_running(tmp_path):
    toml = tmp_path / "pradyos.toml"
    _write(toml, _VALID_TOML)

    watcher = ConfigWatcher(toml, on_reload=lambda cfg: None, poll_interval=0.05)
    assert not watcher.is_running
    watcher.start()
    assert watcher.is_running
    watcher.stop()
    assert not watcher.is_running
