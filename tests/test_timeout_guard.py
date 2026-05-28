"""Phase 56C — 20 tests for pradyos.core.timeout_guard.TimeoutGuard."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.timeout_guard import (
    GuardRecord,
    TimeoutExpiredError,
    TimeoutGuard,
)


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_default_timeout():
    g = TimeoutGuard(default_timeout=2.5)
    assert g.default_timeout == 2.5


# ── execute success ──────────────────────────────────────────────────────────

def test_execute_returns_result_on_success():
    g = TimeoutGuard(default_timeout=1.0)
    assert g.execute("svc", lambda: 42) == 42


def test_execute_records_success_outcome():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("svc", lambda: "ok")
    rec = g.get_history("svc")[0]
    assert rec.outcome == "success"


def test_execute_records_non_negative_elapsed():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("svc", lambda: "ok")
    rec = g.get_history("svc")[0]
    assert rec.elapsed >= 0.0


# ── execute timeout ──────────────────────────────────────────────────────────

def test_execute_raises_timeout_when_fn_too_slow():
    g = TimeoutGuard(default_timeout=0.05)

    def slow():
        time.sleep(1.0)
        return "should not return"

    with pytest.raises(TimeoutExpiredError):
        g.execute("svc", slow)


def test_execute_records_timeout_outcome():
    g = TimeoutGuard(default_timeout=0.05)

    def slow():
        time.sleep(1.0)

    with pytest.raises(TimeoutExpiredError):
        g.execute("svc", slow)
    rec = g.get_history("svc")[0]
    assert rec.outcome == "timeout"


# ── execute error ────────────────────────────────────────────────────────────

def test_execute_raises_original_exception_when_fn_raises():
    g = TimeoutGuard(default_timeout=1.0)

    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        g.execute("svc", boom)


def test_execute_records_error_outcome():
    g = TimeoutGuard(default_timeout=1.0)

    def boom():
        raise RuntimeError("oops")

    with pytest.raises(RuntimeError):
        g.execute("svc", boom)
    rec = g.get_history("svc")[0]
    assert rec.outcome == "error"


def test_execute_records_error_message():
    g = TimeoutGuard(default_timeout=1.0)

    def boom():
        raise RuntimeError("specific message")

    with pytest.raises(RuntimeError):
        g.execute("svc", boom)
    assert "specific message" in g.get_history("svc")[0].error


# ── get_history / clear_history ──────────────────────────────────────────────

def test_get_history_returns_list_of_records():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("svc", lambda: "ok")
    hist = g.get_history("svc")
    assert isinstance(hist, list)
    assert isinstance(hist[0], GuardRecord)


def test_get_history_unknown_returns_empty():
    g = TimeoutGuard(default_timeout=1.0)
    assert g.get_history("phantom") == []


def test_get_history_records_in_submission_order():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("svc", lambda: 1)
    g.execute("svc", lambda: 2)
    g.execute("svc", lambda: 3)
    hist = g.get_history("svc")
    assert [r.outcome for r in hist] == ["success", "success", "success"]
    # Timestamps should be monotonically non-decreasing
    assert hist[0].ts <= hist[1].ts <= hist[2].ts


def test_clear_history_returns_true_removes_records():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("svc", lambda: "ok")
    assert g.clear_history("svc") is True
    assert g.get_history("svc") == []


def test_clear_history_unknown_returns_false():
    g = TimeoutGuard(default_timeout=1.0)
    assert g.clear_history("phantom") is False


# ── list_names / count ───────────────────────────────────────────────────────

def test_list_names_sorted():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("zzz", lambda: None)
    g.execute("aaa", lambda: None)
    g.execute("mmm", lambda: None)
    assert g.list_names() == ["aaa", "mmm", "zzz"]


def test_count_scoped_to_name():
    g = TimeoutGuard(default_timeout=1.0)
    g.execute("a", lambda: 1)
    g.execute("a", lambda: 2)
    g.execute("b", lambda: 3)
    assert g.count("a") == 2
    assert g.count("b") == 1


def test_count_total_across_names():
    g = TimeoutGuard(default_timeout=1.0)
    for n in ("a", "b", "c"):
        g.execute(n, lambda: 1)
        g.execute(n, lambda: 2)
    assert g.count() == 6


# ── per-call timeout override ────────────────────────────────────────────────

def test_per_call_timeout_overrides_default():
    g = TimeoutGuard(default_timeout=10.0)  # default would allow slow fn

    def slow():
        time.sleep(1.0)

    with pytest.raises(TimeoutExpiredError):
        g.execute("svc", slow, timeout=0.05)


# ── TimeoutExpiredError type ─────────────────────────────────────────────────

def test_timeout_expired_error_is_runtime_error():
    assert issubclass(TimeoutExpiredError, RuntimeError)


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_20_concurrent_executes():
    g = TimeoutGuard(default_timeout=1.0)
    errors: list[Exception] = []

    def worker(i: int):
        try:
            g.execute("svc", lambda: f"r{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert g.count("svc") == 20
