"""Phase 92 — Sovereign KLL Sketch (Karnin–Lang–Liberty, 2016).

A randomized, **space-optimal, natively mergeable** streaming-quantile sketch. It
maintains a hierarchy of *compactors* (one list per level ``h``); an item stored
at level ``h`` carries **weight** ``2**h`` (it stands in for ``2**h`` stream
items). New items enter level 0. When a compactor reaches its capacity it
**compacts**: sort it, then randomly keep either the even- or the odd-indexed
half (a fair coin discards one of each adjacent pair) and promote the survivors
to the next level — halving resolution as weight doubles. Each compaction
conserves total weight, so ``Σ over stored items of 2**h == n`` always holds.

Capacities shrink geometrically with height (``cap_h ≈ k·(2/3)**h``, floored at
2), so the total stored size is ``O(k)`` regardless of ``n`` while the number of
levels grows only as ``O(log(n/k))``; the rank error is ``O(n/k)`` with high
probability — asymptotically optimal for comparison-based sketches.

**Merge** is the defining advantage over Phase 91's Greenwald–Khanna: align two
sketches level-by-level, concatenate the compactors, and re-compact — combining
distributed sketches into one with the same guarantee. **Query** flattens every
stored item with its weight, sorts, and returns the weighted-rank ``⌈φn⌉`` value.

Randomness is per-*compaction* (not per-insert): a ``random.Random(seed)`` seeded
at init advances with each compaction, so a fixed insert sequence always yields
the same sketch. Pure stdlib. Thread-safe via a single ``threading.Lock``;
internal ``_*_locked`` helpers run under the lock and never re-acquire it.
"""

from __future__ import annotations

import math
import random
import threading
from typing import Any

_C = 2.0 / 3.0  # geometric capacity decay per level
_MIN_CAP = 2  # smallest compactor capacity


class KLLError(Exception):
    """Raised for an invalid KLL configuration / operation. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid kll sketch configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class KLLSketch:
    """Karnin–Lang–Liberty quantile sketch: space-optimal and mergeable."""

    def __init__(self, k: int = 200, seed: int = 0) -> None:
        if not _is_pos_int(k) or k < 2:
            raise KLLError(k)
        if not _is_int(seed):
            raise KLLError(seed)
        self._k = k
        self._seed = seed
        self._rng = random.Random(seed)
        self._levels: list[list[float]] = [[]]  # levels[h] has weight 2**h
        self._n = 0
        self._lock = threading.Lock()

    # ── capacity schedule ─────────────────────────────────────────────────────────
    def _capacity(self, h: int) -> int:
        # Each compactor fills to k before compacting. Uniform capacity keeps a
        # full-resolution buffer at every weight (the high-weight top levels must
        # NOT be starved — a tiny top compactor would let a few heavy items skew
        # the estimate), while compaction still bounds the total to O(k·log(n/k)).
        return self._k

    # ── compaction (run under the lock; never re-acquire) ────────────────────────
    def _compact_level(self, h: int) -> None:
        items = sorted(self._levels[h])
        if len(items) % 2 == 1:
            # leftover singleton stays in this level (randomise which end → unbiased)
            if self._rng.randint(0, 1):
                keep, items = [items[0]], items[1:]
            else:
                keep, items = [items[-1]], items[:-1]
        else:
            keep = []
        offset = self._rng.randint(0, 1)
        promoted = items[offset::2]
        self._levels[h] = keep
        if h + 1 == len(self._levels):
            self._levels.append([])
        self._levels[h + 1].extend(promoted)

    def _compress(self) -> None:
        h = 0
        while h < len(self._levels):
            if len(self._levels[h]) >= self._capacity(h):
                self._compact_level(h)
            h += 1

    def _insert_locked(self, value: float) -> None:
        self._levels[0].append(float(value))
        self._n += 1
        self._compress()

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, value: Any) -> None:
        """Observe one numeric ``value``."""
        if not _is_number(value):
            raise KLLError(value)
        with self._lock:
            self._insert_locked(value)

    def update_many(self, values: Any) -> int:
        """Observe every value in ``values``; return how many were added."""
        vals = list(values)
        for x in vals:
            if not _is_number(x):
                raise KLLError(x)
        with self._lock:
            for x in vals:
                self._insert_locked(x)
            return len(vals)

    def merge(self, other: KLLSketch) -> None:
        """Fold another KLL sketch into this one (the native KLL advantage)."""
        if not isinstance(other, KLLSketch):
            raise KLLError(other)
        with other._lock:
            other_levels = [list(level) for level in other._levels]
            other_n = other._n
        with self._lock:
            for h, level in enumerate(other_levels):
                while h >= len(self._levels):
                    self._levels.append([])
                self._levels[h].extend(level)  # same level ⇒ same weight 2**h
            self._n += other_n
            # Re-compact bottom-up until every level is within capacity.
            changed = True
            while changed:
                changed = False
                h = 0
                while h < len(self._levels):
                    if len(self._levels[h]) >= self._capacity(h):
                        self._compact_level(h)
                        changed = True
                    h += 1

    def reset(self, k: int | None = None, seed: int | None = None) -> None:
        """Clear the sketch; optionally reconfigure ``k`` / ``seed``."""
        with self._lock:
            if k is not None:
                if not _is_pos_int(k) or k < 2:
                    raise KLLError(k)
                self._k = k
            if seed is not None:
                if not _is_int(seed):
                    raise KLLError(seed)
                self._seed = seed
            self._rng = random.Random(self._seed)
            self._levels = [[]]
            self._n = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def _weighted_items_locked(self) -> list[tuple[float, int]]:
        items: list[tuple[float, int]] = []
        for h, level in enumerate(self._levels):
            w = 1 << h
            for v in level:
                items.append((v, w))
        items.sort()
        return items

    def query(self, phi: float) -> float | None:
        """The ``phi``-quantile (``phi`` in [0, 1]); ``None`` if the sketch is empty."""
        if not _is_number(phi) or not (0.0 <= phi <= 1.0):
            raise KLLError(phi)
        with self._lock:
            if self._n == 0:
                return None
            items = self._weighted_items_locked()
            if phi <= 0.0:
                return items[0][0]
            if phi >= 1.0:
                return items[-1][0]
            target = math.ceil(phi * self._n)
            cum = 0
            for v, w in items:
                cum += w
                if cum >= target:
                    return v
            return items[-1][0]

    def rank(self, value: Any) -> int:
        """Estimated number of stored items ``≤ value`` (weighted rank)."""
        if not _is_number(value):
            raise KLLError(value)
        with self._lock:
            cum = 0
            for v, w in self._weighted_items_locked():
                if v <= value:
                    cum += w
                else:
                    break
            return cum

    def count(self) -> int:
        """Total number of observed values, ``n``."""
        with self._lock:
            return self._n

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def k(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_levels(self) -> int:
        with self._lock:
            return len(self._levels)

    def _stored_locked(self) -> int:
        return sum(len(level) for level in self._levels)

    def stats(self) -> dict:
        """Summary: ``k``, stream size ``n``, ``num_levels``, ``num_compactors``
        (total items stored), and ``sketch_size_ratio = num_compactors / n``."""
        with self._lock:
            stored = self._stored_locked()
            return {
                "k": self._k,
                "n": self._n,
                "num_levels": len(self._levels),
                "num_compactors": stored,
                "sketch_size_ratio": round(stored / self._n, 6) if self._n else 0.0,
            }
