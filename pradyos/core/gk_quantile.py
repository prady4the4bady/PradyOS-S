"""Phase 91 — Sovereign GK Quantile Sketch (Greenwald–Khanna, 2001).

Streaming **ε-approximate quantiles** over an unbounded stream in
``O((1/ε)·log(εn))`` space, with a hard guarantee: the value returned for a
quantile ``φ`` has true rank within ``±⌈εn⌉`` of the requested rank.

The summary is a value-sorted list of tuples ``(v, g, Δ)``:

  * ``v``  — an observed value retained in the summary;
  * ``g``  — ``r_min(v_i) − r_min(v_{i-1})`` (so ``r_min(v_i) = Σ g_j`` for ``j ≤ i``);
  * ``Δ``  — ``r_max(v_i) − r_min(v_i)``, the rank uncertainty for ``v_i``.

The invariant ``g_i + Δ_i ≤ ⌊2εn⌋`` is preserved for every tuple, which is what
bounds the quantile error. **Insert** places ``v`` in sorted order with ``g = 1``
and ``Δ = ⌊2εn⌋`` (the new min/max get ``Δ = 0`` — exact extremes). **Compress**
(run every ``⌊1/2ε⌋`` insertions) merges an adjacent pair when
``g_i + g_{i+1} + Δ_{i+1} ≤ ⌊2εn⌋`` — which keeps the invariant since the merged
gap becomes ``g_i + g_{i+1}``. **Query** for rank ``r = ⌈φn⌉`` walks the summary
and returns the first ``v`` whose running ``r_min`` exceeds ``r − εn``; the
invariant then guarantees ``r_max ≤ r + εn``.

GK is deterministic by construction (no RNG); ``seed`` is accepted for API
parity. Pure stdlib. Thread-safe via a single ``threading.Lock``; internal
``_*_locked`` helpers run under the lock and never re-acquire it.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class GKError(Exception):
    """Raised for an invalid GK-summary configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid gk quantile configuration: {detail!r}")


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class GKSummary:
    """Greenwald–Khanna ε-approximate quantile summary over a stream of numbers."""

    def __init__(self, epsilon: float = 0.01, seed: int = 0) -> None:
        if not _is_number(epsilon) or not (0.0 < epsilon < 1.0):
            raise GKError(epsilon)
        if not _is_int(seed):
            raise GKError(seed)
        self._eps = float(epsilon)
        self._seed = seed
        self._s: list[list] = []  # sorted tuples [v, g, delta]
        self._n = 0
        self._since_compress = 0
        self._interval = max(1, int(1.0 / (2.0 * self._eps)))
        self._lock = threading.Lock()

    # ── internal (run under the lock; never re-acquire) ──────────────────────────
    def _find_index(self, v: float) -> int:
        lo, hi = 0, len(self._s)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._s[mid][0] < v:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _insert_locked(self, value: float) -> None:
        v = float(value)
        i = self._find_index(v)
        if i == 0 or i == len(self._s):
            delta = 0  # new minimum or maximum → exact rank
        else:
            delta = int(2.0 * self._eps * self._n)  # ⌊2εn⌋ with the pre-insert count
        self._s.insert(i, [v, 1, delta])
        self._n += 1
        self._since_compress += 1
        if self._since_compress >= self._interval:
            self._compress_locked()
            self._since_compress = 0

    def _compress_locked(self) -> None:
        threshold = int(2.0 * self._eps * self._n)
        i = len(self._s) - 2
        while i >= 1:  # never merge away the min (0) or the max (last)
            if self._s[i][1] + self._s[i + 1][1] + self._s[i + 1][2] <= threshold:
                self._s[i + 1][1] += self._s[i][1]
                del self._s[i]
            i -= 1

    def _query_locked(self, phi: float) -> float | None:
        if self._n == 0:
            return None
        if phi <= 0.0:
            return self._s[0][0]
        if phi >= 1.0:
            return self._s[-1][0]
        rank = math.ceil(phi * self._n)
        margin = self._eps * self._n
        rmin = 0
        for v, g, _delta in self._s:
            rmin += g
            if rmin > rank - margin:
                return v
        return self._s[-1][0]

    # ── mutation ─────────────────────────────────────────────────────────────────
    def insert(self, value: Any) -> None:
        """Observe one numeric ``value``."""
        if not _is_number(value):
            raise GKError(value)
        with self._lock:
            self._insert_locked(value)

    def insert_many(self, values: Any) -> int:
        """Observe every value in ``values``; return how many were added."""
        vals = list(values)
        for x in vals:
            if not _is_number(x):
                raise GKError(x)
        with self._lock:
            for x in vals:
                self._insert_locked(x)
            return len(vals)

    def reset(self, epsilon: float | None = None, seed: int | None = None) -> None:
        """Clear the summary; optionally reconfigure ``epsilon`` / ``seed``."""
        with self._lock:
            if epsilon is not None:
                if not _is_number(epsilon) or not (0.0 < epsilon < 1.0):
                    raise GKError(epsilon)
                self._eps = float(epsilon)
                self._interval = max(1, int(1.0 / (2.0 * self._eps)))
            if seed is not None:
                if not _is_int(seed):
                    raise GKError(seed)
                self._seed = seed
            self._s = []
            self._n = 0
            self._since_compress = 0

    def compress(self) -> None:
        """Force a compression pass (normally amortized across inserts)."""
        with self._lock:
            self._compress_locked()
            self._since_compress = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def query(self, phi: float) -> float | None:
        """The ``phi``-quantile (``phi`` in [0, 1]); ``None`` if the summary is empty."""
        if not _is_number(phi) or not (0.0 <= phi <= 1.0):
            raise GKError(phi)
        with self._lock:
            return self._query_locked(phi)

    def count(self) -> int:
        """Total number of observed values, ``n``."""
        with self._lock:
            return self._n

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def epsilon(self) -> float:
        return self._eps

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def summary_size(self) -> int:
        with self._lock:
            return len(self._s)

    def _capacity_locked(self) -> float:
        two_en = 2.0 * self._eps * self._n
        if two_en <= 1.0:
            return float(len(self._s))
        return (1.0 / (2.0 * self._eps)) * math.log2(two_en)

    def stats(self) -> dict:
        """Summary: ``epsilon``, stream size ``n``, ``summary_size``, theoretical ``capacity``."""
        with self._lock:
            return {
                "epsilon": self._eps,
                "n": self._n,
                "summary_size": len(self._s),
                "capacity": round(self._capacity_locked(), 6),
            }
