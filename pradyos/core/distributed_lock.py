from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class DistributedLock:
    name: str
    holder_id: str
    acquired_at: float
    ttl_seconds: float
    expires_at: float

    def is_expired(self, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        return now > self.expires_at

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "holder_id": self.holder_id,
            "acquired_at": self.acquired_at,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at,
        }


class LockManager:
    def __init__(self) -> None:
        self._locks: dict[str, DistributedLock] = {}
        self._lock = threading.Lock()

    def acquire(
        self,
        name: str,
        holder_id: str,
        ttl: float = 30.0,
    ) -> DistributedLock | None:
        with self._lock:
            now = time.time()
            existing = self._locks.get(name)
            if existing is not None and not existing.is_expired(now):
                if existing.holder_id != holder_id:
                    return None
                # Same holder re-acquires → replace (refresh TTL).
            lock = DistributedLock(
                name=name,
                holder_id=holder_id,
                acquired_at=now,
                ttl_seconds=ttl,
                expires_at=now + ttl,
            )
            self._locks[name] = lock
            return lock

    def release(self, name: str, holder_id: str) -> bool:
        with self._lock:
            existing = self._locks.get(name)
            if existing is None:
                return False
            if existing.holder_id != holder_id:
                return False
            if existing.is_expired():
                return False
            del self._locks[name]
            return True

    def refresh(
        self,
        name: str,
        holder_id: str,
        ttl: float = 30.0,
    ) -> bool:
        with self._lock:
            existing = self._locks.get(name)
            if existing is None:
                return False
            if existing.is_expired():
                return False
            if existing.holder_id != holder_id:
                return False
            existing.ttl_seconds = ttl
            existing.expires_at = time.time() + ttl
            return True

    def is_locked(self, name: str) -> bool:
        with self._lock:
            existing = self._locks.get(name)
            return existing is not None and not existing.is_expired()

    def list_locks(self) -> list[dict]:
        with self._lock:
            now = time.time()
            active = [lk for lk in self._locks.values() if not lk.is_expired(now)]
        active.sort(key=lambda lk: lk.acquired_at)
        return [lk.to_dict() for lk in active]

    def expire_stale(self) -> int:
        with self._lock:
            now = time.time()
            expired_names = [n for n, lk in self._locks.items() if lk.is_expired(now)]
            for n in expired_names:
                del self._locks[n]
            return len(expired_names)

    def count(self, include_expired: bool = False) -> int:
        with self._lock:
            if include_expired:
                return len(self._locks)
            now = time.time()
            return sum(1 for lk in self._locks.values() if not lk.is_expired(now))
