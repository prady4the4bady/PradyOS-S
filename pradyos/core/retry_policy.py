from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class AttemptRecord:
    name: str
    attempt: int
    outcome: str  # "success" | "failure" | "exhausted"
    elapsed: float
    error: str | None
    ts: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "attempt": self.attempt,
            "outcome": self.outcome,
            "elapsed": self.elapsed,
            "error": self.error,
            "ts": self.ts,
        }


class RetryPolicy:
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: float = 0.1,
        retry_on: tuple = (Exception,),
    ) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._base_delay = float(base_delay)
        self._backoff_factor = float(backoff_factor)
        self._jitter = float(jitter)
        self._retry_on = retry_on
        self._history: dict[str, list[AttemptRecord]] = {}
        self._lock = threading.Lock()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _append_record(self, name: str, rec: AttemptRecord) -> None:
        with self._lock:
            self._history.setdefault(name, []).append(rec)

    def _set_last_outcome(self, name: str, outcome: str) -> None:
        with self._lock:
            records = self._history.get(name)
            if records:
                records[-1].outcome = outcome

    def _compute_sleep(self, attempt: int) -> float:
        """Sleep duration before the NEXT attempt (1-indexed attempt that
        just failed). attempt=1 → base_delay * 1, attempt=2 → base_delay * factor, etc."""
        delay = self._base_delay * (self._backoff_factor ** (attempt - 1))
        if self._jitter > 0:
            delay += random.uniform(-self._jitter, self._jitter)
        return max(0.0, delay)

    # ── primary API ──────────────────────────────────────────────────────────

    def execute(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        last_exc: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                elapsed = time.perf_counter() - t0
                rec = AttemptRecord(
                    name=name,
                    attempt=attempt,
                    outcome="failure",
                    elapsed=elapsed,
                    error=repr(exc),
                    ts=time.time(),
                )
                self._append_record(name, rec)

                # Non-retryable exception → re-raise immediately
                if not isinstance(exc, self._retry_on):
                    raise

                last_exc = exc
                if attempt >= self._max_attempts:
                    self._set_last_outcome(name, "exhausted")
                    raise

                # Sleep with backoff + jitter before next attempt
                time.sleep(self._compute_sleep(attempt))
                continue

            # Success
            elapsed = time.perf_counter() - t0
            rec = AttemptRecord(
                name=name,
                attempt=attempt,
                outcome="success",
                elapsed=elapsed,
                error=None,
                ts=time.time(),
            )
            self._append_record(name, rec)
            return result

        # Unreachable — every path above either returns or raises.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("retry policy exhausted without exception")

    # ── introspection ────────────────────────────────────────────────────────

    def get_history(self, name: str) -> list[dict]:
        with self._lock:
            records = self._history.get(name)
            if records is None:
                return []
            return [r.to_dict() for r in records]

    def clear_history(self, name: str) -> bool:
        with self._lock:
            if name not in self._history:
                return False
            del self._history[name]
            return True

    def list_names(self) -> list[str]:
        with self._lock:
            return sorted(self._history.keys())

    def count(self, name: str | None = None) -> int:
        with self._lock:
            if name is not None:
                return len(self._history.get(name, []))
            return sum(len(v) for v in self._history.values())
