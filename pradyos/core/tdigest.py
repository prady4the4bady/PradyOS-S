"""Phase 79 — Sovereign T-Digest (streaming percentile estimation).

Estimates quantiles (median, p95, p99, …) over a stream of values in compact,
mergeable memory — without keeping every sample. Values are summarised as
*centroids* ``(mean, weight)``; a compression step merges adjacent centroids
under a size bound that shrinks toward the tails (``4·N·q·(1-q)/compression``),
so the extremes keep singleton resolution (``percentile(0)`` is the true min,
``percentile(100)`` the true max) while the bulk is compressed.

Quantile lookup interpolates between centroid centres, clamping to the recorded
min/max. :meth:`merge` combines two digests by pooling and re-compressing their
centroids in sorted order, which makes it order-independent (commutative). Pure
stdlib; thread-safe via a single non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import threading


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class TDigest:
    """A merging t-digest for streaming quantiles (stdlib only)."""

    def __init__(self, max_centroids: int = 300, compression: float = 100.0) -> None:
        if max_centroids < 1:
            raise ValueError("max_centroids must be >= 1")
        if compression <= 0:
            raise ValueError("compression must be positive")
        self._max_centroids = int(max_centroids)
        self._compression = float(compression)
        self._centroids: list[list[float]] = []   # [mean, weight], sorted after compress
        self._total = 0.0
        self._min: float | None = None
        self._max: float | None = None
        self._dirty = False
        self._lock = threading.Lock()

    # ── compression (assumes lock held) ──────────────────────────────────────
    def _compress_locked(self) -> None:
        self._dirty = False
        if not self._centroids:
            return
        self._centroids.sort(key=lambda c: c[0])
        total = self._total
        merged: list[list[float]] = []
        cur_mean, cur_w = self._centroids[0]
        cum = 0.0
        for mean, weight in self._centroids[1:]:
            q = (cum + cur_w / 2.0) / total if total > 0 else 0.0
            max_w = total * 4.0 * q * (1.0 - q) / self._compression
            if cur_w + weight <= max_w:
                cur_mean = (cur_mean * cur_w + mean * weight) / (cur_w + weight)
                cur_w += weight
            else:
                merged.append([cur_mean, cur_w])
                cum += cur_w
                cur_mean, cur_w = mean, weight
        merged.append([cur_mean, cur_w])
        self._centroids = merged

    def _ensure_locked(self) -> None:
        if self._dirty:
            self._compress_locked()

    # ── mutation ──────────────────────────────────────────────────────────────
    def add(self, value, weight=1) -> None:
        """Record ``value`` with the given positive ``weight``."""
        if not _is_number(value):
            raise ValueError("value must be a number")
        if not _is_number(weight) or weight <= 0:
            raise ValueError("weight must be a positive number")
        value = float(value)
        weight = float(weight)
        with self._lock:
            self._centroids.append([value, weight])
            self._total += weight
            self._min = value if self._min is None else min(self._min, value)
            self._max = value if self._max is None else max(self._max, value)
            self._dirty = True
            if len(self._centroids) > self._max_centroids:
                self._compress_locked()

    def clear(self) -> None:
        """Reset to an empty digest."""
        with self._lock:
            self._centroids = []
            self._total = 0.0
            self._min = None
            self._max = None
            self._dirty = False

    def merge(self, other: "TDigest") -> "TDigest":
        """Return a NEW digest pooling ``self`` and ``other`` (order-independent)."""
        if not isinstance(other, TDigest):
            raise ValueError("can only merge another TDigest")
        with self._lock:
            self._ensure_locked()
            a = [c[:] for c in self._centroids]
            a_min, a_max, a_total = self._min, self._max, self._total
        with other._lock:
            other._ensure_locked()
            b = [c[:] for c in other._centroids]
            b_min, b_max, b_total = other._min, other._max, other._total
        result = TDigest(self._max_centroids, self._compression)
        result._centroids = [c[:] for c in (a + b)]
        result._total = a_total + b_total
        mins = [m for m in (a_min, b_min) if m is not None]
        maxs = [m for m in (a_max, b_max) if m is not None]
        result._min = min(mins) if mins else None
        result._max = max(maxs) if maxs else None
        with result._lock:
            result._compress_locked()
        return result

    # ── queries ─────────────────────────────────────────────────────────────
    def quantile(self, q) -> float:
        """Estimated value at quantile ``q`` ∈ [0.0, 1.0]."""
        if not _is_number(q) or not 0.0 <= q <= 1.0:
            raise ValueError("q must be a number in [0.0, 1.0]")
        with self._lock:
            if self._total <= 0:
                raise ValueError("cannot compute a quantile of an empty digest")
            self._ensure_locked()
            if q <= 0.0:
                return self._min
            if q >= 1.0:
                return self._max
            target = q * self._total
            cum = 0.0
            prev_mean = self._min
            prev_rank = 0.0
            for mean, weight in self._centroids:
                center = cum + weight / 2.0
                if target <= center:
                    span = center - prev_rank
                    if span <= 0:
                        return mean
                    frac = (target - prev_rank) / span
                    return prev_mean + frac * (mean - prev_mean)
                prev_mean = mean
                prev_rank = center
                cum += weight
            span = self._total - prev_rank
            if span <= 0:
                return prev_mean
            frac = (target - prev_rank) / span
            return prev_mean + frac * (self._max - prev_mean)

    def percentile(self, p) -> float:
        """Estimated value at percentile ``p`` ∈ [0, 100]."""
        if not _is_number(p) or not 0.0 <= p <= 100.0:
            raise ValueError("p must be a number in [0, 100]")
        return self.quantile(p / 100.0)

    @property
    def min(self) -> float:
        with self._lock:
            if self._min is None:
                raise ValueError("empty digest has no min")
            return self._min

    @property
    def max(self) -> float:
        with self._lock:
            if self._max is None:
                raise ValueError("empty digest has no max")
            return self._max

    @property
    def count(self) -> float:
        with self._lock:
            return self._total

    def stats(self) -> dict:
        """JSON-serialisable snapshot of the digest."""
        with self._lock:
            self._ensure_locked()
            return {
                "count": self._total,
                "centroids": len(self._centroids),
                "min": self._min,
                "max": self._max,
                "max_centroids": self._max_centroids,
                "compression": self._compression,
            }
