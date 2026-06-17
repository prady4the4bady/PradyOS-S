"""Compression Controller — strategy-based stream summarisation (cognitive layer).

The OS's *compression* primitive: it feeds a stream of items through one of
several space-efficient strategies and returns a compact summary. Three
built-in strategies are provided by composition with shipped structures:

  * ``topk``     — frequency-compressed view via SpaceSaving (top-K heavy hitters)
  * ``bloom``    — membership-compressed view via BloomFilter (set membership)
  * ``minhash``  — similarity-compressed view via MinHash (Jaccard signature)

A consumer chooses the strategy that best preserves the property it cares about:

  * ``topk``     → preserve frequency (answer: "what are the most common items?")
  * ``bloom``    → preserve membership (answer: "have I seen this before?")
  * ``minhash``  → preserve similarity (answer: "is this set similar to others?")

**Honest scope.** Probabilistic compression — bounded error, sub-linear space.
Not semantic compression, not an LLM. The label is "probabilistic cognitive runtime".

Design: thread-safe (one RLock); composes SpaceSaving, BloomFilter, MinHash.
"""

from __future__ import annotations

import threading
from typing import Any

from pradyos.core.bloom_filter import BloomFilter
from pradyos.core.minhash import MinHash
from pradyos.core.space_saving import SpaceSaving

__all__ = ["CompressionController", "CompressionControllerError"]

_BUILTIN_STRATEGIES = frozenset({"topk", "bloom", "minhash"})


class CompressionControllerError(Exception):
    """Raised on invalid CompressionController operations."""


class _StrategyState:
    __slots__ = ("topk", "bloom", "minhash", "bloom_total")

    def __init__(self) -> None:
        self.topk: SpaceSaving | None = None
        self.bloom: BloomFilter | None = None
        self.bloom_total: int = 0
        self.minhash: MinHash | None = None


