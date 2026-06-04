"""Phase 157 — Sovereign Range Tree (Bentley, 1979).

A **2-D orthogonal range-search structure**: given a fixed set of points, it answers "which points
lie in an axis-aligned rectangle `[x_min, x_max] × [y_min, y_max]`" in `O(log²n + k)` (report) and
`O(log²n)` (count). It is a balanced binary search tree keyed on `x` in which **every node also
stores its subtree's points pre-sorted by `y`**; a query descends to the `O(log n)` *canonical*
`x`-nodes whose x-range is fully contained in `[x_min, x_max]`, and binary-searches each canonical
node's y-array for the y-interval.

This is the *textbook layered* orthogonal-range structure — distinct from the space-subdividing PR
Quadtree/P153 and the median-split KD-Tree/P139, which answer the same query with different shapes
and without the `O(log²n)` worst-case guarantee. It is **static** (built once from a point set).

The primary tree is built balanced by splitting the x-sorted array at its midpoint, so build
recursion depth is `O(log n)` (structurally bounded — never degenerate); the query is iterative
over an explicit stack. Each node's y-array is produced by an `O(n)` merge of its children's
y-arrays (so build is `O(n log n)`). Pure stdlib; thread-safe via a single ``threading.Lock``;
deterministic.
"""

from __future__ import annotations

import bisect
from typing import Any, Optional

import threading


class RangeTreeError(Exception):
    """Raised for an invalid range-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class _RTNode:
    __slots__ = ("xmin", "xmax", "ys", "pts", "left", "right")

    def __init__(self) -> None:
        self.xmin = 0.0
        self.xmax = 0.0
        self.ys: list = []                  # subtree y-values, ascending
        self.pts: list = []                 # subtree points (x, y), ordered by y (parallel to ys)
        self.left: Optional[_RTNode] = None
        self.right: Optional[_RTNode] = None


class RangeTree:
    """Static 2-D orthogonal range search: O(log²n) rectangle count / O(log²n + k) report."""

    def __init__(self, points: Any = None) -> None:
        self._lock = threading.Lock()
        self._root: Optional[_RTNode] = None
        self._size = 0
        if points is not None:
            self.build(points)

    # ── build ────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _merge_by_y(a: list, b: list) -> list:
        out = []
        i = j = 0
        la, lb = len(a), len(b)
        while i < la and j < lb:
            if a[i][1] <= b[j][1]:
                out.append(a[i]); i += 1
            else:
                out.append(b[j]); j += 1
        if i < la:
            out.extend(a[i:])
        if j < lb:
            out.extend(b[j:])
        return out

    def _build(self, arr: list) -> _RTNode:
        # arr is sorted by (x, y); build a balanced node over it
        node = _RTNode()
        if len(arr) == 1:
            x, y = arr[0]
            node.xmin = node.xmax = x
            node.pts = [arr[0]]
            node.ys = [y]
            return node
        mid = len(arr) // 2
        node.left = self._build(arr[:mid])
        node.right = self._build(arr[mid:])
        node.xmin = node.left.xmin
        node.xmax = node.right.xmax
        node.pts = self._merge_by_y(node.left.pts, node.right.pts)
        node.ys = [p[1] for p in node.pts]
        return node

    def build(self, points: Any) -> None:
        """(Re)build from ``points`` (an iterable of ``(x, y)``); replaces any prior contents."""
        try:
            raw = list(points)
        except TypeError as exc:
            raise RangeTreeError("points must be iterable") from exc
        pts = []
        for p in raw:
            if not (isinstance(p, (list, tuple)) and len(p) == 2 and _is_num(p[0]) and _is_num(p[1])):
                raise RangeTreeError("each point must be a (x, y) pair of numbers")
            pts.append((p[0], p[1]))
        with self._lock:
            self._size = len(pts)
            if not pts:
                self._root = None
            else:
                pts.sort()
                self._root = self._build(pts)

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def _check_rect(self, x_min, y_min, x_max, y_max) -> None:
        if not all(_is_num(v) for v in (x_min, y_min, x_max, y_max)):
            raise RangeTreeError("rectangle bounds must be numbers")
        if x_min > x_max or y_min > y_max:
            raise RangeTreeError("require x_min <= x_max and y_min <= y_max")

    def range_query(self, x_min, y_min, x_max, y_max) -> list:
        """Sorted list of ``(x, y)`` points inside ``[x_min, x_max] × [y_min, y_max]``."""
        self._check_rect(x_min, y_min, x_max, y_max)
        out: list = []
        with self._lock:
            stack = [self._root]
            while stack:
                node = stack.pop()
                if node is None:
                    continue
                if node.xmax < x_min or node.xmin > x_max:
                    continue                                # disjoint in x
                if x_min <= node.xmin and node.xmax <= x_max:   # canonical: x fully covered
                    lo = bisect.bisect_left(node.ys, y_min)
                    hi = bisect.bisect_right(node.ys, y_max)
                    out.extend(node.pts[lo:hi])
                else:
                    stack.append(node.left)
                    stack.append(node.right)
        out.sort()
        return out

    def range_count(self, x_min, y_min, x_max, y_max) -> int:
        """Number of points inside ``[x_min, x_max] × [y_min, y_max]``."""
        self._check_rect(x_min, y_min, x_max, y_max)
        count = 0
        with self._lock:
            stack = [self._root]
            while stack:
                node = stack.pop()
                if node is None:
                    continue
                if node.xmax < x_min or node.xmin > x_max:
                    continue
                if x_min <= node.xmin and node.xmax <= x_max:
                    lo = bisect.bisect_left(node.ys, y_min)
                    hi = bisect.bisect_right(node.ys, y_max)
                    count += hi - lo
                else:
                    stack.append(node.left)
                    stack.append(node.right)
        return count

    def reset(self) -> None:
        """Discard all points."""
        with self._lock:
            self._root = None
            self._size = 0

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    def height(self) -> int:
        """Height of the primary x-tree (0 if empty)."""
        with self._lock:
            h = 0
            node = self._root
            while node is not None:
                h += 1
                node = node.left
            return h

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``x_min`` / ``x_max``."""
        with self._lock:
            if self._root is None:
                return {"size": 0, "height": 0, "x_min": None, "x_max": None}
            h = 0
            node = self._root
            while node is not None:
                h += 1
                node = node.left
            return {"size": self._size, "height": h,
                    "x_min": self._root.xmin, "x_max": self._root.xmax}
