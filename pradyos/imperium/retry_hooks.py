"""Resilience integration — Phase 7C.

Provides:
  CircuitBreaker — opens after N consecutive failures; resets after T seconds.
  apply_retry_policies() — wraps OracleClient.plan, TitanExecutor.execute,
                           and CampaignEngine.run_campaign with RetryPolicy.

Environment overrides
---------------------
  SOVEREIGN_CIRCUIT_THRESHOLD  — integer, consecutive failures to open circuit (default 5)
  SOVEREIGN_CIRCUIT_RESET_SEC  — float, seconds before circuit auto-resets (default 60)

Windows-safe: threading.Lock only, no signals, no AF_UNIX, no fork.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from pradyos.imperium.retry import RetryPolicy, retryable

log = logging.getLogger("pradyos.imperium.retry_hooks")

__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "apply_retry_policies",
]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED  = "closed"   # normal — calls pass through
    OPEN    = "open"     # tripped — calls fail immediately
    HALF    = "half"     # probing — one call let through to test recovery


class CircuitOpenError(RuntimeError):
    """Raised when a call is blocked by an open circuit breaker."""

    def __init__(self, name: str = "circuit") -> None:
        super().__init__(f"Circuit '{name}' is OPEN — call rejected")
        self.name = name


class CircuitBreaker:
    """Sliding-window circuit breaker.

    Parameters
    ----------
    threshold:        Number of consecutive failures that open the circuit.
    reset_after_sec:  Seconds the circuit stays open before transitioning
                      to HALF_OPEN for a probe attempt.
    name:             Friendly name (used in error messages and logs).

    Usage
    -----
    Wrap a callable::

        cb = CircuitBreaker(threshold=5, reset_after_sec=60)

        @cb.protect
        def call_oracle():
            ...

    Or call ``cb.call(fn, *args, **kwargs)`` directly.

    Environment overrides
    ---------------------
    SOVEREIGN_CIRCUIT_THRESHOLD — overrides *threshold* if set.
    SOVEREIGN_CIRCUIT_RESET_SEC — overrides *reset_after_sec* if set.
    """

    def __init__(
        self,
        threshold: int = 5,
        reset_after_sec: float = 60.0,
        name: str = "circuit",
    ) -> None:
        self._name = name
        self._threshold = threshold
        self._reset_after = reset_after_sec
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float | None = None

    # ------------------------------------------------------------------
    # Properties — readable externally
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition()
            return self._state

    @property
    def effective_threshold(self) -> int:
        env = os.environ.get("SOVEREIGN_CIRCUIT_THRESHOLD")
        if env:
            try:
                return max(1, int(env))
            except ValueError:
                log.warning("Invalid SOVEREIGN_CIRCUIT_THRESHOLD=%r — ignoring", env)
        return self._threshold

    @property
    def effective_reset(self) -> float:
        env = os.environ.get("SOVEREIGN_CIRCUIT_RESET_SEC")
        if env:
            try:
                return max(0.0, float(env))
            except ValueError:
                log.warning("Invalid SOVEREIGN_CIRCUIT_RESET_SEC=%r — ignoring", env)
        return self._reset_after

    # ------------------------------------------------------------------
    # Core call interface
    # ------------------------------------------------------------------

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Call *fn* through the breaker (synchronous)."""
        with self._lock:
            self._maybe_transition()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(self._name)
            # Allow the call (CLOSED or HALF)

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self._on_failure()
            raise

    async def call_async(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Call async *fn* through the breaker."""
        with self._lock:
            self._maybe_transition()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(self._name)

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self._on_failure()
            raise

    def protect(self, fn: Callable) -> Callable:
        """Decorator — wraps sync or async callable."""
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await self.call_async(fn, *args, **kwargs)
            return _async_wrapper
        else:
            @functools.wraps(fn)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return self.call(fn, *args, **kwargs)
            return _sync_wrapper

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _maybe_transition(self) -> None:
        """Called inside the lock — check if OPEN should move to HALF."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.effective_reset:
                self._state = CircuitState.HALF
                log.info(
                    "CircuitBreaker '%s': OPEN→HALF after %.1fs",
                    self._name, elapsed,
                )

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF:
                log.info("CircuitBreaker '%s': HALF→CLOSED (probe succeeded)", self._name)
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None

    def _on_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            threshold = self.effective_threshold
            if self._state == CircuitState.HALF:
                # Probe failed — reopen immediately
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                log.warning(
                    "CircuitBreaker '%s': HALF→OPEN (probe failed)", self._name
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._consecutive_failures >= threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                log.warning(
                    "CircuitBreaker '%s': CLOSED→OPEN after %d consecutive failures",
                    self._name, self._consecutive_failures,
                )

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED (admin use)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
        log.info("CircuitBreaker '%s': manually reset to CLOSED", self._name)

    def trip(self) -> None:
        """Manually open the circuit (for testing / emergency use)."""
        with self._lock:
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
        log.info("CircuitBreaker '%s': manually tripped to OPEN", self._name)

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self._name!r}, state={self._state.value}, "
            f"failures={self._consecutive_failures})"
        )


