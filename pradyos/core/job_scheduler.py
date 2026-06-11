"""Phase 68 — Sovereign Scheduler.

NOTE: Filename is job_scheduler.py (not scheduler.py) because
pradyos/core/scheduler.py is already occupied by Phase 38's TaskScheduler.
The class here is named Scheduler per the Phase 68 spec; this is fine
because it lives in a different module.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Job:
    job_id: str
    name: str
    run_at: float
    interval_seconds: float | None
    payload: dict
    status: str  # pending | running | completed | failed | cancelled
    last_run_at: float | None
    next_run_at: float | None
    result: dict | None
    error: str | None
    created_at: float

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "run_at": self.run_at,
            "interval_seconds": self.interval_seconds,
            "payload": dict(self.payload),
            "status": self.status,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "result": dict(self.result) if self.result is not None else None,
            "error": self.error,
            "created_at": self.created_at,
        }


class Scheduler:
    CAPACITY = 1000

    def __init__(self) -> None:
        self._jobs: deque[Job] = deque(maxlen=self.CAPACITY)
        self._index: dict[str, Job] = {}
        self._handlers: dict[str, Callable[[dict], dict]] = {}
        self._lock = threading.Lock()

    # ── handler registry ─────────────────────────────────────────────────────

    def register_handler(self, name: str, handler: Callable[[dict], dict]) -> None:
        with self._lock:
            self._handlers[name] = handler

    # ── schedule / cancel ────────────────────────────────────────────────────

    def schedule(
        self,
        name: str,
        run_at: float,
        payload: dict | None = None,
        interval_seconds: float | None = None,
    ) -> Job:
        job = Job(
            job_id=str(uuid.uuid4()),
            name=name,
            run_at=float(run_at),
            interval_seconds=(float(interval_seconds) if interval_seconds is not None else None),
            payload=dict(payload) if payload else {},
            status="pending",
            last_run_at=None,
            next_run_at=float(run_at),
            result=None,
            error=None,
            created_at=time.time(),
        )
        with self._lock:
            # Sync the index with deque eviction.
            evicted: Job | None = None
            if len(self._jobs) == self._jobs.maxlen:
                evicted = self._jobs[0]
            self._jobs.append(job)
            self._index[job.job_id] = job
            if evicted is not None and evicted.job_id != job.job_id:
                self._index.pop(evicted.job_id, None)
        return job

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._index.get(job_id)
            if job is None or job.status != "pending":
                return False
            job.status = "cancelled"
            return True

    # ── tick ─────────────────────────────────────────────────────────────────

    def tick(self, now: float | None = None) -> list[Job]:
        if now is None:
            now = time.time()

        # Snapshot due jobs + their handlers under the lock — execute outside.
        with self._lock:
            due: list[Job] = []
            for job in self._jobs:
                if job.status != "pending":
                    continue
                if job.next_run_at is None or job.next_run_at > now:
                    continue
                job.status = "running"  # mark before releasing the lock
                due.append(job)
            handlers_snapshot = dict(self._handlers)

        executed: list[Job] = []
        for job in due:
            handler = handlers_snapshot.get(job.name)
            if handler is None:
                with self._lock:
                    job.status = "failed"
                    job.error = "no handler registered"
                    job.last_run_at = now
                executed.append(job)
                continue

            try:
                ret = handler(dict(job.payload))
                if not isinstance(ret, dict):
                    ret = {"value": ret}
                with self._lock:
                    job.last_run_at = now
                    job.result = ret
                    job.error = None
                    job.status = "completed"
                    if job.interval_seconds is not None:
                        job.status = "pending"
                        job.next_run_at = now + job.interval_seconds
            except Exception as exc:
                with self._lock:
                    job.status = "failed"
                    job.error = str(exc)
                    job.last_run_at = now

            executed.append(job)

        return executed

    # ── introspection ────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._index.get(job_id)

    def list_jobs(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Job]:
        capped = max(0, min(self.CAPACITY, int(limit)))
        with self._lock:
            snapshot = list(self._jobs)
        if status is not None:
            snapshot = [j for j in snapshot if j.status == status]
        snapshot.sort(key=lambda j: j.created_at, reverse=True)
        return snapshot[:capped]

    def count(self, status: str | None = None) -> int:
        with self._lock:
            if status is None:
                return len(self._jobs)
            return sum(1 for j in self._jobs if j.status == status)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._index.pop(job_id, None)
            if job is None:
                return False
            try:
                self._jobs.remove(job)
            except ValueError:
                pass
            return True
