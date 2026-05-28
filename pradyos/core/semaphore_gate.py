from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class SemaphoreStats:
    name: str
    capacity: int
    available: int
    acquired_total: int
    released_total: int
    timeout_total: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "capacity": self.capacity,
            "available": self.available,
            "acquired_total": self.acquired_total,
            "released_total": self.released_total,
            "timeout_total": self.timeout_total,
        }


class SemaphoreTimeoutError(RuntimeError):
    """Raised by callers that prefer exception-style timeout signaling.
    `SemaphoreGate.acquire()` itself returns bool; this class is provided
    for downstream code that wants to convert that False into an exception."""


class SemaphoreNotFoundError(KeyError):
    """Raised when operating on an unknown semaphore name."""


class _Entry:
    """Internal bundle: the semaphore object + its tracking counters."""
    __slots__ = (
        "name", "capacity", "semaphore",
        "acquired_total", "released_total", "timeout_total",
    )

    def __init__(self, name: str, capacity: int) -> None:
        self.name = name
        self.capacity = capacity
        self.semaphore = threading.Semaphore(capacity)
        self.acquired_total = 0
        self.released_total = 0
        self.timeout_total = 0


class SemaphoreGate:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    # ── create / delete ─────────────────────────────────────────────────────

    def create(self, name: str, capacity: int = 1) -> SemaphoreStats:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        with self._lock:
            existing = self._entries.get(name)
            if existing is not None:
                if existing.capacity != capacity:
                    raise ValueError(
                        f"semaphore {name!r} already exists with "
                        f"capacity={existing.capacity}, cannot redefine as {capacity}"
                    )
                return self._stats_locked(existing)
            entry = _Entry(name, capacity)
            self._entries[name] = entry
            return self._stats_locked(entry)

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._entries.pop(name, None) is not None

    # ── acquire / release ────────────────────────────────────────────────────

    def acquire(self, name: str, timeout: float | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                raise SemaphoreNotFoundError(name)
            sem = entry.semaphore

        # acquire OUTSIDE the gate lock so other gate operations don't block.
        if timeout is None:
            ok = sem.acquire(blocking=True)
        else:
            ok = sem.acquire(timeout=timeout)

        with self._lock:
            # The entry may have been deleted between our get and the acquire.
            # In that case the counters are gone; just return the result.
            entry2 = self._entries.get(name)
            if entry2 is not None:
                if ok:
                    entry2.acquired_total += 1
                else:
                    entry2.timeout_total += 1
        return bool(ok)

    def release(self, name: str) -> None:
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                raise SemaphoreNotFoundError(name)
            entry.semaphore.release()
            entry.released_total += 1

    # ── stats / listing ──────────────────────────────────────────────────────

    def _stats_locked(self, entry: _Entry) -> SemaphoreStats:
        """Caller holds self._lock."""
        # threading.Semaphore stores its current free count in ._value.
        # Reading it under our own lock guards against torn reads relative
        # to our own counter increments.
        available = getattr(entry.semaphore, "_value", entry.capacity)
        return SemaphoreStats(
            name=entry.name,
            capacity=entry.capacity,
            available=available,
            acquired_total=entry.acquired_total,
            released_total=entry.released_total,
            timeout_total=entry.timeout_total,
        )

    def get_stats(self, name: str) -> SemaphoreStats:
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                raise SemaphoreNotFoundError(name)
            return self._stats_locked(entry)

    def list_names(self) -> list[str]:
        with self._lock:
            return sorted(self._entries.keys())
