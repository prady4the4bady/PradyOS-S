"""Phase 107 — Sovereign Counting Bloom Filter.

A Bloom filter whose single-bit array is replaced by an array of small **integer
counters**, which buys the one thing a classic Bloom cannot do: **deletion**.
``add`` increments each of the ``k`` hashed counters; ``remove`` decrements them;
``contains`` reports membership when *every* hashed counter is ``≥ 1``. Like any
Bloom variant it admits **false positives** (a non-member whose ``k`` counters
were all set by other elements) but — counter saturation aside — **no false
negatives**.

Sizing (standard Bloom formulae) — for an expected ``capacity`` ``n`` and target
``error_rate`` ``p``:

    m = ⌈ -n·ln(p) / (ln 2)² ⌉      (number of counters)
    k = ⌈ (m/n)·ln 2 ⌉             (number of hash functions)

Counters are **4-bit-valued** (the classic width — 16 states ``0..15``), held one
per byte in an ``array.array('B')`` for simple, fast access; ``add`` is
**saturating** at 15 so a hot element can never overflow its counter and corrupt
the count. The 4-bit value range is enough for the vast majority of streams;
saturation only sacrifices exact deletion for elements added more than 15 times
(a documented, bounded degradation).

Hashing uses a **double-hashing** scheme — ``h_i(x) = (h1(x) + i·h2(x)) mod m``
for ``i = 0..k-1`` — where ``h1`` / ``h2`` are two halves of a single seeded
BLAKE2b digest of the element (the same stable, process-independent folding idiom
as MinHash (P88)). This yields ``k`` well-distributed probes from one hash.

Pure stdlib (``array`` + ``hashlib``); thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import array
import hashlib
import math
import threading
from typing import Any

_MAX_COUNTER = 15  # 4-bit saturating counter ceiling


class CountingBloomError(Exception):
    """Raised for an invalid Counting-Bloom operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class CountingBloom:
    """Deletion-supporting Bloom filter over 4-bit saturating counters."""

    def __init__(self, capacity: int = 10000, error_rate: float = 0.01,
                 seed: int = 0) -> None:
        self._validate(capacity, error_rate, seed)
        self._capacity = capacity
        self._error_rate = error_rate
        self._seed = seed
        self._lock = threading.Lock()
        self._configure()

    @staticmethod
    def _validate(capacity: Any, error_rate: Any, seed: Any) -> None:
        if not _is_pos_int(capacity):
            raise CountingBloomError(capacity)
        if not (_is_number(error_rate) and 0.0 < error_rate < 1.0):
            raise CountingBloomError(error_rate)
        if not _is_int(seed):
            raise CountingBloomError(seed)

    def _configure(self) -> None:
        n, p = self._capacity, self._error_rate
        m = math.ceil(-n * math.log(p) / (math.log(2) ** 2))
        m = max(1, m)
        k = math.ceil((m / n) * math.log(2))
        k = max(1, k)
        self._m = m
        self._k = k
        self._init_state()

    def _init_state(self) -> None:
        # One byte per counter (only the low nibble is used); simple and fast.
        self._counters = array.array("B", bytes(self._m))
        self._count = 0

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _indices(self, element: Any) -> list[int]:
        """Double-hashing: ``(h1 + i·h2) mod m`` for ``i = 0..k-1`` from one seeded BLAKE2b digest."""
        data = repr((self._seed, element)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1  # force odd → full period under mod m
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, element: str) -> None:
        """Add ``element`` — increment each of its ``k`` counters (saturating at 15)."""
        with self._lock:
            for idx in self._indices(element):
                if self._counters[idx] < _MAX_COUNTER:
                    self._counters[idx] += 1
            self._count += 1

    def contains(self, element: str) -> bool:
        """True iff every one of ``element``'s ``k`` counters is ``≥ 1``."""
        with self._lock:
            return all(self._counters[idx] >= 1 for idx in self._indices(element))

    def remove(self, element: str) -> None:
        """Decrement ``element``'s ``k`` counters; raise if it is not present.

        Guarding on membership first prevents *under-decrement corruption* — blindly
        decrementing counters for an absent element would corrupt the counts of
        whatever genuine members share those slots."""
        with self._lock:
            indices = self._indices(element)
            if not all(self._counters[idx] >= 1 for idx in indices):
                raise CountingBloomError("element not in filter")
            for idx in indices:
                if self._counters[idx] < _MAX_COUNTER:  # never decrement a saturated counter
                    self._counters[idx] -= 1
            self._count -= 1

    def false_positive_rate(self) -> float:
        """Empirical FPR estimate ``(1 - e^(-k·n/m))^k`` for the current load ``n = count``."""
        with self._lock:
            return self._fpr_locked()

    def _fpr_locked(self) -> float:
        n = self._count
        if n <= 0:
            return 0.0
        return (1.0 - math.exp(-self._k * n / self._m)) ** self._k

    def reset(self, capacity: int | None = None, error_rate: float | None = None,
              seed: int | None = None) -> None:
        """Clear all counters; optionally reconfigure ``capacity`` / ``error_rate`` / ``seed``."""
        with self._lock:
            nc = self._capacity if capacity is None else capacity
            ne = self._error_rate if error_rate is None else error_rate
            ns = self._seed if seed is None else seed
            self._validate(nc, ne, ns)
            self._capacity, self._error_rate, self._seed = nc, ne, ns
            self._configure()

    def __contains__(self, element: str) -> bool:
        return self.contains(element)

    def __len__(self) -> int:
        with self._lock:
            return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def error_rate(self) -> float:
        return self._error_rate

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_hash_functions(self) -> int:
        return self._k

    @property
    def num_counters(self) -> int:
        return self._m

    @property
    def count(self) -> int:
        """Number of ``add`` calls — **not** the number of unique elements (collisions /
        repeated adds both bump this)."""
        with self._lock:
            return self._count

    def stats(self) -> dict:
        """Summary: ``capacity`` / ``error_rate`` / ``num_hash_functions`` (k) /
        ``num_counters`` (m) / ``count`` (n) / ``false_positive_rate``."""
        with self._lock:
            return {
                "capacity": self._capacity,
                "error_rate": self._error_rate,
                "num_hash_functions": self._k,
                "num_counters": self._m,
                "count": self._count,
                "false_positive_rate": self._fpr_locked(),
            }
