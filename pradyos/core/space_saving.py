"""Phase 87 — Sovereign Top-K (Space-Saving).

Tracks the approximate ``k`` most frequent items in a stream of unknown length
using **bounded O(k) memory** (Metwally–Agrawal "Space-Saving" / Stream-Summary).
At most ``k`` (item → count, error) entries are monitored. On each observation:

  * a monitored item simply increments its count;
  * an unmonitored item is admitted directly while fewer than ``k`` are tracked;
  * once full, the **minimum-count** entry is evicted and *reassigned* to the new
    item, whose count becomes ``min_count + 1`` and whose ``error`` (maximum
    over-estimate) becomes the evicted ``min_count``.

Because every step increments the total by one and the monitored counts by one,
the invariant ``sum(counts) == total`` always holds — so when the table is full
the minimum count is ≤ ``total / k``. Two consequences follow:

  * **Heavy-hitter guarantee:** any item whose true frequency exceeds ``n / k``
    is always monitored (no false negatives among the heavy hitters).
  * **Error bound:** a reported count over-estimates the true count by at most the
    item's ``error``, itself ≤ the current minimum count ≤ ``n / k``.

Pure stdlib. Thread-safe via a single ``threading.Lock``; the public surface
acquires it, and internal ``_locked`` helpers never re-acquire it (non-reentrant).
"""

from __future__ import annotations

import threading
from typing import Any


class SpaceSavingError(Exception):
    """Raised for an invalid Space-Saving configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid space-saving configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


class SpaceSaving:
    """Approximate Top-K heavy hitters over a stream in O(k) space (Metwally–Agrawal)."""

    def __init__(self, k: int = 10) -> None:
        if not _is_pos_int(k):
            raise SpaceSavingError(k)
        self._k = k
        self._counts: dict[Any, list[int]] = {}   # item -> [count, error]
        self._total = 0
        self._lock = threading.Lock()

    # ── internal helpers (run under the lock; never re-acquire) ──────────────────
    def _min_entry(self) -> tuple[Any, int | None]:
        """Return ``(item, count)`` of the minimum-count monitored entry (insertion
        order breaks ties, so the *oldest* minimum is evicted first)."""
        min_item: Any = None
        min_count: int | None = None
        for item, (count, _err) in self._counts.items():
            if min_count is None or count < min_count:
                min_item, min_count = item, count
        return min_item, min_count

    def _add_locked(self, item: Any) -> None:
        entry = self._counts.get(item)          # raises TypeError on unhashable BEFORE mutating
        self._total += 1
        if entry is not None:
            entry[0] += 1
            return
        if len(self._counts) < self._k:
            self._counts[item] = [1, 0]
            return
        # full → evict the minimum-count entry, reassign its slot to the new item
        min_item, min_count = self._min_entry()
        del self._counts[min_item]
        self._counts[item] = [min_count + 1, min_count]

    # ── mutation ─────────────────────────────────────────────────────────────────
    def add(self, item: Any) -> None:
        """Observe one occurrence of ``item`` (must be hashable)."""
        with self._lock:
            self._add_locked(item)

    def add_many(self, items: Any) -> int:
        """Observe every item in ``items`` in order; return how many were added."""
        with self._lock:
            n = 0
            for item in items:
                self._add_locked(item)
                n += 1
            return n

    def reset(self, k: int | None = None) -> None:
        """Clear the counter table; optionally resize ``k`` (must be a positive int)."""
        with self._lock:
            if k is not None:
                if not _is_pos_int(k):
                    raise SpaceSavingError(k)
                self._k = k
            self._counts = {}
            self._total = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def count(self, item: Any) -> int:
        """Estimated frequency of ``item`` (0 if it is not currently monitored)."""
        with self._lock:
            entry = self._counts.get(item)
            return entry[0] if entry is not None else 0

    def error(self, item: Any) -> int:
        """Maximum over-estimate of ``item``'s count (0 if exact or unmonitored)."""
        with self._lock:
            entry = self._counts.get(item)
            return entry[1] if entry is not None else 0

    def top(self, n: int | None = None) -> list[dict]:
        """The top items by estimated count, descending. ``n=None`` returns all
        monitored entries. Ties keep first-monitored order (sort is stable)."""
        with self._lock:
            ordered = sorted(self._counts.items(), key=lambda kv: -kv[1][0])
            if n is not None:
                ordered = ordered[: max(n, 0)]
            return [{"item": item, "count": c, "error": e} for item, (c, e) in ordered]

    def __len__(self) -> int:
        with self._lock:
            return len(self._counts)

    def __contains__(self, item: Any) -> bool:
        with self._lock:
            return item in self._counts

    @property
    def k(self) -> int:
        return self._k

    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    def stats(self) -> dict:
        """Summary: configured ``k``, items ``monitored``, stream ``total``, and the
        current ``min_count`` (the eviction threshold / maximum possible error)."""
        with self._lock:
            _item, min_count = self._min_entry()
            return {
                "k": self._k,
                "monitored": len(self._counts),
                "total": self._total,
                "min_count": min_count if min_count is not None else 0,
            }
