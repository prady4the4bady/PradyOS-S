"""Phase 153 — Sovereign PR Quadtree (point-region quadtree; Finkel & Bentley, 1974).

A **2-D spatial index over a fixed rectangle** that stores *named* points and recursively
subdivides a cell into four equal quadrants whenever a leaf would hold more than one point (down
to ``max_depth``). It answers exact lookup, **axis-aligned rectangle range queries**, and
**nearest-neighbour** (Euclidean, branch-and-bound). It is the platform's first
space-subdivision-by-quadrant structure — distinct from the median-split KD-Tree/P139 (a static
nearest-neighbour index over the *points*): the quadtree subdivides *space* and supports dynamic
insert/delete with cell collapse.

Each node owns a rectangle; a leaf holds a small bucket of points, an internal node owns four
children (SW, SE, NW, NE by quadrant index ``qy*2+qx``). Subdivision depth is bounded by
``max_depth`` (never input-dependent), so descent is a bounded loop; range and nearest queries use
an explicit stack / min-heap (no recursion). A side ``id -> (x, y)`` index gives O(1) delete/move.
Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

import heapq
from typing import Any, Optional

import threading


class PRQuadtreeError(Exception):
    """Raised for an invalid PR-quadtree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class _QNode:
    __slots__ = ("x0", "y0", "x1", "y1", "depth", "leaf", "points", "children")

    def __init__(self, x0: float, y0: float, x1: float, y1: float, depth: int) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.depth = depth
        self.leaf = True
        self.points: dict = {}            # id -> (x, y)  (only when leaf)
        self.children: Optional[list] = None

    def quadrant(self, x: float, y: float) -> int:
        midx = (self.x0 + self.x1) / 2
        midy = (self.y0 + self.y1) / 2
        qx = 1 if x >= midx else 0
        qy = 1 if y >= midy else 0
        return qy * 2 + qx

    def child_bounds(self, idx: int) -> tuple:
        midx = (self.x0 + self.x1) / 2
        midy = (self.y0 + self.y1) / 2
        qx = idx & 1
        qy = idx >> 1
        cx0 = midx if qx else self.x0
        cx1 = self.x1 if qx else midx
        cy0 = midy if qy else self.y0
        cy1 = self.y1 if qy else midy
        return (cx0, cy0, cx1, cy1)

    def min_dist2(self, x: float, y: float) -> float:
        dx = self.x0 - x if x < self.x0 else (x - self.x1 if x > self.x1 else 0.0)
        dy = self.y0 - y if y < self.y0 else (y - self.y1 if y > self.y1 else 0.0)
        return dx * dx + dy * dy


