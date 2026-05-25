"""Tests for pradyos.imperium.watchdog — KernelWatchdog.

All tests are self-contained with mock kernels and no real disk I/O.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pradyos.imperium.watchdog import KernelWatchdog


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_kernel(tasks: dict | None = None):
    """Build a minimal mock kernel matching the watchdog contract."""
    tasks = tasks or {}
    checkpoint = MagicMock()
    checkpoint.load.return_value = tasks

    bus = MagicMock()
    kernel = MagicMock()
    kernel.checkpoint = checkpoint
    kernel.bus = bus
    return kernel


def _running_task(started_at: float) -> dict:
    return {"state": "RUNNING", "started_at": started_at}


def _succeeded_task(started_at: float) -> dict:
    return {"state": "SUCCEEDED", "started_at": started_at}


def _queued_task() -> dict:
    return {"state": "QUEUED", "started_at": None}


# ---------------------------------------------------------------------------
# _tick logic
# ---------------------------------------------------------------------------


def test_stuck_task_gets_marked_failed():
    """A task running longer than max_stuck_s is marked FAILED."""
    long_ago = time.time() - 400.0  # 400 s > 300 s default
    kernel = _make_kernel({"task-1": _running_task(long_ago)})
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=999.0)

    wd._tick()

    kernel.mark_failed.assert_called_once_with("task-1", reason="watchdog_timeout")


def test_non_stuck_task_left_alone():
    """A recently started task is not touched."""
    just_now = time.time() - 5.0  # only 5 s < 300 s
    kernel = _make_kernel({"task-2": _running_task(just_now)})
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=999.0)

    wd._tick()

    kernel.mark_failed.assert_not_called()


def test_non_running_states_left_alone():
    """SUCCEEDED/QUEUED tasks are not touched."""
    long_ago = time.time() - 1000.0
    kernel = _make_kernel({
        "task-s": _succeeded_task(long_ago),
        "task-q": _queued_task(),
    })
    wd = KernelWatchdog(kernel, max_stuck_s=1.0, check_interval_s=999.0)

    wd._tick()

    kernel.mark_failed.assert_not_called()


def test_task_without_started_at_skipped():
    """Tasks with started_at=None are skipped gracefully."""
    kernel = _make_kernel({"task-x": {"state": "RUNNING", "started_at": None}})
    wd = KernelWatchdog(kernel, max_stuck_s=1.0, check_interval_s=999.0)

    wd._tick()

    kernel.mark_failed.assert_not_called()


def test_bus_event_published_on_stuck():
    """After marking failed, a task.watchdog_timeout bus event is published."""
    long_ago = time.time() - 600.0
    kernel = _make_kernel({"task-3": _running_task(long_ago)})
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=999.0)

    wd._tick()

    kernel.bus.publish.assert_called_once()
    call_args = kernel.bus.publish.call_args
    assert call_args[0][0] == "task.watchdog_timeout"
    assert call_args[0][1]["task_id"] == "task-3"


def test_multiple_stuck_tasks_all_marked():
    long_ago = time.time() - 500.0
    kernel = _make_kernel({
        "t1": _running_task(long_ago),
        "t2": _running_task(long_ago),
        "t3": _running_task(time.time() - 1.0),  # not stuck
    })
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=999.0)

    wd._tick()

    assert kernel.mark_failed.call_count == 2
    called_ids = {c.args[0] for c in kernel.mark_failed.call_args_list}
    assert "t1" in called_ids
    assert "t2" in called_ids
    assert "t3" not in called_ids


def test_checkpoint_load_exception_is_handled():
    """If checkpoint.load raises, tick should not propagate the exception."""
    kernel = _make_kernel()
    kernel.checkpoint.load.side_effect = OSError("disk gone")
    wd = KernelWatchdog(kernel, max_stuck_s=1.0, check_interval_s=999.0)

    wd._tick()  # must not raise

    kernel.mark_failed.assert_not_called()


def test_mark_failed_exception_continues_other_tasks():
    """If mark_failed raises for one task, other tasks still get processed."""
    long_ago = time.time() - 500.0
    kernel = _make_kernel({
        "t1": _running_task(long_ago),
        "t2": _running_task(long_ago),
    })
    call_count = {"n": 0}

    def side_effect(task_id, reason):
        call_count["n"] += 1
        if task_id == "t1":
            raise RuntimeError("failed to mark t1")

    kernel.mark_failed.side_effect = side_effect

    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=999.0)
    wd._tick()  # must not raise

    assert call_count["n"] == 2


def test_kernel_without_bus_attribute():
    """Kernel without a bus attribute should not raise."""
    long_ago = time.time() - 500.0
    kernel = MagicMock(spec=["checkpoint", "mark_failed"])  # no bus attr
    kernel.checkpoint.load.return_value = {"t1": _running_task(long_ago)}

    wd = KernelWatchdog(kernel, max_stuck_s=1.0, check_interval_s=999.0)
    wd._tick()  # must not raise

    kernel.mark_failed.assert_called_once()


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


def test_env_override_max_stuck_s(monkeypatch):
    monkeypatch.setenv("WATCHDOG_MAX_STUCK_S", "60.0")
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel)
    assert wd.max_stuck_s == 60.0


def test_env_override_check_interval_s(monkeypatch):
    monkeypatch.setenv("WATCHDOG_CHECK_INTERVAL_S", "15.0")
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel)
    assert wd.check_interval_s == 15.0


def test_constructor_args_used_as_defaults(monkeypatch):
    """When env vars absent, constructor args are used."""
    monkeypatch.delenv("WATCHDOG_MAX_STUCK_S", raising=False)
    monkeypatch.delenv("WATCHDOG_CHECK_INTERVAL_S", raising=False)
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel, max_stuck_s=42.0, check_interval_s=7.0)
    assert wd.max_stuck_s == 42.0
    assert wd.check_interval_s == 7.0


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


def test_start_launches_thread():
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=60.0)

    wd.start()
    assert wd._thread is not None
    assert wd._thread.is_alive()
    wd.stop()
    assert wd._thread is None


def test_stop_joins_thread():
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=60.0)

    wd.start()
    alive_before = wd._thread.is_alive()
    wd.stop()

    assert alive_before is True
    assert wd._thread is None


def test_double_start_does_not_create_second_thread():
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=60.0)

    wd.start()
    first_thread = wd._thread
    wd.start()  # should be a no-op
    second_thread = wd._thread

    assert first_thread is second_thread
    wd.stop()


def test_stop_before_start_is_safe():
    kernel = _make_kernel()
    wd = KernelWatchdog(kernel, max_stuck_s=300.0, check_interval_s=60.0)
    wd.stop()  # must not raise


def test_watchdog_fires_on_fast_interval():
    """Integration: watchdog actually calls mark_failed in background thread."""
    long_ago = time.time() - 500.0
    kernel = _make_kernel({"task-stuck": _running_task(long_ago)})

    # Use very small interval so the test doesn't wait long
    wd = KernelWatchdog(kernel, max_stuck_s=100.0, check_interval_s=0.05)
    wd.start()
    time.sleep(0.2)  # give watchdog time for ≥1 tick
    wd.stop()

    assert kernel.mark_failed.call_count >= 1
