"""Phase 84 — Sovereign LRU Cache.

A fixed-capacity key→value cache with least-recently-used eviction and optional
per-key TTL. Backed by an :class:`collections.OrderedDict`, every ``get`` and
``put`` moves the touched key to the most-recent end in O(1); when the cache
overflows its capacity the least-recently-used key (the front) is evicted. A key
may carry a TTL (seconds): once expired it is treated as a miss and lazily purged
on the next touch (no background thread).

Hit/miss/eviction/expiration counters feed :meth:`stats`. The clock is injectable
(``time_fn``, default :func:`time.monotonic`) so TTL behaviour is deterministic in
tests. Pure stdlib. Thread-safe via a single ``threading.Lock``; the public
surface acquires it, and internal helpers that run under the lock never re-acquire
it (the lock is non-reentrant).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


class CacheMissError(Exception):
    """Raised when a key is absent or expired. The ``key`` attribute holds it."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"cache miss: {key!r}")


class SovereignLRUCache:
    """Fixed-capacity LRU cache with optional TTL (stdlib only)."""

    def __init__(self, capacity: int, time_fn: Callable[[], float] | None = None) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._now_fn = time_fn or time.monotonic
        self._data: OrderedDict[str, list] = OrderedDict()  # key -> [value, expiry|None]
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0
        self._lock = threading.Lock()

    # ── internal (callers already hold the lock) ─────────────────────────────
    def _expired(self, entry: list) -> bool:
        return entry[1] is not None and entry[1] <= self._now_fn()

    def _purge_expired(self) -> None:
        dead = [k for k, e in self._data.items() if self._expired(e)]
        for k in dead:
            del self._data[k]
            self._expirations += 1

    def _evict_to_capacity(self) -> None:
        while len(self._data) > self._capacity:
            self._data.popitem(last=False)  # drop least-recently-used
            self._evictions += 1

    # ── mutation ──────────────────────────────────────────────────────────────
    def put(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Insert or update ``key`` (most-recent); optional ``ttl`` seconds."""
        if not isinstance(key, str) or key == "":
            raise ValueError("key must be a non-empty string")
        if ttl is not None and (
            not isinstance(ttl, int | float) or isinstance(ttl, bool) or ttl <= 0
        ):
            raise ValueError("ttl must be a positive number or None")
        with self._lock:
            expiry = (self._now_fn() + ttl) if ttl is not None else None
            self._data[key] = [value, expiry]
            self._data.move_to_end(key)
            self._evict_to_capacity()

    def delete(self, key: str) -> bool:
        """Evict ``key``. Returns True if it was present, else False."""
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def resize(self, new_capacity: int) -> None:
        """Change capacity live, evicting LRU entries if it shrinks."""
        if not isinstance(new_capacity, int) or isinstance(new_capacity, bool) or new_capacity < 1:
            raise ValueError("new_capacity must be a positive integer")
        with self._lock:
            self._capacity = new_capacity
            self._evict_to_capacity()

    def clear(self) -> None:
        """Empty the cache and reset all counters."""
        with self._lock:
            self._data.clear()
            self._hits = self._misses = self._evictions = self._expirations = 0

    # ── queries ─────────────────────────────────────────────────────────────
    def get(self, key: str) -> Any:
        """Return ``key``'s value and mark it most-recent. Raises :class:`CacheMissError`."""
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        with self._lock:
            entry = self._data.get(key)
            if entry is None or self._expired(entry):
                if entry is not None:
                    del self._data[key]
                    self._expirations += 1
                self._misses += 1
                raise CacheMissError(key)
            self._data.move_to_end(key)
            self._hits += 1
            return entry[0]

    def peek(self, key: str) -> Any:
        """Return ``key``'s value without changing recency or hit/miss counters."""
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        with self._lock:
            entry = self._data.get(key)
            if entry is None or self._expired(entry):
                if entry is not None:
                    del self._data[key]
                    self._expirations += 1
                raise CacheMissError(key)
            return entry[0]

    def contains(self, key: str) -> bool:
        if not isinstance(key, str):
            return False
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            if self._expired(entry):
                del self._data[key]
                self._expirations += 1
                return False
            return True

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired()
            return len(self._data)

    @property
    def capacity(self) -> int:
        with self._lock:
            return self._capacity

    # ── snapshots / stats ─────────────────────────────────────────────────────
    def snapshot(self) -> list[list]:
        """``[key, value]`` pairs, most-recently-used first (live entries only)."""
        with self._lock:
            self._purge_expired()
            return [[k, self._data[k][0]] for k in reversed(self._data)]

    def to_dict(self) -> dict:
        """JSON-serialisable cache state, recency-ordered (MRU first)."""
        with self._lock:
            self._purge_expired()
            return {
                "capacity": self._capacity,
                "size": len(self._data),
                "entries": [[k, self._data[k][0]] for k in reversed(self._data)],
            }

    def stats(self) -> dict:
        """Counters plus derived hit-rate."""
        with self._lock:
            self._purge_expired()
            total = self._hits + self._misses
            return {
                "capacity": self._capacity,
                "size": len(self._data),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 6) if total else 0.0,
                "evictions": self._evictions,
                "expirations": self._expirations,
            }
