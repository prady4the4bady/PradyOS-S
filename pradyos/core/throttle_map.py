from __future__ import annotations

import threading
import time
from collections import deque


class ThrottleMap:
    """Per-key sliding-window rate limiter using monotonic timestamps."""

    def __init__(self) -> None:
        self._keys: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── internal helpers ─────────────────────────────────────────────────────

    def _ensure_locked(self, key: str) -> dict:
        """Caller holds self._lock."""
        entry = self._keys.get(key)
        if entry is None:
            entry = {
                "timestamps": deque(),
                "allowed": 0,
                "rejected": 0,
            }
            self._keys[key] = entry
        return entry

    @staticmethod
    def _purge_locked(entry: dict, window: float, now: float) -> None:
        """Caller holds self._lock. Drop timestamps older than (now - window)."""
        cutoff = now - window
        ts: deque = entry["timestamps"]
        while ts and ts[0] < cutoff:
            ts.popleft()

    # ── primary API ──────────────────────────────────────────────────────────

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            entry = self._ensure_locked(key)
            self._purge_locked(entry, window, now)
            if len(entry["timestamps"]) < limit:
                entry["timestamps"].append(now)
                entry["allowed"] += 1
                return True
            entry["rejected"] += 1
            return False

    def reset(self, key: str) -> bool:
        with self._lock:
            entry = self._keys.get(key)
            if entry is None:
                return False
            entry["timestamps"].clear()
            entry["allowed"] = 0
            entry["rejected"] = 0
            return True

    def stats(self, key: str, limit: int, window: float) -> dict | None:
        now = time.monotonic()
        with self._lock:
            entry = self._keys.get(key)
            if entry is None:
                return None
            self._purge_locked(entry, window, now)
            return {
                "key": key,
                "limit": limit,
                "window": window,
                "calls_in_window": len(entry["timestamps"]),
                "allowed_total": entry["allowed"],
                "rejected_total": entry["rejected"],
            }

    def list_keys(self) -> list[str]:
        with self._lock:
            return sorted(self._keys.keys())

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._keys.pop(key, None) is not None
