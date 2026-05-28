from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class GuardRecord:
    name: str
    timeout: float
    elapsed: float
    outcome: str  # 'success' | 'timeout' | 'error'
    error: str | None
    ts: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "timeout": self.timeout,
            "elapsed": self.elapsed,
            "outcome": self.outcome,
            "error": self.error,
            "ts": self.ts,
        }


class TimeoutExpiredError(RuntimeError):
    """Raised when a call does not complete within the deadline."""


class TimeoutGuard:
    def __init__(self, default_timeout: float = 5.0) -> None:
        self._default_timeout = float(default_timeout)
        self._history: dict[str, list[GuardRecord]] = {}
        self._lock = threading.Lock()

    @property
    def default_timeout(self) -> float:
        return self._default_timeout

    # ── primary API ──────────────────────────────────────────────────────────

    def execute(
        self,
        name: str,
        fn: Callable,
        *args,
        timeout: float | None = None,
        **kwargs,
    ) -> Any:
        effective = float(timeout) if timeout is not None else self._default_timeout
        start = time.time()

        # Fresh single-worker executor per call — no shared state between
        # callers, and a timed-out task is left to finish in its own thread
        # while we return promptly via shutdown(wait=False).
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(fn, *args, **kwargs)
            try:
                result = future.result(timeout=effective)
            except FuturesTimeoutError:
                elapsed = time.time() - start
                future.cancel()
                self._append(GuardRecord(
                    name=name,
                    timeout=effective,
                    elapsed=elapsed,
                    outcome="timeout",
                    error=None,
                    ts=start,
                ))
                raise TimeoutExpiredError(
                    f"{name!r} timed out after {effective}s"
                )
            except BaseException as exc:
                elapsed = time.time() - start
                self._append(GuardRecord(
                    name=name,
                    timeout=effective,
                    elapsed=elapsed,
                    outcome="error",
                    error=str(exc),
                    ts=start,
                ))
                raise

            elapsed = time.time() - start
            self._append(GuardRecord(
                name=name,
                timeout=effective,
                elapsed=elapsed,
                outcome="success",
                error=None,
                ts=start,
            ))
            return result
        finally:
            # Don't wait for stragglers — a timed-out task may still be running.
            executor.shutdown(wait=False)

    # ── history helpers ──────────────────────────────────────────────────────

    def _append(self, record: GuardRecord) -> None:
        with self._lock:
            self._history.setdefault(record.name, []).append(record)

    def get_history(self, name: str) -> list[GuardRecord]:
        with self._lock:
            return list(self._history.get(name, []))

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
