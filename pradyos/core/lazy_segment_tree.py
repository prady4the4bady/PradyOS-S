"""Phase 163 — Sovereign Lazy Segment Tree (range-update + range-query).

A segment tree with **lazy propagation**: it supports `O(log n)` **range updates** — both
*range-add* and *range-assign* — alongside `O(log n)` **range-sum / range-min / range-max** queries.
A pending update over a node's whole span is buffered as a **lazy tag** and pushed down to children
only when one is visited, so an update touching `O(n)` leaves still costs `O(log n)`.

This is a new capability for the platform: the Segment Tree/P81 is *point-update* only, and the
Sqrt Decomposition/P147 does range-add/range-sum in `O(√n)` — the lazy segment tree adds `O(log n)`
range *assignment* and range *min/max*. Each node caches `sum` / `min` / `max`; the two lazy tags
compose with the rule **assign dominates** (a pending assign clears any pending add, then later adds
accumulate on top), pushed down assign-then-add.

Built over a perfectly balanced index tree, so recursion depth is `O(log n)` (never degenerate).
Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

import threading
from typing import Any


class LazySegmentTreeError(Exception):
    """Raised for an invalid lazy-segment-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class LazySegmentTree:
    """Range-add / range-assign updates + range sum/min/max queries, all O(log n) via lazy tags."""

    def __init__(self, values: Any = None) -> None:
        self._lock = threading.Lock()
        self._clear()
        if values is not None:
            self.build(values)

    def _clear(self) -> None:
        self._n = 0
        self._sum: list = []
        self._min: list = []
        self._max: list = []
        self._add: list = []
        self._assign: list = []  # None = no pending assign

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, values: Any) -> None:
        """(Re)build from ``values`` (replaces any prior contents)."""
        try:
            arr = list(values)
        except TypeError as exc:
            raise LazySegmentTreeError("values must be iterable") from exc
        for v in arr:
            if not _is_num(v):
                raise LazySegmentTreeError(f"every value must be a number, got {v!r}")
        with self._lock:
            self._clear()
            self._n = len(arr)
            if not arr:
                return
            size = 4 * self._n
            self._sum = [0] * size
            self._min = [0] * size
            self._max = [0] * size
            self._add = [0] * size
            self._assign = [None] * size
            self._build(1, 0, self._n - 1, arr)

    def _build(self, node: int, l: int, r: int, arr: list) -> None:
        if l == r:
            self._sum[node] = arr[l]
            self._min[node] = self._max[node] = arr[l]
            return
        mid = (l + r) // 2
        self._build(2 * node, l, mid, arr)
        self._build(2 * node + 1, mid + 1, r, arr)
        self._pull(node)

    # ── lazy apply / push / pull ──────────────────────────────────────────────────────────
    def _apply_assign(self, node: int, val: float, length: int) -> None:
        self._sum[node] = val * length
        self._min[node] = val
        self._max[node] = val
        self._assign[node] = val
        self._add[node] = 0

    def _apply_add(self, node: int, delta: float, length: int) -> None:
        self._sum[node] += delta * length
        self._min[node] += delta
        self._max[node] += delta
        if self._assign[node] is not None:
            self._assign[node] += delta
        else:
            self._add[node] += delta

    def _push(self, node: int, l: int, r: int) -> None:
        mid = (l + r) // 2
        llen = mid - l + 1
        rlen = r - mid
        if self._assign[node] is not None:
            av = self._assign[node]
            self._apply_assign(2 * node, av, llen)
            self._apply_assign(2 * node + 1, av, rlen)
            self._assign[node] = None
        if self._add[node] != 0:
            ad = self._add[node]
            self._apply_add(2 * node, ad, llen)
            self._apply_add(2 * node + 1, ad, rlen)
            self._add[node] = 0

    def _pull(self, node: int) -> None:
        self._sum[node] = self._sum[2 * node] + self._sum[2 * node + 1]
        self._min[node] = min(self._min[2 * node], self._min[2 * node + 1])
        self._max[node] = max(self._max[2 * node], self._max[2 * node + 1])

    # ── range updates ──────────────────────────────────────────────────────────────────────
    def _validate_range(self, lo: Any, hi: Any) -> None:
        if not _is_int(lo) or not _is_int(hi):
            raise LazySegmentTreeError("lo and hi must be ints")
        if not (0 <= lo <= hi < self._n):
            raise LazySegmentTreeError(f"need 0 <= lo <= hi < {self._n}")

    def _update(
        self, node: int, l: int, r: int, lo: int, hi: int, delta: float | None, assign: float | None
    ) -> None:
        if hi < l or r < lo:
            return
        if lo <= l and r <= hi:
            if assign is not None:
                self._apply_assign(node, assign, r - l + 1)
            else:
                self._apply_add(node, delta, r - l + 1)
            return
        self._push(node, l, r)
        mid = (l + r) // 2
        self._update(2 * node, l, mid, lo, hi, delta, assign)
        self._update(2 * node + 1, mid + 1, r, lo, hi, delta, assign)
        self._pull(node)

    def range_add(self, lo: int, hi: int, delta: float) -> None:
        """Add ``delta`` to every element in ``[lo, hi]``."""
        if not _is_num(delta):
            raise LazySegmentTreeError("delta must be a number")
        with self._lock:
            self._validate_range(lo, hi)
            self._update(1, 0, self._n - 1, lo, hi, delta, None)

    def range_assign(self, lo: int, hi: int, value: float) -> None:
        """Set every element in ``[lo, hi]`` to ``value``."""
        if not _is_num(value):
            raise LazySegmentTreeError("value must be a number")
        with self._lock:
            self._validate_range(lo, hi)
            self._update(1, 0, self._n - 1, lo, hi, None, value)

    # ── range queries ──────────────────────────────────────────────────────────────────────
    def _query(self, node: int, l: int, r: int, lo: int, hi: int, kind: str) -> float:
        if lo <= l and r <= hi:
            if kind == "sum":
                return self._sum[node]
            if kind == "min":
                return self._min[node]
            return self._max[node]
        self._push(node, l, r)
        mid = (l + r) // 2
        if hi <= mid:
            return self._query(2 * node, l, mid, lo, hi, kind)
        if lo > mid:
            return self._query(2 * node + 1, mid + 1, r, lo, hi, kind)
        left = self._query(2 * node, l, mid, lo, hi, kind)
        right = self._query(2 * node + 1, mid + 1, r, lo, hi, kind)
        if kind == "sum":
            return left + right
        if kind == "min":
            return min(left, right)
        return max(left, right)

    def range_sum(self, lo: int, hi: int) -> float:
        """Sum over ``[lo, hi]``."""
        with self._lock:
            self._validate_range(lo, hi)
            return self._query(1, 0, self._n - 1, lo, hi, "sum")

    def range_min(self, lo: int, hi: int) -> float:
        """Minimum over ``[lo, hi]``."""
        with self._lock:
            self._validate_range(lo, hi)
            return self._query(1, 0, self._n - 1, lo, hi, "min")

    def range_max(self, lo: int, hi: int) -> float:
        """Maximum over ``[lo, hi]``."""
        with self._lock:
            self._validate_range(lo, hi)
            return self._query(1, 0, self._n - 1, lo, hi, "max")

    def point_query(self, i: int) -> float:
        """Value at index ``i``."""
        with self._lock:
            if not _is_int(i):
                raise LazySegmentTreeError("i must be an int")
            if not (0 <= i < self._n):
                raise LazySegmentTreeError(f"i must be in [0, {self._n - 1}]")
            return self._query(1, 0, self._n - 1, i, i, "sum")

    def reset(self) -> None:
        """Empty the structure."""
        with self._lock:
            self._clear()

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    def stats(self) -> dict:
        """Summary: ``size`` / ``total`` / ``min`` / ``max``."""
        with self._lock:
            if self._n == 0:
                return {"size": 0, "total": 0, "min": None, "max": None}
            return {
                "size": self._n,
                "total": self._sum[1],
                "min": self._min[1],
                "max": self._max[1],
            }
