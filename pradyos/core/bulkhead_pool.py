from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable


class BulkheadRejectedError(RuntimeError):
    """Raised when a pool refuses a submission because it is at capacity."""


@dataclass
class PoolStats:
    name: str
    max_workers: int
    queue_depth: int
    submitted: int
    completed: int
    rejected: int
    active: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "max_workers": self.max_workers,
            "queue_depth": self.queue_depth,
            "submitted": self.submitted,
            "completed": self.completed,
            "rejected": self.rejected,
            "active": self.active,
        }


class BulkheadPool:
    def __init__(
        self,
        max_workers: int = 4,
        queue_depth: int = 8,
        name: str = "default",
    ) -> None:
        self._name = name
        self._max_workers = max_workers
        self._queue_depth = queue_depth
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._submitted = 0
        self._completed = 0
        self._rejected = 0
        # in_flight = tasks submitted but not yet completed.
        # active = min(in_flight, max_workers) (running)
        # queued = max(0, in_flight - max_workers) (waiting)
        self._in_flight = 0

    @property
    def name(self) -> str:
        return self._name

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        capacity = self._max_workers + self._queue_depth
        with self._lock:
            if self._in_flight >= capacity:
                self._rejected += 1
                raise BulkheadRejectedError(
                    f"pool {self._name!r} at capacity "
                    f"(in_flight={self._in_flight}, capacity={capacity})"
                )
            self._submitted += 1
            self._in_flight += 1

        future = self._executor.submit(fn, *args, **kwargs)

        def _on_done(_fut: Future) -> None:
            with self._lock:
                self._in_flight -= 1
                self._completed += 1

        future.add_done_callback(_on_done)
        return future

    def get_stats(self) -> PoolStats:
        with self._lock:
            active = min(self._in_flight, self._max_workers)
            return PoolStats(
                name=self._name,
                max_workers=self._max_workers,
                queue_depth=self._queue_depth,
                submitted=self._submitted,
                completed=self._completed,
                rejected=self._rejected,
                active=active,
            )

    def reset_stats(self) -> None:
        with self._lock:
            self._submitted = 0
            self._completed = 0
            self._rejected = 0
            # do NOT reset _in_flight — running tasks are still in flight

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


class BulkheadManager:
    def __init__(self) -> None:
        self._pools: dict[str, BulkheadPool] = {}
        self._lock = threading.Lock()

    def create(
        self,
        name: str,
        max_workers: int = 4,
        queue_depth: int = 8,
    ) -> BulkheadPool:
        with self._lock:
            if name in self._pools:
                raise ValueError(f"pool {name!r} already exists")
            pool = BulkheadPool(
                max_workers=max_workers,
                queue_depth=queue_depth,
                name=name,
            )
            self._pools[name] = pool
            return pool

    def get(self, name: str) -> BulkheadPool | None:
        with self._lock:
            return self._pools.get(name)

    def delete(self, name: str) -> bool:
        with self._lock:
            pool = self._pools.pop(name, None)
        if pool is None:
            return False
        try:
            pool.shutdown(wait=True)
        except Exception:
            pass
        return True

    def list_pools(self) -> list[dict]:
        with self._lock:
            pools = sorted(self._pools.values(), key=lambda p: p.name)
        return [p.get_stats().to_dict() for p in pools]

    def count(self) -> int:
        with self._lock:
            return len(self._pools)
