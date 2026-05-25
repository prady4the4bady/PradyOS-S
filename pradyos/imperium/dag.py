"""Basic dependency graph resolution.

Detects cycles, computes in-degree, and tells the scheduler whether a
task's predecessors are satisfied.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Iterable

from pradyos.core.types import TaskState
from pradyos.imperium.task import TaskRecord


class CycleDetected(ValueError):
    """Raised when adding an edge would close a cycle."""


class DependencyGraph:
    def __init__(self) -> None:
        self._edges: dict[str, set[str]] = defaultdict(set)  # parent → {children}
        self._reverse: dict[str, set[str]] = defaultdict(set)  # child → {parents}
        self._lock = threading.Lock()

    def add_task(self, task_id: str, depends_on: Iterable[str]) -> None:
        with self._lock:
            for parent in depends_on:
                if parent == task_id:
                    raise CycleDetected(f"self-dependency on {task_id!r}")
                if self._would_cycle(parent, task_id):
                    raise CycleDetected(
                        f"adding {parent}→{task_id} would form a cycle"
                    )
                self._edges[parent].add(task_id)
                self._reverse[task_id].add(parent)

    def parents(self, task_id: str) -> set[str]:
        with self._lock:
            return set(self._reverse.get(task_id, set()))

    def children(self, task_id: str) -> set[str]:
        with self._lock:
            return set(self._edges.get(task_id, set()))

    def remove(self, task_id: str) -> None:
        with self._lock:
            for parent in list(self._reverse.get(task_id, [])):
                self._edges[parent].discard(task_id)
            self._reverse.pop(task_id, None)
            self._edges.pop(task_id, None)

    def topological_order(self) -> list[str]:
        with self._lock:
            indeg: dict[str, int] = defaultdict(int)
            nodes = set(self._edges) | {n for s in self._edges.values() for n in s} | set(self._reverse)
            for n in nodes:
                indeg[n] = len(self._reverse.get(n, set()))
            q = deque([n for n in nodes if indeg[n] == 0])
            order: list[str] = []
            while q:
                n = q.popleft()
                order.append(n)
                for child in self._edges.get(n, set()):
                    indeg[child] -= 1
                    if indeg[child] == 0:
                        q.append(child)
            if len(order) != len(nodes):
                raise CycleDetected("cycle in dependency graph")
            return order

    # ---------- internals ----------
    def _would_cycle(self, parent: str, child: str) -> bool:
        # If `child` can already reach `parent`, the new edge closes a cycle.
        if parent == child:
            return True
        stack = [child]
        seen: set[str] = set()
        while stack:
            n = stack.pop()
            if n == parent:
                return True
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self._edges.get(n, set()))
        return False


def is_satisfied_factory(records: dict[str, TaskRecord]):
    """Return a closure used by ``TaskQueue.pop_runnable``."""

    def is_satisfied(parent_id: str) -> bool:
        rec = records.get(parent_id)
        if rec is None:
            # parent is unknown — treat as satisfied so external IDs don't block
            return True
        return rec.state == TaskState.SUCCEEDED

    return is_satisfied
