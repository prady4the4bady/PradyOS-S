"""IMPERIUM — SchedulerCore (Phase 1).

The SchedulerCore owns priority-aware dispatch: it wraps the TaskQueue +
DependencyGraph and exposes a clean API that the Kernel calls to pop work.
It is the only layer allowed to touch the heap ordering.

Responsibilities:
    - Accept task submissions (enqueue with DAG validation)
    - Pop the next runnable task given a satisfaction predicate
    - Expose iteration and stats without exposing queue internals
    - Emit telemetry counters accessible to the Throne
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from pradyos.core.types import Priority, TaskState
from pradyos.imperium.dag import CycleDetected, DependencyGraph, is_satisfied_factory
from pradyos.imperium.queue import TaskQueue
from pradyos.imperium.task import ImperiumTask, TaskRecord


SatisfactionPredicate = Callable[[str], bool]


class SchedulerCore:
    """Priority-aware task dispatcher with DAG dependency enforcement."""

    def __init__(self) -> None:
        self._queue = TaskQueue()
        self._dag = DependencyGraph()
        self._lock = threading.Lock()
        self._submitted: int = 0
        self._popped: int = 0

    # ---------- submission ----------

    def submit(self, task: ImperiumTask) -> TaskRecord:
        """Enqueue a task after DAG validation.

        Raises ``CycleDetected`` if the dependency graph would cycle.
        """
        with self._lock:
            self._dag.add_task(task.task_id, task.depends_on)
            rec = self._queue.enqueue(task)
            self._submitted += 1
            return rec

    # ---------- dispatch ----------

    def pop_next(self) -> TaskRecord | None:
        """Return the highest-priority runnable task, or None.

        A task is runnable if all its dependencies have succeeded.
        """
        with self._lock:
            all_records = {r.spec.task_id: r for r in self._queue.all_records()}
            is_sat = is_satisfied_factory(all_records)
            rec = self._queue.pop_runnable(is_sat)
            if rec is not None:
                self._popped += 1
            return rec

    def requeue(self, task: ImperiumTask) -> TaskRecord:
        """Re-insert a task (used by RecoveryCore on retry)."""
        with self._lock:
            rec = self._queue.enqueue(task)
            return rec

    # ---------- inspection ----------

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._queue.get(task_id)

    def all_records(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._queue.all_records())

    def iter_priority_order(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._queue.iter_priority_order())

    def pending_approvals(self) -> list[TaskRecord]:
        with self._lock:
            return [r for r in self._queue.all_records()
                    if r.state is TaskState.ESCALATED]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            s = self._queue.stats()
        s["scheduler.submitted"] = self._submitted
        s["scheduler.popped"] = self._popped
        s["pending_approvals"] = len(self.pending_approvals())
        return s

    def topological_order(self) -> list[str]:
        with self._lock:
            return self._dag.topological_order()
