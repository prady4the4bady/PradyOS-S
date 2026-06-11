from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class CommandResult:
    command_name: str
    payload: dict
    result: dict
    dispatched_at: float
    duration_ms: float
    success: bool
    error: str | None

    def to_dict(self) -> dict:
        return {
            "command_name": self.command_name,
            "payload": dict(self.payload),
            "result": dict(self.result),
            "dispatched_at": self.dispatched_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }


class CommandBus:
    HISTORY_LIMIT = 500

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], dict]] = {}
        self._history: deque[CommandResult] = deque(maxlen=self.HISTORY_LIMIT)
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

    # ── dispatch ─────────────────────────────────────────────────────────────

    def dispatch(self, name: str, payload: dict | None = None) -> CommandResult:
        actual_payload: dict = dict(payload) if payload else {}
        dispatched_at = time.time()

        with self._lock:
            handler = self._handlers.get(name)

        if handler is None:
            result = CommandResult(
                command_name=name,
                payload=actual_payload,
                result={},
                dispatched_at=dispatched_at,
                duration_ms=0.0,
                success=False,
                error=f"no handler registered for: {name}",
            )
            with self._lock:
                self._history.append(result)
            return result

        t0 = time.perf_counter()
        try:
            ret = handler(actual_payload)
            duration_ms = (time.perf_counter() - t0) * 1000
            if not isinstance(ret, dict):
                ret = {"value": ret}
            result = CommandResult(
                command_name=name,
                payload=actual_payload,
                result=ret,
                dispatched_at=dispatched_at,
                duration_ms=duration_ms,
                success=True,
                error=None,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            result = CommandResult(
                command_name=name,
                payload=actual_payload,
                result={},
                dispatched_at=dispatched_at,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
            )

        with self._lock:
            self._history.append(result)
        return result

    # ── history ──────────────────────────────────────────────────────────────

    def history(self, limit: int = 50) -> list[CommandResult]:
        capped = max(0, min(self.HISTORY_LIMIT, int(limit)))
        with self._lock:
            snapshot = list(self._history)
        # newest first
        snapshot.reverse()
        return snapshot[:capped]

    def clear_history(self) -> int:
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count
