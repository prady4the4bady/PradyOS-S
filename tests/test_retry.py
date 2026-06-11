"""Tests for Phase 6 RetryPolicy and @retryable decorator.

Covers: sync retry, async retry, exhaustion, jitter, env override.
"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import MagicMock

import pytest

from pradyos.imperium.retry import DEFAULT_POLICY, RetryPolicy, retryable


# ---------------------------------------------------------------------------
# RetryPolicy dataclass
# ---------------------------------------------------------------------------


def test_retry_policy_defaults():
    p = RetryPolicy()
    assert p.max_attempts == 3
    assert p.base_delay_s == 1.0
    assert p.max_delay_s == 60.0
    assert p.exponential_base == 2.0
    assert p.jitter is True


def test_retry_policy_delay_for_attempt_zero():
    p = RetryPolicy(base_delay_s=1.0, jitter=False)
    assert p.delay_for_attempt(0) == 0.0


def test_retry_policy_delay_exponential():
    p = RetryPolicy(base_delay_s=1.0, exponential_base=2.0, max_delay_s=100.0, jitter=False)
    assert p.delay_for_attempt(1) == pytest.approx(1.0)
    assert p.delay_for_attempt(2) == pytest.approx(2.0)
    assert p.delay_for_attempt(3) == pytest.approx(4.0)


def test_retry_policy_delay_capped_at_max():
    p = RetryPolicy(base_delay_s=1.0, exponential_base=2.0, max_delay_s=3.0, jitter=False)
    assert p.delay_for_attempt(10) == pytest.approx(3.0)


def test_retry_policy_jitter_within_range():
    p = RetryPolicy(base_delay_s=1.0, exponential_base=2.0, max_delay_s=100.0, jitter=True)
    for _ in range(20):
        d = p.delay_for_attempt(3)  # would be 4.0 without jitter
        assert 0.0 <= d <= 4.0


# ---------------------------------------------------------------------------
# SOVEREIGN_RETRY_MAX env override
# ---------------------------------------------------------------------------


def test_retry_policy_env_override(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_RETRY_MAX", "7")
    p = RetryPolicy(max_attempts=3)
    assert p.effective_max_attempts() == 7


def test_retry_policy_env_override_invalid(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_RETRY_MAX", "not_a_number")
    p = RetryPolicy(max_attempts=3)
    assert p.effective_max_attempts() == 3  # falls back to field


def test_retry_policy_no_env_override(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_RETRY_MAX", raising=False)
    p = RetryPolicy(max_attempts=5)
    assert p.effective_max_attempts() == 5


# ---------------------------------------------------------------------------
# @retryable — sync
# ---------------------------------------------------------------------------


def test_retryable_sync_succeeds_first_try():
    calls = []

    @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0))
    def fn():
        calls.append(1)
        return "ok"

    result = fn()
    assert result == "ok"
    assert calls == [1]


def test_retryable_sync_retries_and_succeeds():
    calls = []

    @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0, jitter=False))
    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("not yet")
        return "done"

    result = fn()
    assert result == "done"
    assert len(calls) == 3


def test_retryable_sync_exhaustion():
    calls = []

    @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0, jitter=False))
    def fn():
        calls.append(1)
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        fn()
    assert len(calls) == 3


def test_retryable_sync_raises_last_exception():
    attempts = []

    @retryable(RetryPolicy(max_attempts=2, base_delay_s=0.0, jitter=False))
    def fn():
        attempts.append(len(attempts))
        raise ValueError(f"attempt {attempts[-1]}")

    with pytest.raises(ValueError, match="attempt 1"):
        fn()


# ---------------------------------------------------------------------------
# @retryable — async
# ---------------------------------------------------------------------------


def test_retryable_async_succeeds():
    calls = []

    @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0, jitter=False))
    async def fn():
        calls.append(1)
        return "async_ok"

    result = asyncio.run(fn())
    assert result == "async_ok"
    assert calls == [1]


def test_retryable_async_retries_and_succeeds():
    calls = []

    @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0, jitter=False))
    async def fn():
        calls.append(1)
        if len(calls) < 2:
            raise IOError("transient")
        return "async_done"

    result = asyncio.run(fn())
    assert result == "async_done"
    assert len(calls) == 2


def test_retryable_async_exhaustion():
    calls = []

    @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0, jitter=False))
    async def fn():
        calls.append(1)
        raise ConnectionError("always")

    with pytest.raises(ConnectionError):
        asyncio.run(fn())
    assert len(calls) == 3


# ---------------------------------------------------------------------------
# Audit emission on retry
# ---------------------------------------------------------------------------


def test_retryable_emits_audit_on_retry():
    from pradyos.core.audit import AuditCategory, AuditEvent, EventAuditLog
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        audit = EventAuditLog(path=pathlib.Path(td) / "retry_audit.jsonl")
        calls = []

        @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0, jitter=False), audit_log=audit)
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("retry me")
            return "ok"

        result = flaky()
        assert result == "ok"
        # Should have 2 retry events (attempt 1 and 2 fail; attempt 3 succeeds)
        events = audit.tail(10)
        assert len(events) == 2
        for ev in events:
            assert ev.actor == "retry_engine"
            assert "flaky" in ev.action


def test_retryable_no_audit_on_success():
    from pradyos.core.audit import EventAuditLog
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        audit = EventAuditLog(path=pathlib.Path(td) / "a.jsonl")

        @retryable(RetryPolicy(max_attempts=3, base_delay_s=0.0), audit_log=audit)
        def ok():
            return 42

        ok()
        assert len(audit) == 0
