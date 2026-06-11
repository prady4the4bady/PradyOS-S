"""Phase 85 — Sovereign Reservoir Sampler.

Draws a statistically uniform random sample of fixed size ``k`` from a stream of
unknown length in O(k) memory and one pass — without ever storing the whole
stream. Implements Vitter's **Algorithm R**: the first ``k`` items fill the
reservoir; thereafter the ``i``-th item (0-based) replaces a uniformly chosen
reservoir slot with probability ``k / (i + 1)``. At any moment every item seen so
far is equally likely (``k / n``) to be in the reservoir.

The RNG is injectable (``random_fn``, a zero-arg callable returning a float in
``[0, 1)``, default :func:`random.random`) so sampling is deterministic in tests.
Pure stdlib. Thread-safe via a single ``threading.Lock``; the public surface
acquires it, and internal helpers that run under the lock never re-acquire it
(the lock is non-reentrant).
"""

from __future__ import annotations

import random
import threading
from collections.abc import Callable, Iterable
from typing import Any


class ReservoirError(Exception):
    """Raised when a reservoir capacity is not a positive integer.

    The offending value is preserved on the ``capacity`` attribute.
    """

    def __init__(self, capacity: Any) -> None:
        self.capacity = capacity
        super().__init__(f"invalid reservoir capacity: {capacity!r}")


def _valid_capacity(k: Any) -> bool:
    return isinstance(k, int) and not isinstance(k, bool) and k >= 1


class SovereignReservoir:
    """Fixed-size uniform reservoir sampler over a stream (stdlib only)."""

    def __init__(self, k: int, random_fn: Callable[[], float] | None = None) -> None:
        if not _valid_capacity(k):
            raise ReservoirError(k)
        self._k = k
        self._random_fn = random_fn or random.random
        self._reservoir: list = []
        self._seen = 0
        self._lock = threading.Lock()

    # ── internal (callers already hold the lock) ─────────────────────────────
    def _feed_locked(self, item: Any) -> None:
        i = self._seen
        if i < self._k:
            self._reservoir.append(item)
        else:
            # uniform integer in [0, i]; replace the slot if it lands in-bounds
            j = int(self._random_fn() * (i + 1))
            if j < self._k:
                self._reservoir[j] = item
        self._seen += 1

    # ── mutation ──────────────────────────────────────────────────────────────
    def feed(self, item: Any) -> None:
        """Stream a single item through the sampler (Algorithm R step)."""
        with self._lock:
            self._feed_locked(item)

    def feed_many(self, items: Iterable[Any]) -> int:
        """Stream every item in ``items``; return how many were fed."""
        count = 0
        with self._lock:
            for item in items:
                self._feed_locked(item)
                count += 1
        return count

    def reset(self, k: int | None = None) -> None:
        """Clear the stream; optionally resize the reservoir to ``k``."""
        with self._lock:
            if k is not None:
                if not _valid_capacity(k):
                    raise ReservoirError(k)
                self._k = k
            self._reservoir = []
            self._seen = 0

    # ── queries ─────────────────────────────────────────────────────────────
    def sample(self) -> list:
        """The current reservoir contents (a copy; unordered, size ≤ k)."""
        with self._lock:
            return list(self._reservoir)

    def __len__(self) -> int:
        with self._lock:
            return len(self._reservoir)

    @property
    def capacity(self) -> int:
        with self._lock:
            return self._k

    @property
    def seen(self) -> int:
        with self._lock:
            return self._seen

    def stats(self) -> dict:
        """Stream metadata: capacity, items seen, and current fill."""
        with self._lock:
            return {
                "capacity": self._k,
                "seen": self._seen,
                "filled": len(self._reservoir),
            }