class PRQuadtree:
    """Point-region quadtree: named points, rectangle range queries, nearest-neighbour."""

    def __init__(self, x_min: float, y_min: float, x_max: float, y_max: float,
                 max_depth: int = 12) -> None:
        if not all(_is_num(v) for v in (x_min, y_min, x_max, y_max)):
            raise PRQuadtreeError("bounds must be numbers")
        if not (x_min < x_max and y_min < y_max):
            raise PRQuadtreeError("require x_min < x_max and y_min < y_max")
        if not (isinstance(max_depth, int) and not isinstance(max_depth, bool) and max_depth >= 1):
            raise PRQuadtreeError("max_depth must be a positive int")
        self._x0 = x_min
        self._y0 = y_min
        self._x1 = x_max
        self._y1 = y_max
        self._max_depth = max_depth
        self._lock = threading.Lock()
        self._root = _QNode(x_min, y_min, x_max, y_max, 0)
        self._index: dict = {}            # id -> (x, y)

    def _check_point(self, x: Any, y: Any) -> None:
        if not _is_num(x) or not _is_num(y):
            raise PRQuadtreeError("x and y must be numbers")
        if not (self._x0 <= x <= self._x1 and self._y0 <= y <= self._y1):
            raise PRQuadtreeError("point is outside the quadtree bounds")

    # ── insert (move on duplicate id) ────────────────────────────────────────────────────
    def insert(self, point_id: Any, x: float, y: float) -> None:
        """Insert (or move) ``point_id`` at ``(x, y)``."""
        if point_id is None:
            raise PRQuadtreeError("point_id must not be None")
        try:
            hash(point_id)
        except TypeError as exc:
            raise PRQuadtreeError("point_id must be hashable") from exc
        self._check_point(x, y)
        with self._lock:
            if point_id in self._index:
                self._remove(point_id)
            self._index[point_id] = (x, y)
            node = self._root
            while True:
                if node.leaf:
                    node.points[point_id] = (x, y)
                    if len(node.points) <= 1 or node.depth >= self._max_depth:
                        return
                    bucket = node.points
                    node.leaf = False
                    node.points = {}
                    node.children = [
                        _QNode(*node.child_bounds(i), node.depth + 1) for i in range(4)]
                    for pid, (px, py) in bucket.items():
                        c = node.children[node.quadrant(px, py)]
                        c.points[pid] = (px, py)
                    node = node.children[node.quadrant(x, y)]
                else:
                    node = node.children[node.quadrant(x, y)]

    # ── delete (with collapse) ────────────────────────────────────────────────────────────
    def _remove(self, point_id: Any) -> None:
        """Remove a known-present id from the tree (index already handled by caller)."""
        x, y = self._index[point_id]
        path = []
        node = self._root
        while not node.leaf:
            path.append(node)
            node = node.children[node.quadrant(x, y)]
        node.points.pop(point_id, None)
        # collapse internal nodes whose children are all leaves totalling <= 1 point
        for parent in reversed(path):
            kids = parent.children
            if any(not k.leaf for k in kids):
                break
            merged = {}
            for k in kids:
                merged.update(k.points)
            if len(merged) > 1:
                break
            parent.leaf = True
            parent.points = merged
            parent.children = None

    def delete(self, point_id: Any) -> bool:
        """Delete ``point_id``; return True iff it was present."""
        with self._lock:
            if point_id not in self._index:
                return False
            self._remove(point_id)
            del self._index[point_id]
            return True

    # ── exact lookup by coordinate ────────────────────────────────────────────────────────
    def search(self, x: float, y: float) -> Optional[Any]:
        """Return a ``point_id`` located exactly at ``(x, y)``, or None."""
        if not _is_num(x) or not _is_num(y):
            raise PRQuadtreeError("x and y must be numbers")
        with self._lock:
            node = self._root
            while not node.leaf:
                node = node.children[node.quadrant(x, y)]
            best = None
            for pid, (px, py) in node.points.items():
                if px == x and py == y and (best is None or pid < best):
                    best = pid
            return best

    # ── rectangle range query ──────────────────────────────────────────────────────────────
    def range_query(self, x_min: float, y_min: float, x_max: float, y_max: float) -> list:
        """Return the sorted ids of all points inside ``[x_min, x_max] × [y_min, y_max]``."""
        if not all(_is_num(v) for v in (x_min, y_min, x_max, y_max)):
            raise PRQuadtreeError("rectangle bounds must be numbers")
        if x_min > x_max or y_min > y_max:
            raise PRQuadtreeError("require x_min <= x_max and y_min <= y_max")
        out = []
        with self._lock:
            stack = [self._root]
            while stack:
                node = stack.pop()
                if node.x1 < x_min or node.x0 > x_max or node.y1 < y_min or node.y0 > y_max:
                    continue
                if node.leaf:
                    for pid, (px, py) in node.points.items():
                        if x_min <= px <= x_max and y_min <= py <= y_max:
                            out.append(pid)
                else:
                    stack.extend(node.children)
        out.sort()
        return out

    # ── nearest neighbour (branch-and-bound) ───────────────────────────────────────────────
    def nearest(self, x: float, y: float) -> Optional[Any]:
        """Return the id of the point closest to ``(x, y)`` (Euclidean; ties → smallest id)."""
        if not _is_num(x) or not _is_num(y):
            raise PRQuadtreeError("x and y must be numbers")
        with self._lock:
            if not self._index:
                return None
            best_id = None
            best_d2 = float("inf")
            counter = 0
            heap = [(self._root.min_dist2(x, y), 0, self._root)]
            while heap:
                d2, _, node = heapq.heappop(heap)
                if d2 > best_d2:
                    break
                if node.leaf:
                    for pid, (px, py) in node.points.items():
                        pd2 = (px - x) ** 2 + (py - y) ** 2
                        if pd2 < best_d2 or (pd2 == best_d2 and (best_id is None or pid < best_id)):
                            best_d2 = pd2
                            best_id = pid
                else:
                    for c in node.children:
                        cm = c.min_dist2(x, y)
                        if cm <= best_d2:
                            counter += 1
                            heapq.heappush(heap, (cm, counter, c))
            return best_id

    # ── maintenance / introspection ──────────────────────────────────────────────────────
    def reset(self) -> None:
        """Clear all points."""
        with self._lock:
            self._root = _QNode(self._x0, self._y0, self._x1, self._y1, 0)
            self._index = {}

    def __len__(self) -> int:
        return len(self._index)

    @property
    def num_points(self) -> int:
        return len(self._index)

    def stats(self) -> dict:
        """Summary: ``num_points`` / ``num_nodes`` / ``max_depth_reached``."""
        with self._lock:
            num_nodes = 0
            max_depth_reached = 0
            stack = [self._root]
            while stack:
                node = stack.pop()
                num_nodes += 1
                if node.depth > max_depth_reached:
                    max_depth_reached = node.depth
                if not node.leaf:
                    stack.extend(node.children)
            return {"num_points": len(self._index), "num_nodes": num_nodes,
                    "max_depth_reached": max_depth_reached}
