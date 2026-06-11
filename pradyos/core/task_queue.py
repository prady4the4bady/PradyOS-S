from __future__ import annotations

import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Task:
    id: str
    name: str
    payload: dict
    priority: int
    status: str  # 'pending' | 'running' | 'done' | 'failed'
    created_at: float
    started_at: float | None
    finished_at: float | None
    result: dict | None
    error: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "payload": dict(self.payload),
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": dict(self.result) if self.result else None,
            "error": self.error,
        }


# Sentinel id used by WorkerPool to unblock workers during shutdown.
_STOP_SENTINEL = "__STOP__"


class TaskQueue:
    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=maxsize)
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._counter = 0  # monotonic FIFO tie-breaker for equal priorities

    # ── submit / get / list ──────────────────────────────────────────────────

    def submit(self, name: str, payload: dict, priority: int = 5) -> Task:
        task = Task(
            id=uuid.uuid4().hex,
            name=name,
            payload=dict(payload) if payload else {},
            priority=priority,
            status="pending",
            created_at=time.time(),
            started_at=None,
            finished_at=None,
            result=None,
            error=None,
        )
        with self._lock:
            self._tasks[task.id] = task
            self._counter += 1
            seq = self._counter
        # tuple form: (priority, seq, id) — all comparable, FIFO within priority
        self._queue.put((priority, seq, task.id))
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at)
        return tasks

    # ── cancel / state transitions ───────────────────────────────────────────

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status != "pending":
                return False
            task.status = "failed"
            task.error = "cancelled"
            task.finished_at = time.time()
            return True

    def _mark_running(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "running"
            task.started_at = time.time()

    def _mark_done(self, task_id: str, result: dict) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "done"
            task.result = dict(result) if result else {}
            task.finished_at = time.time()

    def _mark_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "failed"
            task.error = error
            task.finished_at = time.time()


class WorkerPool:
    def __init__(
        self,
        task_queue: TaskQueue,
        num_workers: int = 2,
        handler: Callable[[Task], dict] | None = None,
    ) -> None:
        if handler is None:
            raise ValueError("handler is required")
        self._tq = task_queue
        self._num_workers = num_workers
        self._handler = handler
        self._threads: list[threading.Thread] = []
        self._stopping = False

        for i in range(num_workers):
            t = threading.Thread(
                target=self._worker,
                name=f"pradyos-worker-{i}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

    def _worker(self) -> None:
        while True:
            try:
                item = self._tq._queue.get()
            except Exception:
                return
            # Sentinel detection
            if not isinstance(item, tuple) or len(item) < 3:
                return
            _, _, task_id = item
            if task_id == _STOP_SENTINEL:
                return

            task = self._tq.get(task_id)
            if task is None or task.status != "pending":
                continue  # cancelled or vanished

            self._tq._mark_running(task_id)
            try:
                result = self._handler(task)
                self._tq._mark_done(task_id, result or {})
            except Exception as exc:
                self._tq._mark_failed(task_id, str(exc))

    def stop(self) -> None:
        self._stopping = True
        # Send N sentinels — one per worker.
        # Use a very high priority value so they're processed AFTER pending work.
        for _ in range(self._num_workers):
            self._tq._queue.put((10**9, 10**9, _STOP_SENTINEL))
        for t in self._threads:
            t.join(timeout=2.0)

    def is_alive(self) -> bool:
        return any(t.is_alive() for t in self._threads)
