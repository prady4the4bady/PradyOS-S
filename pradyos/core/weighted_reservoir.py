"""Phase 98 — Sovereign Weighted Reservoir Sampling (Efraimidis–Spirakis "A-Res", 2006).

Maintains a random sample of ``k`` items from a stream of ``(item, weight)`` pairs
in one pass and ``O(k)`` space, where an item is retained with probability
**proportional to its weight** — unlike Phase 85's uniform reservoir (Vitter's
Algorithm R), which samples every item equally.

Algorithm (A-Res): each arriving item is assigned a random *priority key*
``key = u ** (1 / weight)`` with ``u ∼ Uniform(0, 1)``. A **min-heap** keeps the
``k`` items with the largest keys: while fewer than ``k`` are held the item is
pushed; otherwise, if its key beats the smallest retained key, it replaces it.
Because larger weights push ``1/weight`` toward 0 and thus ``u**(1/weight)`` toward
1, heavier items win more often — sampling proportional to weight.

This algorithm is **randomized** (a departure from the recent deterministic
phases): a ``random.Random(seed)`` makes it reproducible and injectable for tests.
``reset()`` clears the reservoir but deliberately does **not** re-seed the RNG —
the generator state continues, which is correct for a long-lived stateful sampler.
Weights must be strictly positive; ``k`` must be ≥ 1. Pure stdlib. Thread-safe via
a single ``threading.Lock``; internal ``_*_locked`` helpers never re-acquire it.
"""

from __future__ import annotations

import heapq
import random
import threading
from typing import Any


class WeightedReservoirError(Exception):
    """Raised for an invalid Weighted-Reservoir configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class WeightedReservoir:
    """A-Res weighted reservoir sampler: retain k items with probability ∝ weight."""

    def __init__(self, k: int, seed: int = 0) -> None:
        if not _is_pos_int(k):
            raise WeightedReservoirError("k must be at least 1")
        if not _is_int(seed):
            raise WeightedReservoirError(seed)
        self._k = k
        self._seed = seed
        self._rng = random.Random(seed)
        self._heap: list[tuple] = []  # min-heap of (key, counter, item)
        self._counter = 0  # tiebreaker so items are never compared
        self._n = 0  # total items seen
        self._lock = threading.Lock()

    # ── internal (run under the lock; never re-acquire) ──────────────────────────
    def _update_locked(self, item: Any, weight: float) -> None:
        self._n += 1
        u = self._rng.random()
        key = u ** (1.0 / weight)
        self._counter += 1
        entry = (key, self._counter, item)
        if len(self._heap) < self._k:
            heapq.heappush(self._heap, entry)
        elif key > self._heap[0][0]:
            heapq.heapreplace(self._heap, entry)

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, item: Any, weight: float = 1.0) -> None:
        """Observe ``item`` with a strictly positive ``weight``."""
        if not _is_number(weight) or weight <= 0:
            raise WeightedReservoirError("weight must be positive")
        with self._lock:
            self._update_locked(item, float(weight))

    def reset(self) -> None:
        """Clear the reservoir and item count (the RNG state is *not* re-seeded)."""
        with self._lock:
            self._heap = []
            self._counter = 0
            self._n = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def sample(self) -> list:
        """The current reservoir contents as a list (order not guaranteed; [] if empty)."""
        with self._lock:
            return [item for _key, _cnt, item in self._heap]

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
    def n(self) -> int:
        with self._lock:
            return self._n

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._heap)

    def stats(self) -> dict:
        """Summary: capacity ``k``, total items seen ``n``, current reservoir ``size``, ``seed``."""
        with self._lock:
            return {
                "k": self._k,
                "n": self._n,
                "size": len(self._heap),
                "seed": self._seed,
            }
