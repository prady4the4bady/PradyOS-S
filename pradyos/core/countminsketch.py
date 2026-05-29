"""Phase 76 — Sovereign Frequency Sketch (Count-Min Sketch).

Estimates the frequency of items in a stream using fixed sublinear memory. The
sketch is a ``depth × width`` grid of counters; each item is hashed into one
cell per row and those cells are incremented. The estimate is the *minimum* of
an item's cells across all rows — collisions can only inflate a counter, so the
estimate **never under-counts** (it is an upper bound on the true frequency).

Each row's hash is derived by Kirsch–Mitzenmacher double-hashing — two
independent 64-bit halves of a single SHA-256 digest (``h1`` and an odd ``h2``)
combine as ``(h1 + row * h2) % width`` to give ``depth`` independent row
positions from two seeds. Pure stdlib (``hashlib``); thread-safe via a single
non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading


class CountMinSketch:
    """Approximate per-item frequency counter (stdlib only)."""

    def __init__(self, width: int = 2000, depth: int = 5) -> None:
        if width <= 0 or depth <= 0:
            raise ValueError("width and depth must be positive integers")
        self._width = int(width)
        self._depth = int(depth)
        self._rows = [[0] * self._width for _ in range(self._depth)]
        self._total = 0
        self._lock = threading.Lock()

    # ── hashing (no lock; pure) ──────────────────────────────────────────────
    def _positions(self, item) -> list[int]:
        data = item.encode("utf-8") if isinstance(item, str) else repr(item).encode("utf-8")
        digest = hashlib.sha256(data).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") | 1  # odd → independent, non-degenerate
        return [(h1 + row * h2) % self._width for row in range(self._depth)]

    # ── mutation ──────────────────────────────────────────────────────────────
    def add(self, item, count: int = 1) -> None:
        """Add ``count`` occurrences of ``item`` (count must be a positive integer)."""
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer")
        positions = self._positions(item)
        with self._lock:
            for row in range(self._depth):
                self._rows[row][positions[row]] += count
            self._total += count

    def clear(self) -> None:
        """Reset all counters to zero."""
        with self._lock:
            self._rows = [[0] * self._width for _ in range(self._depth)]
            self._total = 0

    # ── query ─────────────────────────────────────────────────────────────────
    def estimate(self, item) -> int:
        """Estimated frequency of ``item`` (an upper bound — never under-counts)."""
        positions = self._positions(item)
        with self._lock:
            return min(self._rows[row][positions[row]] for row in range(self._depth))

    def merge(self, other: "CountMinSketch") -> "CountMinSketch":
        """Return a NEW sketch that is the element-wise sum of ``self`` and ``other``.

        Both must share identical ``width`` and ``depth``. Neither input is mutated.
        """
        if (not isinstance(other, CountMinSketch)
                or other._width != self._width or other._depth != self._depth):
            raise ValueError("can only merge a CountMinSketch with identical width and depth")
        with self._lock:
            a_rows = [row[:] for row in self._rows]
            a_total = self._total
        with other._lock:
            b_rows = [row[:] for row in other._rows]
            b_total = other._total
        result = CountMinSketch(self._width, self._depth)
        result._rows = [
            [a_rows[r][c] + b_rows[r][c] for c in range(self._width)]
            for r in range(self._depth)
        ]
        result._total = a_total + b_total
        return result

    # ── introspection ─────────────────────────────────────────────────────────
    @property
    def width(self) -> int:
        return self._width

    @property
    def depth(self) -> int:
        return self._depth

    def stats(self) -> dict:
        """JSON-serialisable snapshot of dimensions and total observations."""
        with self._lock:
            return {
                "width": self._width,
                "depth": self._depth,
                "cells": self._width * self._depth,
                "total": self._total,
            }
