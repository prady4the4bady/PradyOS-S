"""Phase 138 — Sovereign Sparse Table (Bender & Farach-Colton).

A **static range-minimum / range-maximum index** answering queries in `O(1)` after
`O(n log n)` preprocessing — a new capability for the platform. It precomputes, for every
power-of-two length `2ᵏ`, the aggregate of each block of that length:

    table[0][i] = arr[i]
    table[k][i] = op(table[k−1][i], table[k−1][i + 2^{k−1}])

Any half-open range `[l, r)` is then covered by **two overlapping power-of-two blocks** — with
`k = ⌊log₂(r − l)⌋`, the answer is `op(table[k][l], table[k][r − 2ᵏ])`. Because the blocks may
overlap, this is exact only for **idempotent** aggregates (`op(x, x) = x`) — i.e. `min` and
`max` — which is precisely the range-min/max problem.

This is *different* from the platform's **dynamic** Segment Tree (P81), which supports point
updates with `O(log n)` queries: a sparse table is **static** (built once, no updates) but
answers in `O(1)` — the right tradeoff for immutable data. Pure stdlib; thread-safe via a
single ``threading.Lock``; deterministic (static — built once from the array).
"""

from __future__ import annotations

import threading
from typing import Any, Iterable

_OPS = {"min": min, "max": max}


class SparseTableError(Exception):
    """Raised for an invalid Sparse-table operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class SparseTable:
    """Static O(1) range-min/max index over a numeric array (doubling table)."""

    def __init__(self, values: Any = None, op: str = "min") -> None:
        self._lock = threading.Lock()
        self._build("" if values is None else values, op)

    # ── build ──────────────────────────────────────────────────────────────────────────
    def _build_locked(self, values: Iterable[Any], op: str) -> None:
        if op not in _OPS:
            raise SparseTableError("op must be 'min' or 'max'")
        try:
            arr = list(values)
        except TypeError as exc:
            raise SparseTableError("values must be iterable") from exc
        for v in arr:
            if not _num(v):
                raise SparseTableError(f"every value must be a number, got {v!r}")

        agg = _OPS[op]
        n = len(arr)
        table = [arr[:]] if n else []
        k = 1
        while (1 << k) <= n:
            prev = table[k - 1]
            half = 1 << (k - 1)
            length = 1 << k
            table.append([agg(prev[i], prev[i + half]) for i in range(n - length + 1)])
            k += 1

        self._op = op
        self._agg = agg
        self._arr = arr
        self._n = n
        self._table = table

    def _build(self, values: Iterable[Any], op: str) -> None:
        with self._lock:
            self._build_locked(values, op)

    def build(self, values: Iterable[Any], op: str | None = None) -> None:
        """(Re)build the table from ``values`` (static — replaces any prior contents).
        ``op`` defaults to the current aggregate."""
        with self._lock:
            self._build_locked(values, self._op if op is None else op)

    # ── query (O(1)) ───────────────────────────────────────────────────────────────────
    def query(self, lo: int, hi: int) -> Any:
        """Aggregate (``min`` or ``max``) over the half-open range ``[lo, hi)``."""
        if not _is_int(lo) or not _is_int(hi):
            raise SparseTableError("lo and hi must be ints")
        with self._lock:
            if not (0 <= lo < hi <= self._n):
                raise SparseTableError(f"need 0 <= lo < hi <= {self._n}")
            k = (hi - lo).bit_length() - 1            # floor(log2(hi - lo)), hi-lo >= 1
            block = 1 << k
            row = self._table[k]
            return self._agg(row[lo], row[hi - block])

    def get(self, i: int) -> Any:
        """The value at index ``i`` (``i`` in ``[0, n)``)."""
        if not _is_int(i):
            raise SparseTableError("i must be an int")
        with self._lock:
            if not (0 <= i < self._n):
                raise SparseTableError(f"i must be in [0, {self._n - 1}]")
            return self._arr[i]

    def reset(self, op: str | None = None) -> None:
        """Empty the table; optionally change the aggregate ``op``."""
        with self._lock:
            self._build_locked([], self._op if op is None else op)

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def op(self) -> str:
        return self._op

    @property
    def levels(self) -> int:
        return len(self._table)

    def stats(self) -> dict:
        """Summary: ``size`` / ``op`` / ``levels``."""
        with self._lock:
            return {"size": self._n, "op": self._op, "levels": len(self._table)}
