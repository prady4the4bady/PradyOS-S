from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.snapshot_store import SnapshotStore


@dataclass
class MemoryEntry:
    key: str
    value: Any
    tags: list[str]
    created_at: float
    updated_at: float
    ttl: float | None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl": self.ttl,
        }

    def is_expired(self, now: float | None = None) -> bool:
        if self.ttl is None:
            return False
        if now is None:
            now = time.time()
        return (now - self.updated_at) > self.ttl


class MemoryStore:
    def __init__(
        self,
        snapshot_store: "SnapshotStore | None" = None,
        snapshot_ns: str = "memory",
    ) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._lock = threading.Lock()
        self._snapshot_store = snapshot_store
        self._snapshot_ns = snapshot_ns

        if self._snapshot_store is not None:
            self._load_from_snapshot()

    def _load_from_snapshot(self) -> None:
        if self._snapshot_store is None:
            return
        keys = self._snapshot_store.list_keys(self._snapshot_ns)
        now = time.time()
        for key_info in keys:
            snap = self._snapshot_store.get(self._snapshot_ns, key_info["key"])
            if snap is None:
                continue
            d = snap.data
            try:
                entry = MemoryEntry(
                    key=d["key"],
                    value=d["value"],
                    tags=list(d.get("tags", [])),
                    created_at=float(d["created_at"]),
                    updated_at=float(d["updated_at"]),
                    ttl=d["ttl"],
                )
            except (KeyError, TypeError, ValueError):
                continue
            if entry.is_expired(now):
                continue
            self._entries[entry.key] = entry

    def store(
        self,
        key: str,
        value: Any,
        tags: list[str] | None = None,
        ttl: float | None = None,
    ) -> MemoryEntry:
        now = time.time()
        if tags is None:
            tags = []
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                existing.value = value
                existing.tags = list(tags)
                existing.updated_at = now
                existing.ttl = ttl
                entry = existing
            else:
                entry = MemoryEntry(
                    key=key,
                    value=value,
                    tags=list(tags),
                    created_at=now,
                    updated_at=now,
                    ttl=ttl,
                )
                self._entries[key] = entry

        if self._snapshot_store is not None:
            self._snapshot_store.save(self._snapshot_ns, key, entry.to_dict())

        return entry

    def recall(self, key: str) -> MemoryEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._entries[key]
                return None
            return entry

    def search(self, tag: str) -> list[MemoryEntry]:
        now = time.time()
        with self._lock:
            results: list[MemoryEntry] = []
            expired_keys: list[str] = []
            for key, entry in self._entries.items():
                if entry.is_expired(now):
                    expired_keys.append(key)
                    continue
                if tag in entry.tags:
                    results.append(entry)
            for k in expired_keys:
                del self._entries[k]
        return sorted(results, key=lambda e: e.key)

    def forget(self, key: str) -> bool:
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
        return False

    def expire(self) -> int:
        now = time.time()
        with self._lock:
            expired_keys = [k for k, e in self._entries.items() if e.is_expired(now)]
            for k in expired_keys:
                del self._entries[k]
            return len(expired_keys)

    def count(self) -> int:
        with self._lock:
            return len(self._entries)
