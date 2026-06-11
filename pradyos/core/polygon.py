"""Phase 168 — Sovereign Simple Polygon (ordered-vertex polygon geometry).

The platform's second **computational-geometry** structure, and a deliberate complement to the
Convex Hull (P167): where the hull *computes* the smallest convex polygon over an unordered point
*set* (sorting and de-duplicating its input), a :class:`Polygon` is defined by an **ordered list of
vertices** — order is significant and preserved verbatim, so the shape may be **non-convex**. From
that vertex ring it answers:

* ``area()``        — the enclosed area via the **shoelace** formula (``O(n)``).
* ``perimeter()``   — the sum of edge lengths.
* ``contains(x, y)``— **point-in-polygon** by even-odd **ray casting**, with an explicit on-boundary
                      test first so a point on an edge or vertex counts as inside (``O(n)``).
* ``is_convex()``   — whether every turn has the same orientation (no sign flip in the edge
                      cross-products).
* ``orientation()`` — ``"CCW"`` / ``"CW"`` / ``"degenerate"`` from the sign of the signed area.
* ``centroid()``    — the area-weighted polygon centroid (the vertex mean for a degenerate / zero-area
                      ring), distinct from the simple average of the vertices.

The headline ``contains`` is cross-checked in the test-suite two independent ways — ray casting vs a
**winding-number** implementation — over random convex, star-shaped and non-convex polygons, plus a
fine-grid brute force on small shapes. Orientation / cross-products are **exact integer arithmetic**
when the inputs are ints; only ``area`` / ``perimeter`` / ``centroid`` involve floats. Static once
built. Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic; fully iterative.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class PolygonError(Exception):
    """Raised for an invalid polygon operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _cross(o, a, b):
    """Cross product (a-o) x (b-o); > 0 = left/CCW turn, 0 = collinear, < 0 = right/CW."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(a, b, p) -> bool:
    """True iff point ``p`` lies on the closed segment ``a``–``b`` (exact when ints)."""
    if _cross(a, b, p) != 0:
        return False
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


class Polygon:
    """A simple polygon defined by an ordered vertex ring: area / perimeter / contains / convexity."""

    def __init__(self, vertices: Any = None) -> None:
        self._lock = threading.Lock()
        self._verts: list = []  # vertices in input order (NOT sorted / deduped)
        if vertices is not None:
            self.build(vertices)

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, vertices: Any) -> None:
        """(Re)build the polygon from an ordered iterable of ``(x, y)`` vertices."""
        try:
            raw = list(vertices)
        except TypeError as exc:
            raise PolygonError("vertices must be iterable") from exc
        cleaned = []
        for p in raw:
            if not (
                isinstance(p, list | tuple) and len(p) == 2 and _is_num(p[0]) and _is_num(p[1])
            ):
                raise PolygonError("each vertex must be an (x, y) pair of numbers")
            cleaned.append((p[0], p[1]))
        with self._lock:
            self._verts = cleaned  # order preserved verbatim

    # ── internal (lock already held) ─────────────────────────────────────────────────────
    def _signed_area2(self) -> float:
        """Twice the signed area (shoelace); > 0 CCW, < 0 CW."""
        v = self._verts
        n = len(v)
        if n < 3:
            return 0.0
        s = 0
        for i in range(n):
            x1, y1 = v[i]
            x2, y2 = v[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return s

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def area(self) -> float:
        """Enclosed area via the shoelace formula (0 for fewer than 3 vertices)."""
        with self._lock:
            return abs(self._signed_area2()) / 2.0

    def perimeter(self) -> float:
        """Sum of edge lengths around the ring (segment length for 2 vertices; 0 for fewer)."""
        with self._lock:
            v = self._verts
            n = len(v)
            if n < 2:
                return 0.0
            if n == 2:
                return math.dist(v[0], v[1])
            return sum(math.dist(v[i], v[(i + 1) % n]) for i in range(n))

    def contains(self, x: float, y: float) -> bool:
        """True iff ``(x, y)`` is inside or on the polygon (even-odd ray casting)."""
        if not _is_num(x) or not _is_num(y):
            raise PolygonError("x and y must be numbers")
        with self._lock:
            v = self._verts
            n = len(v)
            p = (x, y)
            if n == 0:
                return False
            if n == 1:
                return p == v[0]
            if n == 2:
                return _on_segment(v[0], v[1], p)
            # on the boundary → inside-or-on
            for i in range(n):
                if _on_segment(v[i], v[(i + 1) % n], p):
                    return True
            # strict interior: even-odd ray cast to +x
            inside = False
            j = n - 1
            for i in range(n):
                xi, yi = v[i]
                xj, yj = v[j]
                if (yi > y) != (yj > y):
                    x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
                    if x < x_cross:
                        inside = not inside
                j = i
            return inside

    def is_convex(self) -> bool:
        """True iff the polygon (≥ 3 vertices) turns the same way at every vertex."""
        with self._lock:
            v = self._verts
            n = len(v)
            if n < 3:
                return False
            sign = 0
            for i in range(n):
                c = _cross(v[i], v[(i + 1) % n], v[(i + 2) % n])
                if c != 0:
                    s = 1 if c > 0 else -1
                    if sign == 0:
                        sign = s
                    elif s != sign:
                        return False
            return True

    def orientation(self) -> str:
        """``"CCW"`` / ``"CW"`` / ``"degenerate"`` from the sign of the signed area."""
        with self._lock:
            a2 = self._signed_area2()
        if a2 > 0:
            return "CCW"
        if a2 < 0:
            return "CW"
        return "degenerate"

    def centroid(self):
        """Area-weighted centroid ``(cx, cy)``; vertex mean for a zero-area ring; ``None`` if empty."""
        with self._lock:
            v = self._verts
            n = len(v)
            if n == 0:
                return None
            a2 = self._signed_area2()
            if n < 3 or a2 == 0:
                return (sum(p[0] for p in v) / n, sum(p[1] for p in v) / n)
            cx = cy = 0.0
            for i in range(n):
                x1, y1 = v[i]
                x2, y2 = v[(i + 1) % n]
                w = x1 * y2 - x2 * y1
                cx += (x1 + x2) * w
                cy += (y1 + y2) * w
            return (cx / (3.0 * a2), cy / (3.0 * a2))

    def reset(self) -> None:
        """Discard all vertices."""
        with self._lock:
            self._verts = []

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._verts) == 0

    def vertices(self) -> list:
        """The vertices as ``(x, y)`` tuples, in input order."""
        with self._lock:
            return [tuple(p) for p in self._verts]

    def __len__(self) -> int:
        return len(self._verts)

    @property
    def num_vertices(self) -> int:
        return len(self._verts)

    def stats(self) -> dict:
        """Summary: ``num_vertices`` / ``area`` / ``perimeter`` / ``is_convex`` / ``orientation``."""
        with self._lock:
            v = self._verts
            n = len(v)
            a2 = self._signed_area2()
            area = abs(a2) / 2.0
            if n < 2:
                per = 0.0
            elif n == 2:
                per = math.dist(v[0], v[1])
            else:
                per = sum(math.dist(v[i], v[(i + 1) % n]) for i in range(n))
            # convexity (inline; lock already held)
            convex = False
            if n >= 3:
                sign = 0
                convex = True
                for i in range(n):
                    c = _cross(v[i], v[(i + 1) % n], v[(i + 2) % n])
                    if c != 0:
                        s = 1 if c > 0 else -1
                        if sign == 0:
                            sign = s
                        elif s != sign:
                            convex = False
                            break
            orient = "CCW" if a2 > 0 else ("CW" if a2 < 0 else "degenerate")
            return {
                "num_vertices": n,
                "area": area,
                "perimeter": per,
                "is_convex": convex,
                "orientation": orient,
            }
