"""Phase 146 — Sovereign 2D Fenwick Tree / 2D Binary Indexed Tree (Fenwick, 1994).

A **2-D point-update / rectangle-sum index** in `O(log²n)` per operation — a new capability for
the platform (the Fenwick Tree of P80 is one-dimensional). Over an `R × C` grid it keeps, at
each internal `(i, j)`, the sum of a rectangle of cells determined by the low-bits of `i` and
`j`. `update(i, j, delta)` walks `i += i & -i`, `j += j & -j`; a prefix sum walks them down with
`i -= i & -i`. The sum of any axis-aligned sub-rectangle is then **four prefix sums** by
inclusion-exclusion:

    range_sum(r1,c1,r2,c2) = P(r2,c2) − P(r1−1,c2) − P(r2,c1−1) + P(r1−1,c1−1)

where `P(i,j)` is the sum of the rectangle `[0..i] × [0..j]`.

This is *different* from the 1-D Fenwick (P80) and the range-*min* structures (Sparse
Table/P138, Cartesian Tree/P145): it answers 2-D rectangle *sum* queries under point updates.
Supports `update`, `point_value`, `prefix_sum`, `range_sum`, and `total`. Pure stdlib;
thread-safe via a single ``threading.Lock``; deterministic; every operation is iterative.
"""

from __future__ import annotations

from typing import Any

import threading


class Fenwick2DError(Exception):
    """Raised for an invalid 2D-Fenwick operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class Fenwick2D:
    """2-D Binary Indexed Tree: point updates, O(log²n) rectangle sums."""

    def __init__(self, rows: int = 16, cols: int = 16) -> None:
        self._validate_dims(rows, cols)
        self._rows = rows
        self._cols = cols
        self._tree = [[0] * (cols + 1) for _ in range(rows + 1)]   # 1-indexed internally
        self._lock = threading.Lock()

    @staticmethod
    def _validate_dims(rows: Any, cols: Any) -> None:
        if not _is_pos_int(rows) or not _is_pos_int(cols):
            raise Fenwick2DError("rows and cols must be positive ints")

    # ── update ────────────────────────────────────────────────────────────────────────
    def update(self, i: int, j: int, delta: float) -> None:
        """Add ``delta`` to cell ``(i, j)`` (0-indexed)."""
        if not _is_int(i) or not _is_int(j):
            raise Fenwick2DError("i and j must be ints")
        if not _is_num(delta):
            raise Fenwick2DError("delta must be a number")
        with self._lock:
            if not (0 <= i < self._rows and 0 <= j < self._cols):
                raise Fenwick2DError(f"(i, j) out of range [0,{self._rows}) x [0,{self._cols})")
            tree, R, C = self._tree, self._rows, self._cols
            ii = i + 1
            while ii <= R:
                jj = j + 1
                while jj <= C:
                    tree[ii][jj] += delta
                    jj += jj & -jj
                ii += ii & -ii

    # ── prefix / range sums ──────────────────────────────────────────────────────────
    def _prefix(self, i: int, j: int) -> float:
        """Sum of ``[0..i] x [0..j]`` (0-indexed inclusive); ``i`` or ``j`` < 0 → 0."""
        if i < 0 or j < 0:
            return 0
        tree = self._tree
        s = 0
        ii = i + 1
        while ii > 0:
            jj = j + 1
            while jj > 0:
                s += tree[ii][jj]
                jj -= jj & -jj
            ii -= ii & -ii
        return s

    def prefix_sum(self, i: int, j: int) -> float:
        """Sum of the rectangle ``[0..i] x [0..j]`` (0-indexed inclusive)."""
        if not _is_int(i) or not _is_int(j):
            raise Fenwick2DError("i and j must be ints")
        with self._lock:
            if not (0 <= i < self._rows and 0 <= j < self._cols):
                raise Fenwick2DError(f"(i, j) out of range [0,{self._rows}) x [0,{self._cols})")
            return self._prefix(i, j)

    def range_sum(self, r1: int, c1: int, r2: int, c2: int) -> float:
        """Sum of the rectangle ``[r1..r2] x [c1..c2]`` (0-indexed inclusive)."""
        if not all(_is_int(v) for v in (r1, c1, r2, c2)):
            raise Fenwick2DError("all coordinates must be ints")
        with self._lock:
            if not (0 <= r1 <= r2 < self._rows and 0 <= c1 <= c2 < self._cols):
                raise Fenwick2DError("require 0 <= r1 <= r2 < rows and 0 <= c1 <= c2 < cols")
            return (self._prefix(r2, c2) - self._prefix(r1 - 1, c2)
                    - self._prefix(r2, c1 - 1) + self._prefix(r1 - 1, c1 - 1))

    def point_value(self, i: int, j: int) -> float:
        """The accumulated value at cell ``(i, j)``."""
        if not _is_int(i) or not _is_int(j):
            raise Fenwick2DError("i and j must be ints")
        with self._lock:
            if not (0 <= i < self._rows and 0 <= j < self._cols):
                raise Fenwick2DError(f"(i, j) out of range [0,{self._rows}) x [0,{self._cols})")
            return (self._prefix(i, j) - self._prefix(i - 1, j)
                    - self._prefix(i, j - 1) + self._prefix(i - 1, j - 1))

    def total(self) -> float:
        """Sum over the whole grid."""
        with self._lock:
            return self._prefix(self._rows - 1, self._cols - 1)

    def reset(self, rows: int | None = None, cols: int | None = None) -> None:
        """Zero the grid; optionally reconfigure ``rows`` / ``cols``."""
        with self._lock:
            nr = self._rows if rows is None else rows
            nc = self._cols if cols is None else cols
            self._validate_dims(nr, nc)
            self._rows = nr
            self._cols = nc
            self._tree = [[0] * (nc + 1) for _ in range(nr + 1)]

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cols(self) -> int:
        return self._cols

    def stats(self) -> dict:
        """Summary: ``rows`` / ``cols`` / ``cells`` / ``total``."""
        with self._lock:
            return {"rows": self._rows, "cols": self._cols, "cells": self._rows * self._cols,
                    "total": self._prefix(self._rows - 1, self._cols - 1)}
