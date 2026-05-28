from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SagaRun:
    saga_id: str
    saga_name: str
    steps: list[str]
    status: str  # "pending" | "running" | "completed" | "failed"
    current_step: int
    started_at: float
    finished_at: float | None
    payload_trace: list[dict]
    error: str | None

    def to_dict(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "steps": list(self.steps),
            "status": self.status,
            "current_step": self.current_step,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "payload_trace": [dict(e) for e in self.payload_trace],
            "error": self.error,
        }


class SagaOrchestrator:
    HISTORY_LIMIT = 200

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], dict]] = {}
        self._runs: deque[SagaRun] = deque(maxlen=self.HISTORY_LIMIT)
        self._index: dict[str, SagaRun] = {}
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

    # ── internal helpers ─────────────────────────────────────────────────────

    def _store_run(self, run: SagaRun) -> None:
        """Append run to deque + index; if deque overflows, drop oldest from index too."""
        with self._lock:
            # If deque is full, the oldest will be discarded by maxlen logic.
            # Capture which run would be evicted so we keep the index consistent.
            evicted: SagaRun | None = None
            if len(self._runs) == self._runs.maxlen:
                evicted = self._runs[0]
            self._runs.append(run)
            self._index[run.saga_id] = run
            if evicted is not None and evicted.saga_id != run.saga_id:
                self._index.pop(evicted.saga_id, None)

    # ── run ──────────────────────────────────────────────────────────────────

    def run(
        self,
        saga_name: str,
        steps: list[str],
        initial_payload: dict | None = None,
    ) -> SagaRun:
        saga_run = SagaRun(
            saga_id=str(uuid.uuid4()),
            saga_name=saga_name,
            steps=list(steps),
            status="pending",
            current_step=0,
            started_at=time.time(),
            finished_at=None,
            payload_trace=[],
            error=None,
        )
        self._store_run(saga_run)

        # Snapshot the handler map under lock — then execute OUTSIDE the lock
        # so a handler that re-enters the orchestrator (e.g. register/unregister)
        # never deadlocks.
        with self._lock:
            handlers_snapshot = dict(self._handlers)

        saga_run.status = "running"
        payload: dict = dict(initial_payload) if initial_payload else {}

        for i, step_name in enumerate(saga_run.steps):
            saga_run.current_step = i
            handler = handlers_snapshot.get(step_name)

            if handler is None:
                saga_run.payload_trace.append({
                    "step": step_name,
                    "input": dict(payload),
                    "error": f"no handler: {step_name}",
                })
                saga_run.status = "failed"
                saga_run.error = f"no handler: {step_name}"
                saga_run.finished_at = time.time()
                return saga_run

            step_input = dict(payload)
            try:
                output = handler(step_input)
            except Exception as exc:
                saga_run.payload_trace.append({
                    "step": step_name,
                    "input": step_input,
                    "error": str(exc),
                })
                saga_run.status = "failed"
                saga_run.error = str(exc)
                saga_run.finished_at = time.time()
                return saga_run

            if not isinstance(output, dict):
                output = {"value": output}
            saga_run.payload_trace.append({
                "step": step_name,
                "input": step_input,
                "output": dict(output),
            })
            payload = output  # chain: next step's input

        saga_run.status = "completed"
        saga_run.finished_at = time.time()
        return saga_run

    # ── introspection ────────────────────────────────────────────────────────

    def get(self, saga_id: str) -> SagaRun | None:
        with self._lock:
            return self._index.get(saga_id)

    def list_runs(self, limit: int = 50) -> list[SagaRun]:
        capped = max(0, min(self.HISTORY_LIMIT, int(limit)))
        with self._lock:
            snapshot = list(self._runs)
        snapshot.reverse()  # most-recent first
        return snapshot[:capped]

    def clear(self) -> int:
        with self._lock:
            count = len(self._runs)
            self._runs.clear()
            self._index.clear()
            return count
