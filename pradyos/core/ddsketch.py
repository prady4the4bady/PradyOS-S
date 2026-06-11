"""Phase 96 — Sovereign DDSketch (Masson & Lee, 2019).

A streaming-quantile sketch with a **relative-error** guarantee — a different
guarantee from the *rank*-error sketches of Phase 91 (Greenwald–Khanna) and
Phase 92 (KLL). Each positive value ``v`` is mapped to a logarithmic bucket
``i = ⌈log_γ(v)⌉`` with ``γ = (1 + α)/(1 − α)`` (equivalently ``1 + 2α/(1−α)``),
and a dict ``{bucket → count}`` tallies how many values fell in each. A quantile
query walks the buckets in value order until the ``q``-th item is reached and
returns that bucket's representative value.

**Guarantee:** for any quantile ``q`` whose true value is ``v``, the returned
estimate ``v̂`` satisfies ``|v̂ − v| / v ≤ α`` — relative error is bounded by ``α``
regardless of the value distribution (ideal for long-tailed latencies where p99
accuracy matters proportionally).

Representative value: this uses the standard ``r_i = 2·γ**i / (γ + 1)`` (the
geometric midpoint of bucket ``i``'s range ``(γ**(i−1), γ**i]``). That choice
makes the worst-case relative error exactly ``(γ−1)/(γ+1) = α`` — so the bound
above holds. (A naive ``(1+α)**i`` representative does *not* bound the error — it
mixes two bases and drifts with ``i`` — so the gate-satisfying midpoint is used.)

**Merge** adds the per-bucket counts of two sketches with the same ``α`` — exact,
not approximate, which is the key differentiator over t-Digest and makes DDSketch
suitable for distributed quantile aggregation. The algorithm is deterministic;
``seed`` is accepted for API parity but unused. Negative/zero values are rejected.
Pure stdlib. Thread-safe via a single ``threading.Lock``; internal ``_*_locked``
helpers never re-acquire it.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class DDSketchError(Exception):
    """Raised for an invalid DDSketch configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid ddsketch operation: {detail!r}")


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class DDSketch:
    """Relative-error quantile sketch with exact mergeability (Masson–Lee)."""

    def __init__(self, alpha: float = 0.01, seed: Any = None) -> None:
        if not _is_number(alpha) or not (0.0 < alpha < 1.0):
            raise DDSketchError(alpha)
        self._alpha = float(alpha)
        self._seed = seed  # accepted for parity; deterministic → unused
        self._gamma = (1.0 + self._alpha) / (1.0 - self._alpha)
        self._log_gamma = math.log(self._gamma)
        self._buckets: dict[int, int] = {}  # bucket index -> count
        self._n = 0
        self._min: float | None = None
        self._max: float | None = None
        self._lock = threading.Lock()

    # ── bucketing (pure) ──────────────────────────────────────────────────────────
    def _index(self, value: float) -> int:
        return math.ceil(math.log(value) / self._log_gamma)

    def _value_of(self, index: int) -> float:
        return 2.0 * self._gamma**index / (self._gamma + 1.0)

    # ── mutation ─────────────────────────────────────────────────────────────────
    def _update_locked(self, value: float, count: int) -> None:
        idx = self._index(value)
        self._buckets[idx] = self._buckets.get(idx, 0) + count
        self._n += count
        self._min = value if self._min is None else min(self._min, value)
        self._max = value if self._max is None else max(self._max, value)

    def update(self, value: Any, count: int = 1) -> None:
        """Record ``count`` occurrences of ``value`` (which must be strictly positive)."""
        if not _is_number(value) or value <= 0:
            raise DDSketchError("DDSketch requires positive values")
        if not _is_int(count) or count < 1:
            raise DDSketchError(count)
        with self._lock:
            self._update_locked(float(value), count)

    def merge(self, other: DDSketch) -> None:
        """Fold ``other`` (same ``α``) into this sketch — an exact union of bucket counts."""
        if not isinstance(other, DDSketch):
            raise DDSketchError(other)
        if other._alpha != self._alpha:
            raise DDSketchError((self._alpha, other._alpha))
        with other._lock:
            o_buckets = dict(other._buckets)
            o_n, o_min, o_max = other._n, other._min, other._max
        with self._lock:
            for idx, cnt in o_buckets.items():
                self._buckets[idx] = self._buckets.get(idx, 0) + cnt
            self._n += o_n
            if o_min is not None:
                self._min = o_min if self._min is None else min(self._min, o_min)
            if o_max is not None:
                self._max = o_max if self._max is None else max(self._max, o_max)

    def reset(self, alpha: float | None = None, seed: Any = None) -> None:
        """Clear all state; optionally reconfigure ``alpha`` / ``seed``."""
        with self._lock:
            if alpha is not None:
                if not _is_number(alpha) or not (0.0 < alpha < 1.0):
                    raise DDSketchError(alpha)
                self._alpha = float(alpha)
                self._gamma = (1.0 + self._alpha) / (1.0 - self._alpha)
                self._log_gamma = math.log(self._gamma)
            if seed is not None:
                self._seed = seed
            self._buckets = {}
            self._n = 0
            self._min = None
            self._max = None

    # ── queries ──────────────────────────────────────────────────────────────────
    def quantile(self, q: float) -> float | None:
        """The ``q``-quantile (``q`` in [0, 1]); ``None`` if the sketch is empty."""
        if not _is_number(q) or not (0.0 <= q <= 1.0):
            raise DDSketchError(q)
        with self._lock:
            if self._n == 0:
                return None
            target = math.ceil(q * self._n)
            if target < 1:
                target = 1
            cum = 0
            for idx in sorted(self._buckets):
                cum += self._buckets[idx]
                if cum >= target:
                    return self._value_of(idx)
            return self._value_of(max(self._buckets))

    def count(self) -> int:
        """Total number of recorded values, ``n``."""
        with self._lock:
            return self._n

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def alpha(self) -> float:
        return self._alpha

    @property
    def gamma(self) -> float:
        return self._gamma

    @property
    def seed(self) -> Any:
        return self._seed

    @property
    def num_buckets(self) -> int:
        with self._lock:
            return len(self._buckets)

    def stats(self) -> dict:
        """Summary: ``alpha``, ``gamma``, stream size ``n``, ``num_buckets``, ``min``, ``max``."""
        with self._lock:
            return {
                "alpha": self._alpha,
                "gamma": self._gamma,
                "n": self._n,
                "num_buckets": len(self._buckets),
                "min": self._min,
                "max": self._max,
            }
