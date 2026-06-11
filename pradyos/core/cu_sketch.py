"""Phase 123 — Sovereign Conservative-Update Count-Min Sketch / CU Sketch (Estan & Varghese, 2002).

A frequency sketch that is *strictly more accurate* than the platform's Count-Min (P76)
by changing only the **update rule**. Like Count-Min it keeps a ``depth × width`` grid of
counters and reports ``estimate(x) = min`` of ``x``'s ``depth`` hashed counters. But where
Count-Min increments **all** ``depth`` counters on every add, the conservative update
raises **only the counter(s) currently at the minimum** (and any tied with it):

    est = min over the d cells of x
    for each cell c of x:   counter[c] = max(counter[c], est + amount)

Cells already above ``est + amount`` are left alone, so a heavy hitter stops inflating the
counters it happens to share with light items. This provably **never under-counts** (the
minimum still rises by the inserted mass) and **never exceeds the Count-Min estimate** —
but typically slashes over-estimation. The trade-off: conservative update cannot be
reversed (lowering a counter could corrupt other keys), so — unlike the Counting Bloom or
plain Count-Min — it is an **insert-and-query** estimator with no ``delete``.

A *different* algorithm from Count-Min/P76 (all-counter increment) and Count-Sketch/P94
(signed counters + median): the same ``m``/``k`` grid, smarter writes. Hashing is
double-hashing ``h_i(x) = (h1 + i·h2) mod width`` from one seeded BLAKE2b digest (the
Counting-Bloom/P107 idiom). Counters are arbitrary-width Python ints (no saturation). Pure
stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any


class CUSketchError(Exception):
    """Raised for an invalid CU-Sketch operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class CUSketch:
    """Conservative-update Count-Min: tighter frequency estimates, insert-and-query."""

    def __init__(self, width: int = 2048, depth: int = 4, seed: int = 0) -> None:
        if not _is_pos_int(width):
            raise CUSketchError(width)
        if not _is_pos_int(depth):
            raise CUSketchError(depth)
        if not _is_int(seed):
            raise CUSketchError(seed)
        self._w = width
        self._d = depth
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    def _init_state(self) -> None:
        # depth rows of width counters, flat for speed: index r*w + col.
        self._counters = [0] * (self._w * self._d)
        self._total = 0

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _indices(self, item: Any) -> list[int]:
        """One flat cell index per row via double-hashing from a seeded BLAKE2b digest."""
        data = repr((self._seed, item)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1  # odd → full period under mod w
        w = self._w
        return [r * w + ((h1 + r * h2) % w) for r in range(self._d)]

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, item: Any, amount: int = 1) -> None:
        """Add ``amount`` occurrences of ``item`` using the conservative-update rule."""
        if not _is_pos_int(amount):
            raise CUSketchError(amount)
        with self._lock:
            cells = self._indices(item)
            counters = self._counters
            est = min(counters[c] for c in cells)
            target = est + amount
            for c in cells:
                if counters[c] < target:  # raise only the lagging counters
                    counters[c] = target
            self._total += amount

    def estimate(self, item: Any) -> int:
        """Estimated frequency of ``item`` — the minimum of its ``depth`` counters."""
        with self._lock:
            counters = self._counters
            return min(counters[c] for c in self._indices(item))

    def reset(
        self, width: int | None = None, depth: int | None = None, seed: int | None = None
    ) -> None:
        """Clear all counters; optionally reconfigure ``width`` / ``depth`` / ``seed``."""
        with self._lock:
            nw = self._w if width is None else width
            nd = self._d if depth is None else depth
            ns = self._seed if seed is None else seed
            if not _is_pos_int(nw):
                raise CUSketchError(nw)
            if not _is_pos_int(nd):
                raise CUSketchError(nd)
            if not _is_int(ns):
                raise CUSketchError(ns)
            self._w, self._d, self._seed = nw, nd, ns
            self._init_state()

    @property
    def width(self) -> int:
        return self._w

    @property
    def depth(self) -> int:
        return self._d

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def total(self) -> int:
        """Total mass inserted (Σ amount)."""
        with self._lock:
            return self._total

    def stats(self) -> dict:
        """Summary: ``width`` / ``depth`` / ``total`` / ``num_counters`` / ``seed``."""
        with self._lock:
            return {
                "width": self._w,
                "depth": self._d,
                "total": self._total,
                "num_counters": self._w * self._d,
                "seed": self._seed,
            }
