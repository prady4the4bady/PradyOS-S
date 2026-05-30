"""Phase 93 — Sovereign Theta Sketch (K-Minimum-Values).

Estimates the number of **distinct** elements (cardinality) in a stream using the
KMV / Theta-sketch scheme — and, unlike Phase 74's HyperLogLog, supports a
**lossless set union** of two sketches (the basis for distributed / pipelined
aggregation). Each element is hashed uniformly into ``[0, 1)``; the sketch retains
the ``k`` smallest *distinct* hash values seen. When ``k`` distinct hashes have
been retained, ``θ`` is the largest of them (the ``k``-th smallest overall), which
estimates the fraction of the hash space the retained set covers, so

    estimate = (k − 1) / θ      (once ``k`` distinct hashes are retained)
    estimate = retained_count   (exact, while fewer than ``k`` are retained)

Duplicates hash to a value already retained and are ignored, so repeats never
inflate the count. The relative error is ``≈ 1/√(k−1)`` (≈ 1.6 % at ``k = 4096``).

**Union** keeps the ``k`` smallest hashes of the two retained sets — itself a valid
KMV sketch of ``A ∪ B`` — and **intersection** follows by inclusion–exclusion,
``|A ∩ B| ≈ est(A) + est(B) − est(A ∪ B)``. The hash is seeded (BLAKE2b) so a
fixed insert sequence is deterministic. Pure stdlib. Thread-safe via a single
``threading.Lock``; internal ``_*_locked`` helpers never re-acquire it.
"""

from __future__ import annotations

import hashlib
import heapq
import threading
from typing import Any

_TWO64 = float(1 << 64)


class ThetaError(Exception):
    """Raised for an invalid Theta-sketch configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid theta sketch configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class ThetaSketch:
    """KMV distinct-count sketch with native set-union mergeability."""

    def __init__(self, k: int = 4096, seed: int = 0) -> None:
        if not _is_pos_int(k) or k < 2:
            raise ThetaError(k)
        if not _is_int(seed):
            raise ThetaError(seed)
        self._k = k
        self._seed = seed
        self._set: set[float] = set()        # retained distinct hashes (the k smallest)
        self._heap: list[float] = []          # max-heap of retained hashes (stores -h)
        self._n = 0                           # total insert calls (incl. duplicates)
        self._lock = threading.Lock()

    # ── hashing ───────────────────────────────────────────────────────────────────
    def _hash(self, element: Any) -> float:
        data = repr((self._seed, element)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big") / _TWO64

    # ── internal helpers (run under the lock; never re-acquire) ──────────────────
    def _insert_locked(self, element: Any) -> None:
        self._n += 1
        h = self._hash(element)
        if h in self._set:
            return                            # duplicate hash → ignore
        if len(self._set) < self._k:
            self._set.add(h)
            heapq.heappush(self._heap, -h)
            return
        if h < -self._heap[0]:                # smaller than the current max → it belongs
            evicted = -heapq.heappushpop(self._heap, -h)
            self._set.discard(evicted)
            self._set.add(h)
        # else: h is not among the k smallest → discard

    def _theta_of(self, hashes: set[float]) -> float:
        return max(heapq.nsmallest(self._k, hashes)) if len(hashes) >= self._k else 1.0

    def _estimate_of(self, hashes: set[float]):
        m = len(hashes)
        if m < self._k:
            return m                           # exact distinct count below threshold (int)
        return (self._k - 1) / self._theta_of(hashes)

    # ── mutation ─────────────────────────────────────────────────────────────────
    def update(self, element: Any) -> None:
        """Observe one ``element`` (duplicates do not change the estimate)."""
        with self._lock:
            self._insert_locked(element)

    def update_many(self, elements: Any) -> int:
        """Observe every element; return how many ``update`` calls were made."""
        with self._lock:
            n = 0
            for element in elements:
                self._insert_locked(element)
                n += 1
            return n

    def merge(self, other: "ThetaSketch") -> None:
        """Fold ``other`` into this sketch so it estimates ``|self ∪ other|``."""
        if not isinstance(other, ThetaSketch):
            raise ThetaError(other)
        o_set, o_n = other._snapshot()
        with self._lock:
            combined = self._set | o_set
            smallest = heapq.nsmallest(self._k, combined)
            self._set = set(smallest)
            self._heap = [-h for h in smallest]
            heapq.heapify(self._heap)
            self._n += o_n

    def reset(self, k: int | None = None, seed: int | None = None) -> None:
        """Clear the sketch; optionally reconfigure ``k`` / ``seed``."""
        with self._lock:
            if k is not None:
                if not _is_pos_int(k) or k < 2:
                    raise ThetaError(k)
                self._k = k
            if seed is not None:
                if not _is_int(seed):
                    raise ThetaError(seed)
                self._seed = seed
            self._set = set()
            self._heap = []
            self._n = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def _snapshot(self) -> tuple[set[float], int]:
        with self._lock:
            return set(self._set), self._n

    def estimate(self) -> float:
        """Estimated distinct-element count (0 when empty; exact below ``k``)."""
        with self._lock:
            return self._estimate_of(self._set)

    def union_estimate(self, other: "ThetaSketch") -> float:
        """Estimated ``|self ∪ other|`` without mutating either sketch."""
        if not isinstance(other, ThetaSketch):
            raise ThetaError(other)
        o_set, _o_n = other._snapshot()
        with self._lock:
            return self._estimate_of(self._set | o_set)

    def intersection_estimate(self, other: "ThetaSketch") -> float:
        """Estimated ``|self ∩ other|`` via inclusion–exclusion (clamped at 0)."""
        if not isinstance(other, ThetaSketch):
            raise ThetaError(other)
        o_set, _o_n = other._snapshot()
        with self._lock:
            a = self._estimate_of(self._set)
            b = self._estimate_of(o_set)
            u = self._estimate_of(self._set | o_set)
            return max(0.0, a + b - u)

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def k(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def retained_count(self) -> int:
        with self._lock:
            return len(self._set)

    @property
    def is_exact(self) -> bool:
        with self._lock:
            return len(self._set) < self._k

    def stats(self) -> dict:
        """Summary: ``k``, total inserts ``n``, ``theta``, ``retained_count``, ``is_exact``."""
        with self._lock:
            retained = len(self._set)
            exact = retained < self._k
            return {
                "k": self._k,
                "n": self._n,
                "theta": self._theta_of(self._set),
                "retained_count": retained,
                "is_exact": exact,
                "estimate": self._estimate_of(self._set),
            }