class CompressionController:
    """Multi-strategy stream compressor — feed items, summarise via chosen strategy.

    Thread-safe: single threading.RLock guards all state.
    """

    def __init__(
        self,
        topk_k: int = 100,
        bloom_capacity: int = 100_000,
        bloom_error_rate: float = 0.01,
        minhash_hashes: int = 128,
        seed: int = 0,
    ) -> None:
        if not isinstance(topk_k, int) or topk_k <= 0:
            raise CompressionControllerError("topk_k must be a positive integer")
        if not isinstance(bloom_capacity, int) or bloom_capacity <= 0:
            raise CompressionControllerError("bloom_capacity must be a positive integer")
        if not (isinstance(bloom_error_rate, (int, float)) and 0.0 < bloom_error_rate < 1.0):
            raise CompressionControllerError("bloom_error_rate must be in (0, 1)")
        if not isinstance(minhash_hashes, int) or minhash_hashes <= 0:
            raise CompressionControllerError("minhash_hashes must be a positive integer")
        self._topk_k = topk_k
        self._bloom_cap = bloom_capacity
        self._bloom_err = bloom_error_rate
        self._mh_hashes = minhash_hashes
        self._seed = int(seed)
        self._state = _StrategyState()
        self._lock = threading.RLock()

    def _ensure_topk(self) -> SpaceSaving:
        if self._state.topk is None:
            self._state.topk = SpaceSaving(k=self._topk_k)
        return self._state.topk

    def _ensure_bloom(self) -> BloomFilter:
        if self._state.bloom is None:
            self._state.bloom = BloomFilter(capacity=self._bloom_cap, error_rate=self._bloom_err)
        return self._state.bloom

    def _ensure_minhash(self) -> MinHash:
        if self._state.minhash is None:
            self._state.minhash = MinHash(num_hashes=self._mh_hashes, seed=self._seed)
        return self._state.minhash

    def strategies(self) -> list[str]:
        """Return the list of available strategy names."""
        return sorted(_BUILTIN_STRATEGIES)

    def feed(self, items: list[str], strategy: str = "topk") -> dict[str, Any]:
        """Feed ``items`` through the named compression strategy.

        Returns a summary snapshot after feeding.
        """
        if not isinstance(items, (list, tuple)):
            raise CompressionControllerError("items must be a list of strings")
        if not items:
            return self.summarize(strategy)
        if strategy not in _BUILTIN_STRATEGIES:
            raise CompressionControllerError(
                f"unknown strategy {strategy!r}; choose from {sorted(_BUILTIN_STRATEGIES)}"
            )
        with self._lock:
            if strategy == "topk":
                ss = self._ensure_topk()
                for item in items:
                    ss.add(str(item))
            elif strategy == "bloom":
                bf = self._ensure_bloom()
                for item in items:
                    bf.add(str(item))
                self._state.bloom_total += len(items)
            elif strategy == "minhash":
                mh = self._ensure_minhash()
                for item in items:
                    mh.add("_default", str(item))
        return self.summarize(strategy)

    def summarize(self, strategy: str) -> dict[str, Any]:
        """Return the compressed summary for the named strategy."""
        if strategy not in _BUILTIN_STRATEGIES:
            raise CompressionControllerError(
                f"unknown strategy {strategy!r}; choose from {sorted(_BUILTIN_STRATEGIES)}"
            )
        with self._lock:
            if strategy == "topk":
                ss = self._state.topk
                if ss is None:
                    return {"strategy": "topk", "items": [], "total": 0, "k": self._topk_k}
                return {
                    "strategy": "topk",
                    "items": ss.top(self._topk_k),
                    "total": ss.total,
                    "k": self._topk_k,
                }
            elif strategy == "bloom":
                bf = self._state.bloom
                if bf is None:
                    return {
                        "strategy": "bloom",
                        "unique_estimate": 0,
                        "total_fed": 0,
                        "fill_ratio": 0.0,
                        "capacity": self._bloom_cap,
                    }
                return {
                    "strategy": "bloom",
                    "unique_estimate": len(bf),
                    "total_fed": self._state.bloom_total,
                    "fill_ratio": round(bf.fill_ratio(), 6),
                    "capacity": self._bloom_cap,
                }
            elif strategy == "minhash":
                mh = self._state.minhash
                if mh is None or mh.signature("_default") is None:
                    return {
                        "strategy": "minhash",
                        "signature": None,
                        "num_hashes": self._mh_hashes,
                    }
                return {
                    "strategy": "minhash",
                    "signature": mh.signature("_default"),
                    "num_hashes": self._mh_hashes,
                }

    def estimate_size(self, items: list[str], strategy: str) -> dict[str, Any]:
        """Estimate the compressed size and ratio for ``items`` under ``strategy``.

        This is a *projected* estimate — it does not modify the stored state.
        """
        if not isinstance(items, list):
            raise CompressionControllerError("items must be a list")
        if strategy not in _BUILTIN_STRATEGIES:
            raise CompressionControllerError(
                f"unknown strategy {strategy!r}; choose from {sorted(_BUILTIN_STRATEGIES)}"
            )
        raw_bytes = sum(len(str(i)) for i in items)
        with self._lock:
            if strategy == "topk":
                projected = SpaceSaving(k=self._topk_k)
                for item in items:
                    projected.add(str(item))
                compressed_bytes = self._topk_k * 64  # rough: k × 64 bytes per entry
                items_count = len(projected)
            elif strategy == "bloom":
                bf = BloomFilter(capacity=max(len(items), self._bloom_cap), error_rate=self._bloom_err)
                for item in items:
                    bf.add(str(item))
                compressed_bytes = len(bf) * 8
                items_count = len(items)
            elif strategy == "minhash":
                compressed_bytes = self._mh_hashes * 8
                items_count = 1
        return {
            "strategy": strategy,
            "raw_items": len(items),
            "raw_bytes": raw_bytes,
            "estimated_compressed_bytes": compressed_bytes,
            "compression_ratio": round(compressed_bytes / raw_bytes, 6) if raw_bytes else 0.0,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            topk_active = self._state.topk is not None
            bloom_active = self._state.bloom is not None
            mh_active = self._state.minhash is not None
            return {
                "strategies": sorted(_BUILTIN_STRATEGIES),
                "active_strategies": {
                    "topk": topk_active,
                    "bloom": bloom_active,
                    "minhash": mh_active,
                },
                "topk_k": self._topk_k,
                "bloom_capacity": self._bloom_cap,
                "minhash_hashes": self._mh_hashes,
                "seed": self._seed,
            }

    def reset(self, strategy: str | None = None) -> None:
        """Reset state for ``strategy`` (or all if ``None``)."""
        with self._lock:
            if strategy is None or strategy == "topk":
                self._state.topk = None
            if strategy is None or strategy == "bloom":
                self._state.bloom = None
            if strategy is None or strategy == "minhash":
                self._state.minhash = None
