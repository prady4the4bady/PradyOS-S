"""Phase 167 — Sovereign Convex Hull (Andrew's monotone chain, 1979).

The platform's first **computational-geometry** structure. From a set of 2-D points it builds the
**convex hull** — the smallest convex polygon containing them — in `O(n log n)`: sort the (unique)
points by `(x, y)`, sweep left-to-right building the **lower** chain, then right-to-left building
the **upper** chain, each time popping a vertex that would make a non-left (clockwise) turn. It then
answers `hull()` (vertices counter-clockwise), `area()` (shoelace), `perimeter()`, and
`contains(x, y)` (point inside-or-on the hull).

This opens a domain distinct from the spatial *point-set* indices (KD-Tree/P139, PR Quadtree/P153,
Range Tree/P157), which answer range / nearest queries rather than computing a hull. The orientation
test is an **exact integer cross-product** when the inputs are ints, so the hull has no
floating-point error; only `area`/`perimeter` involve floats. Collinear interior points are excluded
(strict turns), duplicates are removed, and `< 3`-point inputs degenerate gracefully. Static (built
once). Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic; iterative.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class ConvexHullError(Exception):
    """Raised for an invalid convex-hull operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _cross(o, a, b):
    """Cross product (a-o) x (b-o); > 0 = left/CCW turn, 0 = collinear, < 0 = right/CW."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


class ConvexHull:
    """Convex hull of a 2-D point set (monotone chain): hull / area / perimeter / point-in-hull."""

    def __init__(self, points: Any = None) -> None:
        self._lock = threading.Lock()
        self._points: list = []  # unique input points, sorted
        self._hull: list = []  # hull vertices, CCW
        if points is not None:
            self.build(points)

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, points: Any) -> None:
        """(Re)build the hull from ``points`` (an iterable of ``(x, y)``)."""
        try:
            raw = list(points)
        except TypeError as exc:
            raise ConvexHullError("points must be iterable") from exc
        cleaned = []
        for p in raw:
            if not (
                isinstance(p, list | tuple) and len(p) == 2 and _is_num(p[0]) and _is_num(p[1])
            ):
                raise ConvexHullError("each point must be an (x, y) pair of numbers")
            cleaned.append((p[0], p[1]))
        pts = sorted(set(cleaned))
        with self._lock:
            self._points = pts
            self._hull = self._monotone_chain(pts)

    @staticmethod
    def _monotone_chain(pts: list) -> list:
        n = len(pts)
        if n <= 2:
            return pts[:]  # 0, 1, or 2 points: hull is the points themselves
        lower = []
        for p in pts:
            while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]  # CCW; drop shared endpoints

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def hull(self) -> list:
        """The hull vertices as ``(x, y)`` tuples, counter-clockwise."""
        with self._lock:
            return [tuple(p) for p in self._hull]

    def area(self) -> float:
        """Area enclosed by the hull (0 for fewer than 3 hull vertices)."""
        with self._lock:
            h = self._hull
            if len(h) < 3:
                return 0.0
            s = 0
            for i in range(len(h)):
                x1, y1 = h[i]
                x2, y2 = h[(i + 1) % len(h)]
                s += x1 * y2 - x2 * y1
            return abs(s) / 2.0

    def perimeter(self) -> float:
        """Perimeter of the hull (segment length for 2 points; 0 for fewer)."""
        with self._lock:
            h = self._hull
            if len(h) < 2:
                return 0.0
            if len(h) == 2:
                return math.dist(h[0], h[1])
            total = 0.0
            for i in range(len(h)):
                total += math.dist(h[i], h[(i + 1) % len(h)])
            return total

    def contains(self, x: float, y: float) -> bool:
        """True iff ``(x, y)`` lies inside or on the hull."""
        if not _is_num(x) or not _is_num(y):
            raise ConvexHullError("x and y must be numbers")
        with self._lock:
            h = self._hull
            p = (x, y)
            if len(h) == 0:
                return False
            if len(h) == 1:
                return p == h[0]
            if len(h) == 2:
                a, b = h[0], h[1]
                if _cross(a, b, p) != 0:
                    return False
                return min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(
                    a[1], b[1]
                )
            # convex polygon (CCW): inside-or-on iff left of / on every edge
            for i in range(len(h)):
                if _cross(h[i], h[(i + 1) % len(h)], p) < 0:
                    return False
            return True

    def reset(self) -> None:
        """Discard all points."""
        with self._lock:
            self._points = []
            self._hull = []

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._points) == 0

    def __len__(self) -> int:
        return len(self._points)

    @property
    def num_points(self) -> int:
        return len(self._points)

    @property
    def num_hull_points(self) -> int:
        return len(self._hull)

    def stats(self) -> dict:
        """Summary: ``num_points`` / ``num_hull_points`` / ``area`` / ``perimeter``."""
        with self._lock:
            h = self._hull
            area = 0.0
            if len(h) >= 3:
                s = 0
                for i in range(len(h)):
                    x1, y1 = h[i]
                    x2, y2 = h[(i + 1) % len(h)]
                    s += x1 * y2 - x2 * y1
                area = abs(s) / 2.0
            if len(h) < 2:
                per = 0.0
            elif len(h) == 2:
                per = math.dist(h[0], h[1])
            else:
                per = sum(math.dist(h[i], h[(i + 1) % len(h)]) for i in range(len(h)))
            return {
                "num_points": len(self._points),
                "num_hull_points": len(h),
                "area": area,
                "perimeter": per,
            }
