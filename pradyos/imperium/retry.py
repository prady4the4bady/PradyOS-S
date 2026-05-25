"""RetryPolicy and @retryable decorator — Phase 6 Resilience Layer.

Supports both sync and async target functions.
Exponential back-off with optional jitter.
Emits an AuditEvent on each retry attempt (if an EventAuditLog is injected).
SOVEREIGN_RETRY_MAX env var overrides max_attempts at runtime.

Windows-safe: no fork(), no signal, no os.killpg().
"""

from __future__ import annotations

import asyncio
import functools
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("pradyos.imperium.retry")

# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Configuration for the retry behaviour of a callable."""

    max_attempts:    int   = 3
    base_delay_s:    float = 1.0
    max_delay_s:     float = 60.0
    exponential_base: float = 2.0
    jitter:          bool  = True

    def effective_max_attempts(self) -> int:
        """Return max_attempts, allowing SOVEREIGN_RETRY_MAX env override."""
        env_val = os.environ.get("SOVEREIGN_RETRY_MAX")
        if env_val is not None:
            try:
                return max(1, int(env_val))
            except ValueError:
                log.warning("Invalid SOVEREIGN_RETRY_MAX=%r — ignoring", env_val)
        return self.max_attempts

    def delay_for_attempt(self, attempt: int) -> float:
        """Return sleep duration (seconds) before *attempt* (0-based)."""
        if attempt == 0:
            return 0.0
        raw = self.base_delay_s * math.pow(self.exponential_base, attempt - 1)
        delay = min(raw, self.max_delay_s)
        if self.jitter:
            delay = random.uniform(0.0, delay)
        return delay


# ---------------------------------------------------------------------------
# Default policy singleton
# ---------------------------------------------------------------------------

DEFAULT_POLICY = RetryPolicy()


# ---------------------------------------------------------------------------
# @retryable decorator
# ---------------------------------------------------------------------------


def retryable(
    policy: RetryPolicy | None = None,
    audit_log: Any = None,  # Optional[EventAuditLog]
) -> Callable:
    """Decorator factory — wraps sync or async function with retry logic.

    Usage::

        @retryable(RetryPolicy(max_attempts=5, base_delay_s=0.5))
        def fetch_data(url):
            ...

        @retryable(RetryPolicy(max_attempts=3), audit_log=my_audit_log)
        async def call_llm(prompt):
            ...

    After exhausting all attempts, re-raises the last exception.
    """
    _policy = policy or DEFAULT_POLICY

    def decorator(fn: Callable) -> Callable:
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _run_async(fn, args, kwargs, _policy, audit_log)
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return _run_sync(fn, args, kwargs, _policy, audit_log)
            return sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# Internal retry runners
# ---------------------------------------------------------------------------


def _emit_retry_event(
    audit_log: Any,
    fn_name: str,
    attempt: int,
    max_attempts: int,
    exc: Exception,
) -> None:
    """Emit an AuditEvent to *audit_log* if provided and supports append()."""
    if audit_log is None:
        return
    try:
        from pradyos.core.audit import AuditCategory, AuditEvent  # lazy import
        event = AuditEvent(
            category=AuditCategory.SYSTEM,
            actor="retry_engine",
            action=f"retry:{fn_name}",
            payload={
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        audit_log.append(event)
    except Exception as e:  # noqa: BLE001 — never crash the retry loop
        log.debug("Failed to emit retry audit event: %s", e)


def _run_sync(
    fn: Callable,
    args: tuple,
    kwargs: dict,
    policy: RetryPolicy,
    audit_log: Any,
) -> Any:
    max_attempts = policy.effective_max_attempts()
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        delay = policy.delay_for_attempt(attempt)
        if delay > 0:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.debug(
                "Retry attempt %d/%d for %s failed: %s",
                attempt + 1, max_attempts, fn.__name__, exc,
            )
            if attempt < max_attempts - 1:
                _emit_retry_event(audit_log, fn.__name__, attempt + 1, max_attempts, exc)

    raise last_exc  # type: ignore[misc]


async def _run_async(
    fn: Callable,
    args: tuple,
    kwargs: dict,
    policy: RetryPolicy,
    audit_log: Any,
) -> Any:
    max_attempts = policy.effective_max_attempts()
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        delay = policy.delay_for_attempt(attempt)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.debug(
                "Async retry attempt %d/%d for %s failed: %s",
                attempt + 1, max_attempts, fn.__name__, exc,
            )
            if attempt < max_attempts - 1:
                _emit_retry_event(audit_log, fn.__name__, attempt + 1, max_attempts, exc)

    raise last_exc  # type: ignore[misc]
