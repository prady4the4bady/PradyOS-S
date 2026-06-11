"""Phase 95 — Sovereign Lossy Counting (Manku–Motwani, 2002).

**Deterministic** approximate frequency / heavy-hitter detection with a clean
ε-error guarantee and *no hashing* (unlike the probabilistic Count-Min (P76) and
Count Sketch (P94)). The stream is divided into buckets of width ``w = ⌈1/ε⌉``,
numbered ``1, 2, …``. A dictionary holds ``{element: (freq, Δ)}`` where ``freq`` is
the observed count and ``Δ`` is the maximum it can *under*-count by. On each
arrival the element's ``freq`` is incremented (or it is inserted as
``(count, b_current − 1)``); at every bucket boundary the table is swept and every
entry with ``freq + Δ ≤ b_current`` is deleted.

Guarantees (Manku–Motwani):
  * **No false negatives** — every element whose true frequency ≥ ``support·n`` is
    returned by ``heavy_hitters(support)``.
  * **No false positives above threshold** — every returned element has true
    frequency ≥ ``(support − ε)·n``.
  * **Space** — at most ``(1/ε)·log(εn)`` entries are kept at any time.

The algorithm is **deterministic**: no randomness is involved, so ``seed`` is
accepted only for API parity and is *unused* — the same stream in the same order
always yields the same state. **Deletion is not supported** (Lossy Counting is
append-only by design): a negative ``count`` raises :class:`LossyCountError`.
Pure stdlib. Thread-safe via a single ``threading.Lock``; internal ``_*_locked``
helpers never re-acquire it.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class LossyCountError(Exception):
    """Raised for an invalid Lossy-Counting configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid lossy counting operation: {detail!r}")


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class LossyCount:
    """Deterministic ε-approximate heavy-hitter counter (Manku–Motwani)."""

    def __init__(self, epsilon: float = 0.001, seed: Any = None) -> None:
        if not _is_number(epsilon) or not (0.0 < epsilon < 1.0):
            raise LossyCountError(epsilon)
        self._epsilon = float(epsilon)
        self._seed = seed  # accepted for parity; deterministic → unused
        self._w = math.ceil(1.0 / self._epsilon)  # bucket width
        self._d: dict[Any, list[int]] = {}  # element -> [freq, delta]
        self._n = 0  # total items seen
        self._lock = threading.Lock()

    # ── internal (run under the lock; never re-acquire) ──────────────────────────
    def _b_current(self) -> int:
        return (self._n + self._w - 1) // self._w  # ⌈n / w⌉

    def _update_locked(self, element: Any, count: int) -> None:
        n_before = self._n
        self._n += count
        b_current = self._b_current()
        entry = self._d.get(element)
        if entry is not None:
            entry[0] += count
        else:
            self._d[element] = [count, b_current - 1]
        # Sweep at every bucket boundary crossed by this update.
        boundary = (n_before // self._w + 1) * self._w
        while boundary <= self._n:
            b = boundary // self._w
            self._d = {e: v for e, v in self._d.items() if v[0] + v[1] > b}
            boundary += self._w

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, element: Any, count: int = 1) -> None:
        """Observe ``count`` occurrences of ``element`` (``count`` must be ≥ 0; no deletion)."""
        if not _is_int(count):
            raise LossyCountError(count)
        if count < 0:
            raise LossyCountError("Lossy Counting does not support deletion")
        if count == 0:
            return
        with self._lock:
            self._update_locked(element, count)

    def reset(self, epsilon: float | None = None, seed: Any = None) -> None:
        """Clear all state (n=0, empty table); optionally reconfigure ``epsilon`` / ``seed``."""
        with self._lock:
            if epsilon is not None:
                if not _is_number(epsilon) or not (0.0 < epsilon < 1.0):
                    raise LossyCountError(epsilon)
                self._epsilon = float(epsilon)
                self._w = math.ceil(1.0 / self._epsilon)
            if seed is not None:
                self._seed = seed
            self._d = {}
            self._n = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def estimate(self, element: Any) -> int:
        """Tracked frequency of ``element`` (0 if not currently retained)."""
        with self._lock:
            entry = self._d.get(element)
            return entry[0] if entry is not None else 0

    def heavy_hitters(self, support: float) -> list[dict]:
        """Elements with frequency ≥ ``(support − ε)·n``, highest first.

        Guarantees every element whose *true* frequency ≥ ``support·n`` is included."""
        if not _is_number(support) or not (0.0 < support <= 1.0):
            raise LossyCountError(support)
        with self._lock:
            cutoff = (support - self._epsilon) * self._n
            hits = [(e, v[0]) for e, v in self._d.items() if v[0] >= cutoff]
            hits.sort(key=lambda pair: -pair[1])
            return [{"element": e, "frequency": f} for e, f in hits]

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def epsilon(self) -> float:
        return self._epsilon

    @property
    def bucket_width(self) -> int:
        return self._w

    @property
    def n(self) -> int:
        with self._lock:
            return self._n

    @property
    def entries(self) -> int:
        with self._lock:
            return len(self._d)

    def stats(self) -> dict:
        """Summary: ``epsilon``, stream size ``n``, ``bucket_width``, ``entries``, ``current_bucket``."""
        with self._lock:
            return {
                "epsilon": self._epsilon,
                "n": self._n,
                "bucket_width": self._w,
                "entries": len(self._d),
                "current_bucket": self._b_current(),
            }
