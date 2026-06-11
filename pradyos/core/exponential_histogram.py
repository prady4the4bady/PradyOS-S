"""Phase 97 — Sovereign Exponential Histogram (Datar–Gionis–Indyk–Motwani, 2002).

**Sliding-window** counting: how many 1-bits occurred in the last ``window`` ticks
of a binary stream, using only ``O((1/ε)·log²(window))`` space (it never stores
the raw stream). The window is summarised by a list of *buckets*, each
``(timestamp, size)`` with ``size`` a power of two, ordered oldest→newest. On each
update a fresh size-1 bucket is appended at the current tick; then, while more
than ``k = ⌈1/ε⌉`` buckets share a size, the two **oldest** of that size are
merged into one bucket of double the size (the merged bucket takes the *newer*
timestamp). Buckets older than ``window`` ticks are expired.

``count()`` returns ``Σ size − ½·(oldest surviving bucket's size)`` — the standard
DGIM end-correction, since the oldest bucket may straddle the window boundary.

**Guarantee:** ``count()`` estimates the number of 1-bits in the last ``window``
updates with **relative error ≤ ε/2** (a larger ``k``/smaller ``ε`` ⇒ tighter).

This is a binary-stream model (each update contributes a 1); ``value`` is the
number of 1-bits at that tick — fractional/weighted updates are *not* part of
DGIM. The algorithm is deterministic; ``seed`` is accepted for parity but unused.
Pure stdlib. Thread-safe via a single ``threading.Lock``; internal ``_*_locked``
helpers never re-acquire it.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class ExponentialHistogramError(Exception):
    """Raised for an invalid Exponential-Histogram config / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid exponential histogram operation: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class ExponentialHistogram:
    """DGIM sliding-window 1-bit counter with ``ε/2`` relative-error count."""

    def __init__(self, window: int, epsilon: float = 0.5, seed: Any = None) -> None:
        if not _is_pos_int(window):
            raise ExponentialHistogramError(window)
        if not _is_number(epsilon) or not (0.0 < epsilon <= 1.0):
            raise ExponentialHistogramError(epsilon)
        self._window = window
        self._epsilon = float(epsilon)
        self._seed = seed  # accepted for parity; deterministic → unused
        self._k = math.ceil(1.0 / self._epsilon)
        self._buckets: list[list[int]] = []  # [timestamp, size], oldest → newest
        self._now = -1  # latest timestamp seen (−1 = empty)
        self._lock = threading.Lock()

    # ── internal (run under the lock; never re-acquire) ──────────────────────────
    def _merge_locked(self) -> None:
        if not self._buckets:
            return
        size = 1
        max_size = max(b[1] for b in self._buckets)
        while size <= max_size:
            same = sorted((b for b in self._buckets if b[1] == size), key=lambda b: b[0])
            while len(same) > self._k:
                b1, b2 = same[0], same[1]  # the two oldest of this size
                ts_merged = max(b1[0], b2[0])  # merged bucket keeps the newer timestamp
                self._buckets.remove(b1)
                self._buckets.remove(b2)
                self._buckets.append([ts_merged, size * 2])
                max_size = max(max_size, size * 2)
                same = same[2:]
            size *= 2
        self._buckets.sort(key=lambda b: b[0])

    def _expire_locked(self) -> None:
        cutoff = self._now - self._window  # buckets at ts ≤ cutoff are outside the window
        self._buckets = [b for b in self._buckets if b[0] > cutoff]

    def _update_locked(self, value: int, timestamp: int | None) -> None:
        if timestamp is None:
            ts = self._now + 1
        else:
            if not _is_pos_int(timestamp) and timestamp != 0:
                raise ExponentialHistogramError(timestamp)
            if timestamp < self._now:
                raise ExponentialHistogramError(timestamp)  # timestamps are non-decreasing
            ts = timestamp
        self._now = ts
        for _ in range(value):
            self._buckets.append([ts, 1])
        self._merge_locked()
        self._expire_locked()

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, value: int = 1, timestamp: int | None = None) -> None:
        """Record ``value`` 1-bits at ``timestamp`` (defaults to the next internal tick)."""
        if not _is_pos_int(value):
            raise ExponentialHistogramError(value)
        with self._lock:
            self._update_locked(value, timestamp)

    def reset(
        self, window: int | None = None, epsilon: float | None = None, seed: Any = None
    ) -> None:
        """Clear all buckets and the tick counter; optionally reconfigure."""
        with self._lock:
            if window is not None:
                if not _is_pos_int(window):
                    raise ExponentialHistogramError(window)
                self._window = window
            if epsilon is not None:
                if not _is_number(epsilon) or not (0.0 < epsilon <= 1.0):
                    raise ExponentialHistogramError(epsilon)
                self._epsilon = float(epsilon)
                self._k = math.ceil(1.0 / self._epsilon)
            if seed is not None:
                self._seed = seed
            self._buckets = []
            self._now = -1

    # ── queries ──────────────────────────────────────────────────────────────────
    def count(self) -> float:
        """Estimated number of 1-bits in the last ``window`` ticks (DGIM end-correction)."""
        with self._lock:
            if not self._buckets:
                return 0
            total = sum(b[1] for b in self._buckets)
            oldest_size = self._buckets[0][1]  # buckets sorted oldest → newest
            return total - oldest_size / 2.0

    def oldest(self) -> int | None:
        """Timestamp of the oldest surviving bucket (``None`` when empty)."""
        with self._lock:
            return self._buckets[0][0] if self._buckets else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)

    @property
    def window(self) -> int:
        return self._window

    @property
    def epsilon(self) -> float:
        return self._epsilon

    @property
    def k(self) -> int:
        return self._k

    @property
    def now(self) -> int:
        with self._lock:
            return self._now

    @property
    def num_buckets(self) -> int:
        with self._lock:
            return len(self._buckets)

    def stats(self) -> dict:
        """Summary: ``window``, ``epsilon``, ``k``, ``num_buckets``, ``count``, ``oldest``, ``now``."""
        with self._lock:
            if self._buckets:
                total = sum(b[1] for b in self._buckets)
                count = total - self._buckets[0][1] / 2.0
                oldest = self._buckets[0][0]
            else:
                count, oldest = 0, None
            return {
                "window": self._window,
                "epsilon": self._epsilon,
                "k": self._k,
                "num_buckets": len(self._buckets),
                "count": count,
                "oldest": oldest,
                "now": self._now,
            }
