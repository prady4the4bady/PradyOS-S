from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ScheduledTask:
    name: str
    interval_seconds: float
    next_run_at: float
    last_run: float | None
    enabled: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "next_run_at": self.next_run_at,
            "last_run": self.last_run,
            "enabled": self.enabled,
        }


@dataclass
class TaskRun:
    task_name: str
    ran_at: float
    duration_ms: float
    success: bool
    error: str | None

    def to_dict(self) -> dict:
        return {
            "task_name": self.task_name,
            "ran_at": self.ran_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }


class TaskScheduler:
    def __init__(self, max_log: int = 1000) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._fns: dict[str, Callable[[], Any]] = {}
        self._log: collections.deque[TaskRun] = collections.deque(maxlen=max_log)
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        interval_seconds: float,
        fn: Callable[[], Any],
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            interval_seconds=interval_seconds,
            next_run_at=time.time() + interval_seconds,
            last_run=None,
            enabled=True,
        )
        with self._lock:
            self._tasks[name] = task
            self._fns[name] = fn
        return task

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name not in self._tasks:
                return False
            del self._tasks[name]
            self._fns.pop(name, None)
            return True

    def enable(self, name: str) -> bool:
        with self._lock:
            if name not in self._tasks:
                return False
            self._tasks[name].enabled = True
            return True

    def disable(self, name: str) -> bool:
        with self._lock:
            if name not in self._tasks:
                return False
            self._tasks[name].enabled = False
            return True

    def list_tasks(self) -> list[dict]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.name)
        return [t.to_dict() for t in tasks]

    def tick(self, now: float | None = None) -> list[TaskRun]:
        if now is None:
            now = time.time()

        with self._lock:
            due = []
            for name, task in self._tasks.items():
                if not task.enabled:
                    continue
                if task.next_run_at > now:
                    continue
                fn = self._fns.get(name)
                if fn is None:
                    continue
                due.append((name, task, fn))

        runs: list[TaskRun] = []
        for name, task, fn in due:
            start = time.time()
            try:
                fn()
                success = True
                error: str | None = None
            except Exception as exc:
                success = False
                error = str(exc)
            duration_ms = (time.time() - start) * 1000

            with self._lock:
                task.last_run = now
                task.next_run_at = now + task.interval_seconds

            run = TaskRun(
                task_name=name,
                ran_at=start,
                duration_ms=duration_ms,
                success=success,
                error=error,
            )
            with self._lock:
                self._log.append(run)
            runs.append(run)

        return runs

    def get_log(self, limit: int = 100) -> list[TaskRun]:
        with self._lock:
            log = list(self._log)
        return log[-limit:]

    def count(self) -> dict:
        with self._lock:
            return {"tasks": len(self._tasks), "runs": len(self._log)}
