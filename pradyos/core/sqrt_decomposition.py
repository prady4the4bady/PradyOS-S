"""Phase 147 — Sovereign Sqrt Decomposition (block decomposition with lazy tags).

A **block-decomposition range structure** supporting `O(√n)` **range-add** and **range-sum** —
a new *technique* for the platform, distinct from the Segment Tree of P81 (`O(log n)` with full
lazy propagation) and the point-update Fenwick of P80.

The array is split into `≈√n` contiguous blocks. Each block stores the **sum of its elements**
and a **lazy `add` tag** that has been applied conceptually to every element of the block but
not yet pushed down. A range update touches the `O(√n)` fully-covered blocks via their tag
(`tag[b] += delta`) and the two partial boundary blocks element-wise (updating both the element
and its block sum); a range query sums each covered block's `block_sum + tag·block_len` plus the
partial ends — both `O(√n)`. The true value of element `i` is `a[i] + tag[block(i)]`.

This is *different* from the platform's other range structures: a deliberately simple `O(√n)`
block method with lazy tags — the classic stepping-stone to segment-tree lazy propagation.
Supports `range_add`, `range_sum`, `point_query`, and absolute point `update`. Pure stdlib;
thread-safe via a single ``threading.Lock``; deterministic; every operation is iterative.
"""

from __future__ import annotations

import math
from typing import Any

import threading


class SqrtDecompositionError(Exception):
    """Raised for an invalid sqrt-decomposition operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class SqrtDecomposition:
    """Array with O(√n) range-add (lazy block tags) and range-sum."""

    def __init__(self, values: Any = None) -> None:
        self._lock = threading.Lock()
        self._build([] if values is None else values)

    # ── build ──────────────────────────────────────────────────────────────────────────
    def _build_locked(self, values: Any) -> None:
        try:
            arr = list(values)
        except TypeError as exc:
            raise SqrtDecompositionError("values must be iterable") from exc
        for v in arr:
            if not _is_num(v):
                raise SqrtDecompositionError(f"every value must be a number, got {v!r}")
        n = len(arr)
        bs = max(1, int(math.isqrt(n))) if n else 1
        nblocks = (n + bs - 1) // bs if n else 0
        block_sum = [0] * nblocks
        for i, v in enumerate(arr):
            block_sum[i // bs] += v
        self._a = arr
        self._n = n
        self._bs = bs
        self._nblocks = nblocks
        self._block_sum = block_sum
        self._tag = [0] * nblocks

    def _build(self, values: Any) -> None:
        with self._lock:
            self._build_locked(values)

    def build(self, values: Any) -> None:
        """(Re)build from ``values`` (replaces any prior contents)."""
        with self._lock:
            self._build_locked(values)

    # ── helpers (under the lock) ───────────────────────────────────────────────────────
    def _block_bounds(self, b: int) -> tuple[int, int]:
        start = b * self._bs
        end = min(start + self._bs - 1, self._n - 1)
        return start, end

    # ── range add (lazy) ───────────────────────────────────────────────────────────────
    def range_add(self, lo: int, hi: int, delta: float) -> None:
        """Add ``delta`` to every element in ``[lo, hi]`` (inclusive)."""
        if not _is_int(lo) or not _is_int(hi):
            raise SqrtDecompositionError("lo and hi must be ints")
        if not _is_num(delta):
            raise SqrtDecompositionError("delta must be a number")
        with self._lock:
            if not (0 <= lo <= hi < self._n):
                raise SqrtDecompositionError(f"need 0 <= lo <= hi < {self._n}")
            a, bs, bsum, tag = self._a, self._bs, self._block_sum, self._tag
            i = lo
            while i <= hi:
                b = i // bs
                start, end = self._block_bounds(b)
                if i == start and end <= hi:
                    tag[b] += delta
                    i = end + 1
                else:
                    a[i] += delta
                    bsum[b] += delta
                    i += 1

    # ── range sum ──────────────────────────────────────────────────────────────────────
    def range_sum(self, lo: int, hi: int) -> float:
        """Sum of the elements in ``[lo, hi]`` (inclusive)."""
        if not _is_int(lo) or not _is_int(hi):
            raise SqrtDecompositionError("lo and hi must be ints")
        with self._lock:
            if not (0 <= lo <= hi < self._n):
                raise SqrtDecompositionError(f"need 0 <= lo <= hi < {self._n}")
            a, bs, bsum, tag = self._a, self._bs, self._block_sum, self._tag
            s = 0
            i = lo
            while i <= hi:
                b = i // bs
                start, end = self._block_bounds(b)
                if i == start and end <= hi:
                    s += bsum[b] + tag[b] * (end - start + 1)
                    i = end + 1
                else:
                    s += a[i] + tag[b]
                    i += 1
            return s

    def point_query(self, i: int) -> float:
        """The value of element ``i`` (base value plus its block's lazy tag)."""
        if not _is_int(i):
            raise SqrtDecompositionError("i must be an int")
        with self._lock:
            if not (0 <= i < self._n):
                raise SqrtDecompositionError(f"i must be in [0, {self._n - 1}]")
            return self._a[i] + self._tag[i // self._bs]

    def update(self, i: int, value: float) -> None:
        """Set element ``i`` to the absolute ``value``."""
        if not _is_int(i):
            raise SqrtDecompositionError("i must be an int")
        if not _is_num(value):
            raise SqrtDecompositionError("value must be a number")
        with self._lock:
            if not (0 <= i < self._n):
                raise SqrtDecompositionError(f"i must be in [0, {self._n - 1}]")
            b = i // self._bs
            delta = value - (self._a[i] + self._tag[b])
            self._a[i] += delta
            self._block_sum[b] += delta

    def total(self) -> float:
        """Sum over the whole array."""
        with self._lock:
            return sum(self._block_sum) + sum(
                self._tag[b] * (self._block_bounds(b)[1] - self._block_bounds(b)[0] + 1)
                for b in range(self._nblocks))

    def reset(self) -> None:
        """Empty the structure."""
        with self._lock:
            self._build_locked([])

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def block_size(self) -> int:
        return self._bs

    @property
    def num_blocks(self) -> int:
        return self._nblocks

    def stats(self) -> dict:
        """Summary: ``size`` / ``block_size`` / ``num_blocks`` / ``total``."""
        with self._lock:
            total = sum(self._block_sum) + sum(
                self._tag[b] * (self._block_bounds(b)[1] - self._block_bounds(b)[0] + 1)
                for b in range(self._nblocks))
            return {"size": self._n, "block_size": self._bs,
                    "num_blocks": self._nblocks, "total": total}
