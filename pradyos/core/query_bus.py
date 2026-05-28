from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass
class QueryResult:
    query_name: str
    params: dict
    result: dict
    queried_at: float
    duration_ms: float
    success: bool
    error: str | None

    def to_dict(self) -> dict:
        return {
            "query_name": self.query_name,
            "params": dict(self.params),
            "result": dict(self.result),
            "queried_at": self.queried_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }


class QueryBus:
    HISTORY_LIMIT = 500

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], dict]] = {}
        self._history: deque[QueryResult] = deque(maxlen=self.HISTORY_LIMIT)
        self._lock = threading.Lock()

    # ── handler registry ─────────────────────────────────────────────────────

    def register(self, name: str, handler: Callable[[dict], dict]) -> None:
        with self._lock:
            self._handlers[name] = handler

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._handlers.pop(name, None) is not None

    def list_handlers(self) -> list[str]:
        with self._lock:
            return sorted(self._handlers.keys())

    # ── query ────────────────────────────────────────────────────────────────

    def query(self, name: str, params: dict | None = None) -> QueryResult:
        actual_params: dict = dict(params) if params else {}
        queried_at = time.time()

        with self._lock:
            handler = self._handlers.get(name)

        if handler is None:
            result = QueryResult(
                query_name=name,
                params=actual_params,
                result={},
                queried_at=queried_at,
                duration_ms=0.0,
                success=False,
                error=f"no handler registered for: {name}",
            )
            with self._lock:
                self._history.append(result)
            return result

        t0 = time.perf_counter()
        try:
            ret = handler(actual_params)
            duration_ms = (time.perf_counter() - t0) * 1000
            if not isinstance(ret, dict):
                ret = {"value": ret}
            result = QueryResult(
                query_name=name,
                params=actual_params,
                result=ret,
                queried_at=queried_at,
                duration_ms=duration_ms,
                success=True,
                error=None,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            result = QueryResult(
                query_name=name,
                params=actual_params,
                result={},
                queried_at=queried_at,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
            )

        with self._lock:
            self._history.append(result)
        return result

    # ── history ──────────────────────────────────────────────────────────────

    def history(self, limit: int = 50) -> list[QueryResult]:
        capped = max(0, min(self.HISTORY_LIMIT, int(limit)))
        with self._lock:
            snapshot = list(self._history)
        snapshot.reverse()  # newest first
        return snapshot[:capped]

    def clear_history(self) -> int:
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count