# ---------------------------------------------------------------------------
# Apply retry policies to subsystem methods
# ---------------------------------------------------------------------------

# Default circuit breakers (one per subsystem)
_oracle_cb  = CircuitBreaker(threshold=5, reset_after_sec=60.0, name="oracle")
_titan_cb   = CircuitBreaker(threshold=5, reset_after_sec=60.0, name="titan")
_campaign_cb = CircuitBreaker(threshold=5, reset_after_sec=60.0, name="campaign")


def apply_retry_policies(
    oracle_client: Any | None = None,
    titan_executor: Any | None = None,
    campaign_engine: Any | None = None,
) -> dict[str, CircuitBreaker]:
    """Wrap subsystem methods with RetryPolicy and CircuitBreaker.

    OracleClient.plan()       — up to 3 retries, 1s base delay
    TitanExecutor.execute()   — up to 2 retries, 0.5s base delay
    CampaignEngine.run_campaign() — up to 1 retry (resubmit failed nodes only)

    Returns a dict of the circuit breakers keyed by subsystem name, so the
    caller can inspect / override them.
    """
    if oracle_client is not None:
        _apply_oracle_retry(oracle_client)

    if titan_executor is not None:
        _apply_titan_retry(titan_executor)

    if campaign_engine is not None:
        _apply_campaign_retry(campaign_engine)

    return {
        "oracle": _oracle_cb,
        "titan": _titan_cb,
        "campaign": _campaign_cb,
    }


# ---------------------------------------------------------------------------
# Per-subsystem wrappers
# ---------------------------------------------------------------------------

def _apply_oracle_retry(client: Any) -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_s=1.0, jitter=False)
    original = getattr(client, "plan", None)
    if original is None:
        return

    @functools.wraps(original)
    async def _plan_with_retry(*args: Any, **kwargs: Any) -> Any:
        attempt = [0]

        async def _once() -> Any:
            return await original(*args, **kwargs)

        # Manual retry loop to integrate circuit breaker
        last_exc: Exception | None = None
        max_attempts = policy.effective_max_attempts()
        for i in range(max_attempts):
            delay = policy.delay_for_attempt(i)
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await _oracle_cb.call_async(_once)
            except CircuitOpenError:
                raise
            except Exception as exc:
                last_exc = exc
                log.debug("oracle.plan retry %d/%d: %s", i + 1, max_attempts, exc)
        raise last_exc  # type: ignore[misc]

    client.plan = _plan_with_retry


def _apply_titan_retry(executor: Any) -> None:
    policy = RetryPolicy(max_attempts=2, base_delay_s=0.5, jitter=False)
    original = getattr(executor, "execute", None)
    if original is None:
        return

    @functools.wraps(original)
    def _execute_with_retry(*args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        max_attempts = policy.effective_max_attempts()
        for i in range(max_attempts):
            delay = policy.delay_for_attempt(i)
            if delay > 0:
                time.sleep(delay)
            try:
                return _titan_cb.call(original, *args, **kwargs)
            except CircuitOpenError:
                raise
            except Exception as exc:
                last_exc = exc
                log.debug("titan.execute retry %d/%d: %s", i + 1, max_attempts, exc)
        raise last_exc  # type: ignore[misc]

    executor.execute = _execute_with_retry


def _apply_campaign_retry(engine: Any) -> None:
    """Wrap run_campaign with a single retry at the campaign level.

    Note: we only retry the full campaign once (not individual nodes) to
    avoid re-running already-succeeded nodes inadvertently.
    """
    original = getattr(engine, "run_campaign", None)
    if original is None:
        return

    @functools.wraps(original)
    async def _run_with_retry(campaign: Any) -> Any:
        last_exc: Exception | None = None
        max_attempts = 2  # 1 initial + 1 retry
        for i in range(max_attempts):
            if i > 0:
                await asyncio.sleep(0.5)
                log.info("campaign.run_campaign retry attempt %d", i + 1)
            try:
                return await _campaign_cb.call_async(original, campaign)
            except CircuitOpenError:
                raise
            except Exception as exc:
                last_exc = exc
                log.debug("campaign retry %d/%d: %s", i + 1, max_attempts, exc)
        raise last_exc  # type: ignore[misc]

    engine.run_campaign = _run_with_retry
