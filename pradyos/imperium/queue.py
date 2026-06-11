"""IMPERIUM SchedulerCore — priority queue with FIFO tiebreaking.

A pure-Python heap is sufficient for Phase 0. The kernel hands off to a
real scheduler (asyncio task group, distributed dispatcher) in later
phases without changing the queue contract.
"""

from __future__ import annotations

import heapq
import itertools
import threading
from collections.abc import Iterator

from pradyos.core.types import Priority
from pradyos.imperium.task import ImperiumTask, TaskRecord


class TaskQueue:
    def __init__(self) -> None:
        self._heap: list[tuple[int, int, float, str]] = []
        self._records: dict[str, TaskRecord] = {}
        self._counter = itertools.count()
        self._lock = threading.Lock()

    # ---------- write ----------
    def enqueue(self, task: ImperiumTask) -> TaskRecord:
        rec = TaskRecord(spec=task)
        with self._lock:
            self._records[task.task_id] = rec
            heapq.heappush(
                self._heap,
                (task.priority.rank, next(self._counter), rec.queued_at, task.task_id),
            )
        return rec

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            rec = self._records.get(task_id)
            if rec is None or rec.is_terminal:
                return False
            from pradyos.core.types import TaskState

            rec.state = TaskState.CANCELLED
            return True

    # ---------- read ----------
    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._records.get(task_id)

    def __contains__(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._records

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def pending_records(self) -> list[TaskRecord]:
        from pradyos.core.types import TaskState

        with self._lock:
            return [r for r in self._records.values() if r.state == TaskState.QUEUED]

    def all_records(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._records.values())

    def iter_priority_order(self) -> Iterator[TaskRecord]:
        """Snapshot view in priority + FIFO order. For inspection only."""
        with self._lock:
            ordered = sorted(
                self._records.values(),
                key=lambda r: (r.spec.priority.rank, r.queued_at),
            )
            return iter(ordered)

    # ---------- pop next runnable ----------
    def pop_runnable(self, is_satisfied) -> TaskRecord | None:
        """Pop the highest-priority QUEUED task whose dependencies are
        satisfied. ``is_satisfied(task_id) -> bool`` decides per-dep."""
        from pradyos.core.types import TaskState

        with self._lock:
            skipped: list[tuple[int, int, float, str]] = []
            chosen: TaskRecord | None = None
            while self._heap:
                entry = heapq.heappop(self._heap)
                tid = entry[3]
                rec = self._records.get(tid)
                if rec is None or rec.state != TaskState.QUEUED:
                    continue
                if all(is_satisfied(d) for d in rec.spec.depends_on):
                    chosen = rec
                    break
                skipped.append(entry)
            for s in skipped:
                heapq.heappush(self._heap, s)
            return chosen

    def stats(self) -> dict[str, int]:
        from pradyos.core.types import TaskState

        counts = {s.value: 0 for s in TaskState}
        priority_counts = {p.value: 0 for p in Priority}
        with self._lock:
            for r in self._records.values():
                counts[r.state.value] += 1
                priority_counts[r.spec.priority.value] += 1
        return {
            "total": sum(counts.values()),
            **{f"state.{k}": v for k, v in counts.items()},
            **{f"priority.{k}": v for k, v in priority_counts.items()},
        }
