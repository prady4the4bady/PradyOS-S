"""Phase 80 — Sovereign Fenwick Tree (Binary Indexed Tree).

A Fenwick tree maintains a running array of values and answers prefix-sum
queries — "what is the total of indices 1..i?" — and point updates both in
O(log n), where a naive array gives O(1) update but O(n) prefix sum, and a naive
prefix-array gives the reverse. It exploits the binary structure of indices:
each tree slot ``i`` covers the range ending at ``i`` of length ``i & -i`` (the
lowest set bit), so updates walk *up* by adding that bit and prefix sums walk
*down* by subtracting it.

Indices are 1-based. ``range_sum(lo, hi)`` is ``prefix_sum(hi) -
prefix_sum(lo-1)`` and ``point_query(i)`` is ``range_sum(i, i)``. Values may be
ints or floats and deltas may be negative. Pure stdlib; thread-safe via a single
non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import threading


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class FenwickTree:
    """A 1-indexed binary indexed tree for prefix sums (stdlib only)."""

    def __init__(self, size: int) -> None:
        if not _is_int(size) or size < 1:
            raise ValueError("size must be a positive integer")
        self._size = size
        self._tree = [0] * (size + 1)  # 1-indexed; slot 0 unused
        self._lock = threading.Lock()

    # ── internal (assume lock held) ──────────────────────────────────────────
    def _prefix_sum_locked(self, i: int):
        total = 0
        while i > 0:
            total += self._tree[i]
            i -= i & (-i)
        return total

    def _add_locked(self, i: int, delta) -> None:
        while i <= self._size:
            self._tree[i] += delta
            i += i & (-i)

    # ── mutation ──────────────────────────────────────────────────────────────
    def update(self, i: int, delta) -> None:
        """Add ``delta`` (int or float, may be negative) at 1-based index ``i``."""
        if not _is_int(i):
            raise ValueError("index must be an integer")
        if not _is_number(delta):
            raise ValueError("delta must be a number")
        with self._lock:
            if not 1 <= i <= self._size:
                raise ValueError(f"index {i} out of bounds [1, {self._size}]")
            self._add_locked(i, delta)

    def resize(self, new_size: int) -> None:
        """Grow or shrink to ``new_size``, preserving values within the overlap."""
        if not _is_int(new_size) or new_size < 1:
            raise ValueError("new_size must be a positive integer")
        with self._lock:
            keep = min(self._size, new_size)
            values = [
                self._prefix_sum_locked(i) - self._prefix_sum_locked(i - 1)
                for i in range(1, keep + 1)
            ]
            self._size = new_size
            self._tree = [0] * (new_size + 1)
            for idx, value in enumerate(values, start=1):
                if value != 0:
                    self._add_locked(idx, value)

    def clear(self) -> None:
        """Reset every value to zero (size unchanged)."""
        with self._lock:
            self._tree = [0] * (self._size + 1)

    # ── queries ─────────────────────────────────────────────────────────────
    def prefix_sum(self, i: int):
        """Sum of indices 1..i (``prefix_sum(0)`` is 0)."""
        if not _is_int(i):
            raise ValueError("index must be an integer")
        with self._lock:
            if not 0 <= i <= self._size:
                raise ValueError(f"index {i} out of bounds [0, {self._size}]")
            return self._prefix_sum_locked(i)

    def range_sum(self, lo: int, hi: int):
        """Inclusive sum of indices lo..hi (= prefix_sum(hi) - prefix_sum(lo-1))."""
        if not _is_int(lo) or not _is_int(hi):
            raise ValueError("lo and hi must be integers")
        with self._lock:
            if not 1 <= lo <= hi <= self._size:
                raise ValueError(f"range [{lo}, {hi}] out of bounds [1, {self._size}]")
            return self._prefix_sum_locked(hi) - self._prefix_sum_locked(lo - 1)

    def point_query(self, i: int):
        """Current value stored at index ``i``."""
        if not _is_int(i):
            raise ValueError("index must be an integer")
        with self._lock:
            if not 1 <= i <= self._size:
                raise ValueError(f"index {i} out of bounds [1, {self._size}]")
            return self._prefix_sum_locked(i) - self._prefix_sum_locked(i - 1)

    # ── introspection ─────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        with self._lock:
            return self._size

    def stats(self) -> dict:
        """JSON-serialisable snapshot: size and grand total (prefix_sum(size))."""
        with self._lock:
            return {"size": self._size, "total": self._prefix_sum_locked(self._size)}
