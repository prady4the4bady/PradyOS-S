"""Tests for Phase 7C: retry_hooks.py (CircuitBreaker + apply_retry_policies)"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import MagicMock, call

import pytest

from pradyos.imperium.retry_hooks import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    apply_retry_policies,
)


# ---------------------------------------------------------------------------
# 1. Circuit starts CLOSED
# ---------------------------------------------------------------------------

def test_circuit_starts_closed():
    cb = CircuitBreaker(threshold=3, reset_after_sec=60.0)
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 2. Circuit opens after threshold failures
# ---------------------------------------------------------------------------

def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(threshold=3, reset_after_sec=60.0)

    def bad():
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(bad)

    assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# 3. Open circuit rejects immediately with CircuitOpenError
# ---------------------------------------------------------------------------

def test_open_circuit_rejects():
    cb = CircuitBreaker(threshold=2, reset_after_sec=60.0)
    cb.trip()
    assert cb.state == CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "never called")


# ---------------------------------------------------------------------------
# 4. Circuit resets to HALF after reset_after_sec
# ---------------------------------------------------------------------------

def test_circuit_resets_to_half_after_timeout():
    cb = CircuitBreaker(threshold=2, reset_after_sec=0.05)
    cb.trip()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.1)
    # Reading state triggers the transition check
    assert cb.state == CircuitState.HALF


# ---------------------------------------------------------------------------
# 5. HALF state: successful probe closes the circuit
# ---------------------------------------------------------------------------

def test_half_state_successful_probe_closes():
    cb = CircuitBreaker(threshold=2, reset_after_sec=0.05)
    cb.trip()
    time.sleep(0.1)
    assert cb.state == CircuitState.HALF

    cb.call(lambda: "ok")  # probe succeeds
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 6. HALF state: failed probe reopens the circuit
# ---------------------------------------------------------------------------

def test_half_state_failed_probe_reopens():
    cb = CircuitBreaker(threshold=2, reset_after_sec=0.05)
    cb.trip()
    time.sleep(0.1)
    assert cb.state == CircuitState.HALF

    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("probe failed")))

    assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# 7. Manual reset works
# ---------------------------------------------------------------------------

def test_manual_reset():
    cb = CircuitBreaker(threshold=2, reset_after_sec=60.0)
    cb.trip()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 8. SOVEREIGN_CIRCUIT_THRESHOLD env override
# ---------------------------------------------------------------------------

def test_env_threshold_override(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_CIRCUIT_THRESHOLD", "2")
    cb = CircuitBreaker(threshold=10, reset_after_sec=60.0)
    assert cb.effective_threshold == 2


# ---------------------------------------------------------------------------
# 9. SOVEREIGN_CIRCUIT_RESET_SEC env override
# ---------------------------------------------------------------------------

def test_env_reset_sec_override(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_CIRCUIT_RESET_SEC", "0.01")
    cb = CircuitBreaker(threshold=5, reset_after_sec=999.0)
    assert cb.effective_reset == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# 10. Async call_async works
# ---------------------------------------------------------------------------

def test_circuit_async_call():
    cb = CircuitBreaker(threshold=3, reset_after_sec=60.0)

    async def good() -> str:
        return "ok"

    result = asyncio.run(cb.call_async(good))
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 11. protect() decorator on sync function
# ---------------------------------------------------------------------------

def test_protect_decorator_sync():
    cb = CircuitBreaker(threshold=3, reset_after_sec=60.0)
    calls = []

    @cb.protect
    def fn(x):
        calls.append(x)
        return x * 2

    assert fn(3) == 6
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# 12. apply_retry_policies returns circuit breakers dict
# ---------------------------------------------------------------------------

def test_apply_retry_policies_returns_cbs():
    result = apply_retry_policies()
    assert "oracle" in result
    assert "titan" in result
    assert "campaign" in result
    assert isinstance(result["oracle"], CircuitBreaker)


# ---------------------------------------------------------------------------
# 13. apply_retry_policies wraps titan execute with retry
# ---------------------------------------------------------------------------

def test_titan_execute_retried():
    executor = MagicMock()
    call_count = [0]

    def flaky_execute(instr):
        call_count[0] += 1
        if call_count[0] < 2:
            raise RuntimeError("transient failure")
        return MagicMock(succeeded=True)

    executor.execute = flaky_execute
    apply_retry_policies(titan_executor=executor)

    instr = MagicMock()
    result = executor.execute(instr)
    assert call_count[0] == 2  # failed once, succeeded on retry


# ---------------------------------------------------------------------------
# 14. consecutive successes keep circuit closed
# ---------------------------------------------------------------------------

def test_consecutive_successes_keep_closed():
    cb = CircuitBreaker(threshold=3, reset_after_sec=60.0)
    for _ in range(10):
        cb.call(lambda: "ok")
    assert cb.state == CircuitState.CLOSED
    assert cb._consecutive_failures == 0
