"""Novelty Detector — real-time novelty and surprise scoring (cognitive layer).

The OS's *novelty* primitive: for every item (token, event, observation) the
detector answers "have I seen this before?" in sub-linear space and scores how
*surprising* a known item is relative to the full observed distribution.

It **composes** two shipped probabilistic structures (never reimplements them):

  * **Bloom Filter** — zero-false-negative membership test. ``is_novel(item)``
    returns True iff the filter *definitely has not* seen the item (Bloom
    guarantees no false negatives, so not-in-filter ⇒ genuinely new). False
    positives (<1% by default) cause a small number of repeat items to be
    misclassified as novel — an acceptable trade-off for bounded memory.

  * **HyperLogLog** — fixed-memory distinct-count estimator. It tracks *how many
    unique items* have been observed, which feeds the ``surprise_score``::

      surprise_score(item) = HLL_cardinality_estimate / item_frequency

    An item observed only once gets surprise ≈ total_unique; an item observed
    thousands of times gets surprise → 0.

**Honest scope.** This is statistical novelty detection with bounded false-positive
rate — *not* semantic understanding, not an LLM judge. The label is "probabilistic
cognitive runtime".

Design: deterministic given seed; thread-safe (one Lock); imports and composes
BloomFilter + HyperLogLog — never reimplements either.
"""

from __future__ import annotations

import threading
from typing import Any

from pradyos.core.bloom_filter import BloomFilter
from pradyos.core.hyperloglog import HyperLogLog

__all__ = ["NoveltyDetector", "NoveltyDetectorError"]


class NoveltyDetectorError(Exception):
    """Raised on invalid NoveltyDetector operations."""


class NoveltyDetector:
    """Real-time novelty detection via Bloom membership + HLL cardinality.

    Space: O(bloom_capacity + HLL_registers + dict for per-item counts).
    Thread-safe: single threading.Lock guards all state.
    """

    def __init__(
        self,
        bloom_capacity: int = 100_000,
        bloom_error_rate: float = 0.01,
        hll_precision: int = 14,
        seed: int = 0,
    ) -> None:
        if not isinstance(bloom_capacity, int) or bloom_capacity <= 0:
            raise NoveltyDetectorError("bloom_capacity must be a positive integer")
        if not (isinstance(bloom_error_rate, (int, float)) and 0.0 < bloom_error_rate < 1.0):
            raise NoveltyDetectorError("bloom_error_rate must be in (0, 1)")
        if not isinstance(hll_precision, int) or hll_precision < 4 or hll_precision > 16:
            raise NoveltyDetectorError("hll_precision must be between 4 and 16")
        self._seed = int(seed)
        self._bloom = BloomFilter(capacity=bloom_capacity, error_rate=bloom_error_rate)
        self._hll = HyperLogLog(precision=hll_precision)
        self._seen_count: dict[str, int] = {}
        self._total_obs = 0
        self._novel_obs = 0
        self._lock = threading.Lock()

    def observe(self, item: str) -> None:
        """Record an observation of ``item``.

        Updates Bloom filter (membership), HLL (cardinality), and per-item
        frequency counter for surprise scoring. Thread-safe.
        """
        if not isinstance(item, str):
            raise NoveltyDetectorError("item must be a string")
        was_new = self._bloom.add(item)
        self._hll.add(item)
        with self._lock:
            self._seen_count[item] = self._seen_count.get(item, 0) + 1
            self._total_obs += 1
            if was_new:
                self._novel_obs += 1

    def is_novel(self, item: str) -> bool:
        """Return True if ``item`` has (probably) never been seen before.

        Uses Bloom filter membership: Bloom guarantees no false negatives, so
        ``not contains()`` is a definitive "this item is new". A false positive
        in the filter (<1% by default) would make a repeat item appear novel.
        """
        if not isinstance(item, str):
            raise NoveltyDetectorError("item must be a string")
        return not self._bloom.contains(item)

    def novelty_rate(self) -> float:
        """Proportion of all observations that were novel (first-time)."""
        with self._lock:
            if self._total_obs == 0:
                return 0.0
            return self._novel_obs / self._total_obs

    def surprise_score(self, item: str) -> float:
        """How surprising is ``item``? Inversely proportional to its frequency.

        ``surprise = HLL_cardinality / item_frequency``

        An item seen once gets surprise ≈ total distinct count; an item seen
        thousands of times gets surprise → 0.
        """
        if not isinstance(item, str):
            raise NoveltyDetectorError("item must be a string")
        with self._lock:
            freq = self._seen_count.get(item, 0)
        cardinality = self._hll.estimate()
        if freq == 0:
            return float(cardinality)
        return float(cardinality) / freq

    def reset(self) -> None:
        """Clear all state — Bloom filter, HLL, per-item counters."""
        self._bloom.clear()
        self._hll.clear()
        with self._lock:
            self._seen_count.clear()
            self._total_obs = 0
            self._novel_obs = 0

    def stats(self) -> dict[str, Any]:
        """JSON-serialisable snapshot of detector state."""
        with self._lock:
            total = self._total_obs
            novel = self._novel_obs
        return {
            "total_observations": total,
            "novel_observations": novel,
            "novelty_rate": round(novel / total, 6) if total else 0.0,
            "unique_estimate": self._hll.estimate(),
            "bloom_count": len(self._bloom),
            "bloom_fill_ratio": round(self._bloom.fill_ratio(), 6),
            "hll_fill_ratio": round(self._hll.fill_ratio(), 6),
            "seed": self._seed,
        }
