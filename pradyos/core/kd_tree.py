"""Phase 139 — Sovereign KD-Tree (Bentley, 1975).

A **k-dimensional spatial index** for nearest-neighbour and orthogonal range search — the
platform's first *spatial* structure. Points are stored in a binary tree that **cycles through
the dimensions by depth**: the root splits on axis 0, its children on axis 1, …, wrapping
around every `k` levels, so each node partitions space by one coordinate. The tree is built by
**median split** per axis, which keeps it balanced (height `O(log n)`).

Queries:

  * ``nearest(point)`` descends to the leaf region containing the query, then **backtracks,
    pruning any subtree whose splitting plane is farther than the best squared distance found
    so far** — that subtree cannot contain a closer point;
  * ``range(lo, hi)`` reports every stored point inside the axis-aligned box `[lo, hi]`,
    pruning a child whenever the box does not reach across its splitting plane.

This is *different* from the platform's one-dimensional ordered maps and the interval tree —
it answers *multidimensional proximity* queries. Nearest-neighbour compares **squared**
distances (no `sqrt`), so it is exact. Pure stdlib; thread-safe via a single
``threading.Lock``; deterministic (static — built once from the point set).
"""

from __future__ import annotations

import threading
from typing import Any, Iterable


class KDTreeError(Exception):
    """Raised for an invalid KD-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("point", "axis", "left", "right")

    def __init__(self, point: tuple, axis: int) -> None:
        self.point = point
        self.axis = axis
        self.left: "_Node | None" = None
        self.right: "_Node | None" = None


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class KDTree:
    """Static k-d spatial index (nearest-neighbour + orthogonal range search)."""

    def __init__(self, points: Any = None, dim: int = 2) -> None:
        if not _is_pos_int(dim):
            raise KDTreeError("dim must be a positive int")
        self._dim = dim
        self._lock = threading.Lock()
        self._build([] if points is None else points)

    # ── validation ────────────────────────────────────────────────────────────────────
    def _coerce_point(self, point: Any, what: str = "point") -> tuple:
        try:
            p = tuple(point)
        except TypeError as exc:
            raise KDTreeError(f"{what} must be a sequence of {self._dim} numbers") from exc
        if len(p) != self._dim:
            raise KDTreeError(f"{what} must have {self._dim} coordinates, got {len(p)}")
        if not all(_num(c) for c in p):
            raise KDTreeError(f"{what} coordinates must be numbers")
        return p

    # ── build (median split per axis → balanced) ──────────────────────────────────────
    def _build_locked(self, points: Iterable[Any]) -> None:
        try:
            raw = list(points)
        except TypeError as exc:
            raise KDTreeError("points must be iterable") from exc
        pts = [self._coerce_point(p) for p in raw]
        self._size = len(pts)
        self._root = self._make(pts, 0)

    def _make(self, pts: list, depth: int) -> "_Node | None":
        if not pts:
            return None
        axis = depth % self._dim
        pts.sort(key=lambda p: p[axis])
        mid = len(pts) // 2
        node = _Node(pts[mid], axis)
        node.left = self._make(pts[:mid], depth + 1)
        node.right = self._make(pts[mid + 1:], depth + 1)
        return node

    def _build(self, points: Iterable[Any]) -> None:
        with self._lock:
            self._build_locked(points)

    def build(self, points: Iterable[Any]) -> None:
        """(Re)build the tree from ``points`` (static — replaces any prior contents)."""
        with self._lock:
            self._build_locked(points)

    # ── nearest neighbour (backtracking with splitting-plane pruning) ─────────────────
    def _dist2(self, a: tuple, b: tuple) -> float:
        return sum((a[i] - b[i]) ** 2 for i in range(self._dim))

    def nearest(self, point: Any) -> tuple | None:
        """Return the stored point nearest to ``point`` (Euclidean), or ``None`` if empty."""
        q = self._coerce_point(point, "query point")
        with self._lock:
            best = [None, float("inf")]          # [point, dist²]
            self._nn(self._root, q, best)
            return best[0]

    def _nn(self, node: "_Node | None", q: tuple, best: list) -> None:
        if node is None:
            return
        d2 = self._dist2(q, node.point)
        if d2 < best[1]:
            best[0], best[1] = node.point, d2
        axis = node.axis
        diff = q[axis] - node.point[axis]
        near, far = (node.left, node.right) if diff < 0 else (node.right, node.left)
        self._nn(near, q, best)
        if diff * diff < best[1]:                # the plane is closer than the best → far may help
            self._nn(far, q, best)

    def nearest_dist(self, point: Any) -> float | None:
        """Euclidean distance to the nearest stored point, or ``None`` if empty."""
        q = self._coerce_point(point, "query point")
        with self._lock:
            best = [None, float("inf")]
            self._nn(self._root, q, best)
            return None if best[0] is None else best[1] ** 0.5

    # ── orthogonal range search ────────────────────────────────────────────────────────
    def range(self, lo: Any, hi: Any) -> list:
        """All stored points inside the inclusive axis-aligned box ``[lo, hi]``, sorted."""
        a = self._coerce_point(lo, "lo")
        b = self._coerce_point(hi, "hi")
        for i in range(self._dim):
            if a[i] > b[i]:
                raise KDTreeError(f"lo[{i}] ({a[i]}) must be <= hi[{i}] ({b[i]})")
        with self._lock:
            out: list = []
            self._range(self._root, a, b, out)
            out.sort()
            return out

    def _range(self, node: "_Node | None", lo: tuple, hi: tuple, out: list) -> None:
        if node is None:
            return
        p = node.point
        if all(lo[i] <= p[i] <= hi[i] for i in range(self._dim)):
            out.append(p)
        axis = node.axis
        if lo[axis] <= p[axis]:                  # left holds coords ≤ p[axis]
            self._range(node.left, lo, hi, out)
        if hi[axis] >= p[axis]:                   # right holds coords ≥ p[axis]
            self._range(node.right, lo, hi, out)

    def reset(self) -> None:
        """Empty the tree (keeps the configured dimension)."""
        with self._lock:
            self._build_locked([])

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def dim(self) -> int:
        return self._dim

    def _height(self) -> int:
        if self._root is None:
            return 0
        h = 0
        stack = [(self._root, 1)]
        while stack:
            node, d = stack.pop()
            if d > h:
                h = d
            if node.left is not None:
                stack.append((node.left, d + 1))
            if node.right is not None:
                stack.append((node.right, d + 1))
        return h

    def height(self) -> int:
        with self._lock:
            return self._height()

    def stats(self) -> dict:
        """Summary: ``size`` / ``dim`` / ``height``."""
        with self._lock:
            return {"size": self._size, "dim": self._dim, "height": self._height()}
