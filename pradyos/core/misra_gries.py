"""Phase 99 — Sovereign Misra-Gries (Misra–Gries, 1982).

The *original* **deterministic counter-based heavy-hitter** algorithm. At most
``k`` ``(element → count)`` counters are kept. On each arrival: increment the
element's counter if monitored; else, if a slot is free, start a new counter at
the item's count; otherwise **decrement every counter** by the item's count and
drop any that reach zero. The arriving (unmonitored, no-slot) item is absorbed by
that decrement rather than stored.

Comparison with the other heavy-hitter algorithms in this codebase:
  * **Misra-Gries (this, P99)** — *decrement all* counters on a miss.
  * **Space-Saving (P87)** — *evict the minimum* counter and reassign it.
  * **Lossy Counting (P95)** — *bucket sweeps* with a per-entry error bound Δ.

Guarantees (Misra–Gries):
  * Any element with true frequency **> n / (k+1)** appears in the summary.
  * Every reported estimate under-counts the true frequency by at most ``n/(k+1)``.
  * **Space:** exactly ``k`` counters.

So ``heavy_hitters(support)`` (returning counts ≥ ``(support − 1/(k+1))·n``) has no
false negatives among elements whose true frequency ≥ ``support·n``. The algorithm
is fully deterministic (no RNG — ``seed`` is accepted for parity but unused), and
**append-only**: a non-positive ``count`` raises :class:`MisraGriesError`. Pure
stdlib. Thread-safe via a single ``threading.Lock``; internal ``_*_locked``
helpers never re-acquire it.
"""

from __future__ import annotations

from typing import Any
import threading


class MisraGriesError(Exception):
    """Raised for an invalid Misra-Gries configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class MisraGries:
    """Deterministic ε-approximate heavy-hitter counter (decrement-all on a miss)."""

    def __init__(self, k: int, seed: Any = None) -> None:
        if not _is_pos_int(k):
            raise MisraGriesError("k must be at least 1")
        self._k = k
        self._seed = seed                         # accepted for parity; deterministic → unused
        self._counters: dict[Any, int] = {}
        self._n = 0
        self._lock = threading.Lock()

    # ── internal (run under the lock; never re-acquire) ──────────────────────────
    def _update_locked(self, element: Any, count: int) -> None:
        self._n += count
        if element in self._counters:
            self._counters[element] += count
        elif len(self._counters) < self._k:
            self._counters[element] = count
        else:
            # decrement every counter by ``count``; drop those that hit zero
            for e in list(self._counters):
                self._counters[e] -= count
                if self._counters[e] <= 0:
                    del self._counters[e]

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, element: Any, count: int = 1) -> None:
        """Observe ``count`` occurrences of ``element`` (``count`` ≥ 1; no deletion)."""
        if not _is_int(count):
            raise MisraGriesError(count)
        if count <= 0:
            raise MisraGriesError("Misra-Gries does not support deletion")
        with self._lock:
            self._update_locked(element, count)

    def reset(self, k: int | None = None) -> None:
        """Clear all counters and ``n``; optionally reconfigure ``k``."""
        with self._lock:
            if k is not None:
                if not _is_pos_int(k):
                    raise MisraGriesError("k must be at least 1")
                self._k = k
            self._counters = {}
            self._n = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def estimate(self, element: Any) -> int:
        """Stored (under-)count of ``element`` (0 if not currently monitored)."""
        with self._lock:
            return self._counters.get(element, 0)

    def heavy_hitters(self, support: float) -> list[dict]:
        """Elements with stored count ≥ ``(support − 1/(k+1))·n``, highest first.

        Guarantees every element whose *true* frequency ≥ ``support·n`` is returned."""
        if not _is_number(support) or not (0.0 < support <= 1.0):
            raise MisraGriesError(support)
        with self._lock:
            cutoff = (support - 1.0 / (self._k + 1)) * self._n
            hits = [(e, c) for e, c in self._counters.items() if c >= cutoff]
            hits.sort(key=lambda pair: -pair[1])
            return [{"element": e, "count": c} for e, c in hits]

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def k(self) -> int:
        return self._k

    @property
    def n(self) -> int:
        with self._lock:
            return self._n

    @property
    def counters(self) -> int:
        with self._lock:
            return len(self._counters)

    def stats(self) -> dict:
        """Summary: ``k``, total items ``n``, monitored ``counters``, error ``threshold = n/(k+1)``."""
        with self._lock:
            return {
                "k": self._k,
                "n": self._n,
                "counters": len(self._counters),
                "threshold": self._n / (self._k + 1),
            }
