"""Phase 148 — Sovereign Li Chao Tree (convex-hull-trick line container).

A **line container** over a fixed integer x-domain `[x_min, x_max]`: it maintains a set of lines
`y = m·x + b` and answers the **minimum (or maximum) `y` at any query `x`** in `O(log C)`, where
`C = x_max − x_min + 1`. This is the platform's *first* convex-hull-trick / kinetic-line
structure — distinct from every range-sum / range-min index (Fenwick/P80, Segment Tree/P81,
Sparse Table/P138, Cartesian Tree/P145, 2D Fenwick/P146, Sqrt Decomposition/P147) and the
spatial KD-Tree/P139.

It is an implicit segment tree over the x-range. Each node owns the single line that is dominant
at its segment **midpoint**. ``add_line`` compares the incoming line against the node's line at
the midpoint, keeps the winner there, and pushes the loser down into the *one* half-segment where
it can still become dominant (the classic Li Chao trick — the loser can cross the winner in at
most one half). ``query(x)`` descends the root→leaf path for ``x`` and takes the best value among
the lines stored on that path.

Max-mode is handled by storing negated lines and negating the answer, so the same min machinery
serves both. The add/query descents are **iterative** (segment depth is only `O(log C)`, but we
avoid recursion entirely per platform discipline). Pure stdlib; thread-safe via a single
``threading.Lock``; deterministic.
"""

from __future__ import annotations

import threading
from typing import Any


class LiChaoTreeError(Exception):
    """Raised for an invalid Li-Chao-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class LiChaoTree:
    """Line container: add ``y = m·x + b``, query min/max ``y`` at ``x`` in ``O(log C)``."""

    def __init__(self, x_min: int = 0, x_max: int = 1_000_000, mode: str = "min") -> None:
        self._lock = threading.Lock()
        self._configure(x_min, x_max, mode)

    # ── (re)configuration ────────────────────────────────────────────────────────────────
    def _configure(self, x_min: Any, x_max: Any, mode: Any) -> None:
        if not _is_int(x_min) or not _is_int(x_max):
            raise LiChaoTreeError("x_min and x_max must be ints")
        if x_min > x_max:
            raise LiChaoTreeError("require x_min <= x_max")
        if mode not in ("min", "max"):
            raise LiChaoTreeError("mode must be 'min' or 'max'")
        self._lo = x_min
        self._hi = x_max
        self._mode = mode
        self._sign = 1 if mode == "min" else -1
        self._lines: dict[tuple[int, int], tuple[float, float]] = {}  # (l, r) -> (m, b)
        self._count = 0

    # ── add_line ─────────────────────────────────────────────────────────────────────────
    def add_line(self, m: float, b: float) -> None:
        """Insert the line ``y = m·x + b`` into the container."""
        if not _is_num(m) or not _is_num(b):
            raise LiChaoTreeError("m and b must be numbers")
        with self._lock:
            # store with the sign convention so the min-machinery serves max-mode too
            new = (self._sign * m, self._sign * b)
            lines = self._lines
            stack = [(self._lo, self._hi, new)]
            while stack:
                l, r, ln = stack.pop()
                cur = lines.get((l, r))
                if cur is None:
                    lines[(l, r)] = ln
                    continue
                mid = (l + r) // 2
                left_better = ln[0] * l + ln[1] < cur[0] * l + cur[1]
                mid_better = ln[0] * mid + ln[1] < cur[0] * mid + cur[1]
                if mid_better:
                    lines[(l, r)] = ln
                    ln = cur  # the loser descends
                if l == r:
                    continue
                if left_better != mid_better:
                    stack.append((l, mid, ln))
                else:
                    stack.append((mid + 1, r, ln))
            self._count += 1

    # ── query ────────────────────────────────────────────────────────────────────────────
    def query(self, x: int) -> float | None:
        """Best ``y`` (min by default, max in max-mode) at ``x``; ``None`` if no lines."""
        if not _is_int(x):
            raise LiChaoTreeError("x must be an int")
        with self._lock:
            if not (self._lo <= x <= self._hi):
                raise LiChaoTreeError(f"x must be in [{self._lo}, {self._hi}]")
            if not self._lines:
                return None
            lines = self._lines
            l, r = self._lo, self._hi
            best: float | None = None
            while True:
                cur = lines.get((l, r))
                if cur is not None:
                    val = cur[0] * x + cur[1]
                    if best is None or val < best:
                        best = val
                if l == r:
                    break
                mid = (l + r) // 2
                if x <= mid:
                    r = mid
                else:
                    l = mid + 1
            return None if best is None else self._sign * best

    # ── maintenance ──────────────────────────────────────────────────────────────────────
    def reset(
        self, x_min: int | None = None, x_max: int | None = None, mode: str | None = None
    ) -> None:
        """Clear all lines; optionally reconfigure the domain / mode."""
        with self._lock:
            nlo = self._lo if x_min is None else x_min
            nhi = self._hi if x_max is None else x_max
            nmode = self._mode if mode is None else mode
            self._configure(nlo, nhi, nmode)

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._count

    @property
    def num_lines(self) -> int:
        return self._count

    @property
    def x_min(self) -> int:
        return self._lo

    @property
    def x_max(self) -> int:
        return self._hi

    @property
    def mode(self) -> str:
        return self._mode

    def stats(self) -> dict:
        """Summary: ``num_lines`` / ``x_min`` / ``x_max`` / ``mode`` / ``nodes``."""
        with self._lock:
            return {
                "num_lines": self._count,
                "x_min": self._lo,
                "x_max": self._hi,
                "mode": self._mode,
                "nodes": len(self._lines),
            }
