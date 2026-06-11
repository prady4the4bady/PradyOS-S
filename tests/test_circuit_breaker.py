"""Phase 53C — 20 tests for pradyos.core.circuit_breaker.CircuitBreaker."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitOpenError,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_HALF_OPEN,
)


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_states():
    cb = CircuitBreaker()
    assert cb._states == {}


# ── call success / failure ────────────────────────────────────────────────────

def test_call_success_creates_closed_state():
    cb = CircuitBreaker()
    cb.call("svc", lambda: "ok")
    bs = cb.get_state("svc")
    assert bs is not None
    assert bs.state == STATE_CLOSED


def test_closed_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=5)
    # Drive up some failures
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cb.get_state("svc").failure_count == 3
    # Success resets count
    cb.call("svc", lambda: "ok")
    assert cb.get_state("svc").failure_count == 0


def test_closed_failure_increments_count():
    cb = CircuitBreaker(failure_threshold=5)
    with pytest.raises(RuntimeError):
        cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cb.get_state("svc").failure_count == 1


# ── CLOSED → OPEN ─────────────────────────────────────────────────────────────

def test_closed_to_open_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cb.get_state("svc").state == STATE_OPEN


def test_open_raises_circuit_open_error_immediately():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    # Now OPEN — even a success-fn raises CircuitOpenError immediately
    called = []
    with pytest.raises(CircuitOpenError):
        cb.call("svc", lambda: called.append(1) or "ok")
    assert called == []  # fn was NOT invoked


# ── OPEN → HALF_OPEN → CLOSED / OPEN ─────────────────────────────────────────

def test_open_transitions_to_half_open_after_recovery_timeout_then_closed_on_success():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cb.get_state("svc").state == STATE_OPEN

    time.sleep(0.02)
    # First post-timeout call goes through (HALF_OPEN probe). Success → CLOSED.
    result = cb.call("svc", lambda: "recovered")
    assert result == "recovered"
    bs = cb.get_state("svc")
    assert bs.state == STATE_CLOSED


def test_half_open_success_closes_the_breaker():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    time.sleep(0.02)
    # First post-timeout success transitions HALF_OPEN → CLOSED
    cb.call("svc", lambda: "ok")
    bs = cb.get_state("svc")
    assert bs.state == STATE_CLOSED
    assert bs.failure_count == 0
    assert bs.opened_at is None


def test_half_open_failure_returns_to_open():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max=1)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    open_at_first = cb.get_state("svc").opened_at
    time.sleep(0.02)
    with pytest.raises(RuntimeError):
        cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("y")))
    bs = cb.get_state("svc")
    assert bs.state == STATE_OPEN
    assert bs.opened_at > open_at_first  # opened_at reset on flip-back


def test_half_open_max_2_requires_two_failures_to_flip_back():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max=2)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    time.sleep(0.02)

    # First probe failure — still HALF_OPEN
    with pytest.raises(RuntimeError):
        cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("y")))
    assert cb.get_state("svc").state == STATE_HALF_OPEN

    # Second probe failure — now OPEN
    with pytest.raises(RuntimeError):
        cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("z")))
    assert cb.get_state("svc").state == STATE_OPEN


# ── get_state ─────────────────────────────────────────────────────────────────

def test_get_state_returns_breakerstate():
    cb = CircuitBreaker()
    cb.call("svc", lambda: "ok")
    assert isinstance(cb.get_state("svc"), BreakerState)


def test_get_state_returns_none_for_unknown():
    cb = CircuitBreaker()
    assert cb.get_state("phantom") is None


# ── reset ─────────────────────────────────────────────────────────────────────

def test_reset_returns_true_forces_closed():
    cb = CircuitBreaker(failure_threshold=1)
    with pytest.raises(RuntimeError):
        cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cb.get_state("svc").state == STATE_OPEN
    assert cb.reset("svc") is True
    assert cb.get_state("svc").state == STATE_CLOSED


def test_reset_returns_false_for_unknown():
    cb = CircuitBreaker()
    assert cb.reset("phantom") is False


def test_reset_zeros_out_failure_count_and_timestamps():
    cb = CircuitBreaker(failure_threshold=1)
    with pytest.raises(RuntimeError):
        cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    cb.reset("svc")
    bs = cb.get_state("svc")
    assert bs.failure_count == 0
    assert bs.last_failure_at is None
    assert bs.opened_at is None


# ── list_breakers / count ─────────────────────────────────────────────────────

def test_list_breakers_sorted():
    cb = CircuitBreaker()
    cb.call("zzz", lambda: None)
    cb.call("aaa", lambda: None)
    cb.call("mmm", lambda: None)
    names = [b["name"] for b in cb.list_breakers()]
    assert names == ["aaa", "mmm", "zzz"]


def test_list_breakers_to_dict_has_required_keys():
    cb = CircuitBreaker()
    cb.call("svc", lambda: None)
    entry = cb.list_breakers()[0]
    for k in ("name", "state", "failure_count", "last_failure_at", "opened_at"):
        assert k in entry


def test_count_zero_on_empty():
    cb = CircuitBreaker()
    assert cb.count() == 0


def test_count_correct_after_calls():
    cb = CircuitBreaker()
    cb.call("a", lambda: None)
    cb.call("b", lambda: None)
    cb.call("c", lambda: None)
    assert cb.count() == 3


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_calls():
    cb = CircuitBreaker(failure_threshold=100)  # high threshold so no flipping
    errors: list[Exception] = []

    def worker(i: int):
        try:
            if i % 2 == 0:
                cb.call("svc", lambda: "ok")
            else:
                with pytest.raises(RuntimeError):
                    cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    bs = cb.get_state("svc")
    # 25 failures recorded; last success may have reset to 0 — accept either
    assert bs is not None
    assert bs.state == STATE_CLOSED
