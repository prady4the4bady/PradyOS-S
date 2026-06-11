from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

STATE_CLOSED = "CLOSED"
STATE_OPEN = "OPEN"
STATE_HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when call() is invoked on a breaker in the OPEN state."""


@dataclass
class BreakerState:
    name: str
    state: str
    failure_count: int
    last_failure_at: float | None
    opened_at: float | None
    # Internal probe counter — not exposed in to_dict() per spec.
    half_open_probes: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_at": self.last_failure_at,
            "opened_at": self.opened_at,
        }


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max
        self._states: dict[str, BreakerState] = {}
        self._lock = threading.Lock()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_or_create_locked(self, name: str) -> BreakerState:
        """Caller holds self._lock."""
        bs = self._states.get(name)
        if bs is None:
            bs = BreakerState(
                name=name,
                state=STATE_CLOSED,
                failure_count=0,
                last_failure_at=None,
                opened_at=None,
                half_open_probes=0,
            )
            self._states[name] = bs
        return bs

    # ── primary API ──────────────────────────────────────────────────────────

    def call(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        with self._lock:
            bs = self._get_or_create_locked(name)
            # OPEN → maybe HALF_OPEN
            if bs.state == STATE_OPEN:
                opened = bs.opened_at or 0.0
                if (time.time() - opened) >= self._recovery_timeout:
                    bs.state = STATE_HALF_OPEN
                    bs.half_open_probes = 0
                else:
                    raise CircuitOpenError(f"breaker {name!r} is OPEN")
            # Snapshot current state for the call below
            state_at_entry = bs.state

        # Execute fn OUTSIDE the lock so a slow fn doesn't block other callers.
        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                bs.failure_count += 1
                bs.last_failure_at = time.time()
                if state_at_entry == STATE_CLOSED:
                    if bs.failure_count >= self._failure_threshold:
                        bs.state = STATE_OPEN
                        bs.opened_at = time.time()
                elif state_at_entry == STATE_HALF_OPEN:
                    bs.half_open_probes += 1
                    if bs.half_open_probes >= self._half_open_max:
                        bs.state = STATE_OPEN
                        bs.opened_at = time.time()
                        bs.half_open_probes = 0
            raise

        # Success
        with self._lock:
            if state_at_entry == STATE_CLOSED:
                bs.failure_count = 0
            elif state_at_entry == STATE_HALF_OPEN:
                bs.state = STATE_CLOSED
                bs.failure_count = 0
                bs.opened_at = None
                bs.half_open_probes = 0
        return result

    def get_state(self, name: str) -> BreakerState | None:
        with self._lock:
            return self._states.get(name)

    def reset(self, name: str) -> bool:
        with self._lock:
            bs = self._states.get(name)
            if bs is None:
                return False
            bs.state = STATE_CLOSED
            bs.failure_count = 0
            bs.last_failure_at = None
            bs.opened_at = None
            bs.half_open_probes = 0
            return True

    def list_breakers(self) -> list[dict]:
        with self._lock:
            states = sorted(self._states.values(), key=lambda s: s.name)
        return [s.to_dict() for s in states]

    def count(self) -> int:
        with self._lock:
            return len(self._states)
