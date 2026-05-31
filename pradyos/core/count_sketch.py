"""Phase 94 — Sovereign Count Sketch (Charikar–Chen–Farach-Colton, 2002).

Sub-linear **frequency** estimation that, unlike Phase 76's Count-Min Sketch,
yields an **unbiased** estimate. A ``depth × width`` integer table is paired with
two independent seeded hash families: a *bucket* hash ``h_i`` and a *sign* hash
``s_i ∈ {−1, +1}``. Each ``(element, count)`` update adds ``s_i(element)·count`` to
``table[i][h_i(element)]`` in every row ``i``. A point query reads
``table[i][h_i(x)]·s_i(x)`` from each row and returns the **median** of those
``depth`` signed readings.

The sign flip is the whole trick: a colliding element contributes ``±count`` with
equal probability, so collision noise cancels in expectation — the estimator is
**unbiased** (vs Count-Min's always-positive ``min``, which only over-counts). The
trade-off is symmetric noise: an element that was never inserted can read a small
**negative** estimate when it happens to collide with negatively-signed updates —
this is expected and correct behaviour for an unbiased sketch. The median over
``depth`` rows tolerates a few bad (heavily-collided) rows.

For heavy-hitter queries a side dict of every element seen is kept (the sketch
itself is not enumerable); ``heavy_hitters(threshold)`` re-estimates each and
returns those above ``threshold · total_count``. Updates accept **negative**
counts, so the sketch supports deletion. Pure stdlib; the hash families are
injectable for tests. Thread-safe via a single ``threading.Lock``; internal
``_*_locked`` helpers never re-acquire it.
"""

from __future__ import annotations

import hashlib
import statistics
import threading
from typing import Any, Callable


class CountSketchError(Exception):
    """Raised for an invalid Count-Sketch configuration / update. The value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid count sketch configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class CountSketch:
    """Unbiased frequency sketch via signed hashes and a median estimator."""

    def __init__(self, depth: int = 5, width: int = 2048, seed: int = 0,
                 bucket_fn: Callable[[int, Any], int] | None = None,
                 sign_fn: Callable[[int, Any], int] | None = None) -> None:
        if not _is_pos_int(depth):
            raise CountSketchError(depth)
        if not _is_pos_int(width):
            raise CountSketchError(width)
        if not _is_int(seed):
            raise CountSketchError(seed)
        self._depth = depth
        self._width = width
        self._seed = seed
        self._bucket_fn = bucket_fn
        self._sign_fn = sign_fn
        self._table = [[0] * width for _ in range(depth)]
        self._seen: set[Any] = set()
        self._total = 0
        self._lock = threading.Lock()

    # ── hash families (pure) ──────────────────────────────────────────────────────
    def _digest(self, tag: str, i: int, element: Any) -> int:
        data = repr((tag, self._seed, i, element)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")

    def _bucket(self, i: int, element: Any) -> int:
        raw = self._bucket_fn(i, element) if self._bucket_fn is not None \
            else self._digest("bucket", i, element)
        return raw % self._width

    def _sign(self, i: int, element: Any) -> int:
        raw = self._sign_fn(i, element) if self._sign_fn is not None \
            else self._digest("sign", i, element)
        return 1 if raw % 2 == 0 else -1

    # ── internal (run under the lock; never re-acquire) ──────────────────────────
    def _estimate_locked(self, element: Any) -> int:
        readings = [self._table[i][self._bucket(i, element)] * self._sign(i, element)
                    for i in range(self._depth)]
        return int(statistics.median(readings))

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, element: Any, count: int = 1) -> None:
        """Add ``count`` (which may be negative — deletion) occurrences of ``element``."""
        if not _is_int(count):
            raise CountSketchError(count)
        with self._lock:
            for i in range(self._depth):
                self._table[i][self._bucket(i, element)] += self._sign(i, element) * count
            self._total += count
            self._seen.add(element)

    def reset(self, depth: int | None = None, width: int | None = None,
              seed: int | None = None) -> None:
        """Clear the table and tracking dict; optionally reconfigure."""
        with self._lock:
            if depth is not None:
                if not _is_pos_int(depth):
                    raise CountSketchError(depth)
                self._depth = depth
            if width is not None:
                if not _is_pos_int(width):
                    raise CountSketchError(width)
                self._width = width
            if seed is not None:
                if not _is_int(seed):
                    raise CountSketchError(seed)
                self._seed = seed
            self._table = [[0] * self._width for _ in range(self._depth)]
            self._seen = set()
            self._total = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def estimate(self, element: Any) -> int:
        """Signed-median frequency estimate (0 for an unseen element in an empty table)."""
        with self._lock:
            return self._estimate_locked(element)

    def heavy_hitters(self, threshold: float) -> list[dict]:
        """Elements whose estimate exceeds ``threshold · total_count``, highest first."""
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise CountSketchError(threshold)
        with self._lock:
            cutoff = threshold * self._total
            hits = [(e, self._estimate_locked(e)) for e in self._seen]
            hits = [(e, est) for e, est in hits if est > cutoff]
            hits.sort(key=lambda pair: -pair[1])
            return [{"element": e, "estimate": est} for e, est in hits]

    def __len__(self) -> int:
        with self._lock:
            return self._total

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def width(self) -> int:
        return self._width

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def total_count(self) -> int:
        with self._lock:
            return self._total

    @property
    def unique_elements(self) -> int:
        with self._lock:
            return len(self._seen)

    def stats(self) -> dict:
        """Summary: ``depth``, ``width``, ``total_count``, ``unique_elements``, ``table_cells``."""
        with self._lock:
            return {
                "depth": self._depth,
                "width": self._width,
                "total_count": self._total,
                "unique_elements": len(self._seen),
                "table_cells": self._depth * self._width,
            }
