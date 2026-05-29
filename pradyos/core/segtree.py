"""Phase 81 — Sovereign Segment Tree (range queries with point updates).

A segment tree answers associative range queries — sum, min, or max over any
sub-range ``[lo, hi]`` — together with point updates, both in O(log n). It is
more general than a Fenwick tree (which only does prefix sums), at the cost of
roughly double the memory.

Implementation note: this is the *iterative bottom-up* variant (a flat ``2·n``
array with the leaves in ``[n, 2n)`` and each internal node ``i`` holding
``combine(tree[2i], tree[2i+1])``). It is chosen over the textbook recursive
``4·n`` layout because the tight while-loop hits the project's O(log n) latency
budget on a million-element tree where Python recursion would not. The
aggregate (``sum`` / ``min`` / ``max``) is fixed at construction; all three are
commutative and associative, so the bottom-up combine order is correct. The
underlying array starts at all zeros. Pure stdlib; thread-safe via a single
non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import threading


_MODES = ("sum", "min", "max")


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class SegmentTree:
    """Range sum/min/max with O(log n) point updates (stdlib only)."""

    def __init__(self, size: int, mode: str = "sum") -> None:
        if not _is_int(size) or size < 1:
            raise ValueError("size must be a positive integer")
        if mode not in _MODES:
            raise ValueError("mode must be one of 'sum', 'min', 'max'")
        self._n = size
        self._mode = mode
        self._tree = [0] * (2 * size)   # leaves live in [n, 2n)
        self._lock = threading.Lock()

    # ── aggregation primitives ───────────────────────────────────────────────
    def _combine(self, a, b):
        if self._mode == "sum":
            return a + b
        if self._mode == "min":
            return a if a < b else b
        return a if a > b else b

    @property
    def _identity(self):
        if self._mode == "sum":
            return 0
        if self._mode == "min":
            return float("inf")
        return float("-inf")

    # ── internal (assume lock held); indices below are 1-based externally ────
    def _set_locked(self, i: int, val) -> None:
        pos = (i - 1) + self._n
        self._tree[pos] = val
        pos >>= 1
        while pos >= 1:
            self._tree[pos] = self._combine(self._tree[2 * pos], self._tree[2 * pos + 1])
            pos >>= 1

    def _query_locked(self, lo: int, hi: int):
        res = self._identity
        left = (lo - 1) + self._n
        right = hi + self._n            # half-open upper bound
        while left < right:
            if left & 1:
                res = self._combine(res, self._tree[left])
                left += 1
            if right & 1:
                right -= 1
                res = self._combine(res, self._tree[right])
            left >>= 1
            right >>= 1
        return res

    # ── mutation ──────────────────────────────────────────────────────────────
    def update(self, i: int, val) -> None:
        """Set the value at 1-based index ``i`` (int or float, may be negative)."""
        if not _is_int(i):
            raise ValueError("index must be an integer")
        if not _is_number(val):
            raise ValueError("val must be a number")
        with self._lock:
            if not 1 <= i <= self._n:
                raise ValueError(f"index {i} out of bounds [1, {self._n}]")
            self._set_locked(i, val)

    def resize(self, new_size: int) -> None:
        """Grow or shrink to ``new_size``, preserving the overlapping prefix."""
        if not _is_int(new_size) or new_size < 1:
            raise ValueError("new_size must be a positive integer")
        with self._lock:
            keep = min(self._n, new_size)
            values = [self._tree[(i - 1) + self._n] for i in range(1, keep + 1)]
            self._n = new_size
            self._tree = [0] * (2 * new_size)
            for offset, value in enumerate(values):
                self._tree[new_size + offset] = value
            for node in range(new_size - 1, 0, -1):
                self._tree[node] = self._combine(self._tree[2 * node], self._tree[2 * node + 1])

    def clear(self) -> None:
        """Reset every value to zero (size and mode unchanged)."""
        with self._lock:
            self._tree = [0] * (2 * self._n)

    # ── queries ─────────────────────────────────────────────────────────────
    def query(self, lo: int, hi: int):
        """Aggregate (sum/min/max) over the inclusive range ``[lo, hi]``."""
        if not _is_int(lo) or not _is_int(hi):
            raise ValueError("lo and hi must be integers")
        with self._lock:
            if not 1 <= lo <= hi <= self._n:
                raise ValueError(f"range [{lo}, {hi}] out of bounds [1, {self._n}]")
            return self._query_locked(lo, hi)

    def point_query(self, i: int):
        """Current value stored at 1-based index ``i``."""
        if not _is_int(i):
            raise ValueError("index must be an integer")
        with self._lock:
            if not 1 <= i <= self._n:
                raise ValueError(f"index {i} out of bounds [1, {self._n}]")
            return self._tree[(i - 1) + self._n]

    # ── introspection ─────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        with self._lock:
            return self._n

    @property
    def mode(self) -> str:
        return self._mode

    def stats(self) -> dict:
        """JSON-serialisable snapshot: size, mode, and whole-array aggregate."""
        with self._lock:
            return {"size": self._n, "mode": self._mode, "aggregate": self._tree[1]}
