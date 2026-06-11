"""Phase 103 — Sovereign Spectral Bloom Filter (Cohen & Matias, 2003).

A **frequency-aware** Bloom filter. The standard Bloom filter (P12) stores a
single presence *bit* per hash position and answers only *membership*; the
spectral filter replaces each bit with an integer **counter**, so it answers
*how many* — an item's multiplicity is estimated as the **minimum** counter
across its ``k`` hash positions. That minimum is the natural estimator here (the
exact opposite of HeavyKeeper's *max*, P102): collisions can only push a counter
*higher*, so the smallest of an item's counters is the tightest upper-bounded
estimate of its true count, and over-counting — never under-counting — is the
failure mode (zero false negatives, like any Bloom).

Because the cells are counters rather than bits, the spectral filter also
supports **deletion**: ``remove`` decrements an item's counters (guarded so a
non-member, whose minimum is already 0, is never touched and counters never go
negative) — the practical advantage over a plain Bloom, which cannot delete.

Sizing follows the standard Bloom formulae from ``capacity`` (expected distinct
items) and ``error_rate`` (target membership FPR):

    m = ⌈ -capacity · ln(error_rate) / ln(2)² ⌉      (counter slots)
    k = round( (m / capacity) · ln 2 )               (hash functions, ≥ 1)

Membership FPR (``min > 0``) is therefore the same as a standard Bloom of the
same parameters. The ``k`` positions come from one seeded BLAKE2b digest split
into two 64-bit halves and combined by Kirsch–Mitzenmacher double hashing
(``h1 + i·h2 mod m``) — deterministic for a given ``seed`` (the hashing idiom of
MinHash (P88) / Ribbon (P101) / HeavyKeeper (P102)). Pure stdlib; thread-safe via
a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

_LN2 = math.log(2.0)


class SpectralBloomError(Exception):
    """Raised for an invalid Spectral-Bloom configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_rate(x: Any) -> bool:
    return (not isinstance(x, bool)) and isinstance(x, int | float) and 0.0 < float(x) < 1.0


class SpectralBloom:
    """Counting Bloom filter with min-counter multiplicity estimation and deletion."""

    def __init__(self, capacity: int = 10000, error_rate: float = 0.01, seed: int = 0) -> None:
        self._validate(capacity, error_rate, seed)
        self._capacity = capacity
        self._error_rate = float(error_rate)
        self._seed = seed
        self._lock = threading.Lock()
        self._size()
        self._counters = [0] * self._m
        self._num_added = 0

    # ── config ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _validate(capacity: Any, error_rate: Any, seed: Any) -> None:
        if not _is_pos_int(capacity):
            raise SpectralBloomError(capacity)
        if not _is_rate(error_rate):
            raise SpectralBloomError(error_rate)
        if not _is_int(seed):
            raise SpectralBloomError(seed)

    def _size(self) -> None:
        m = math.ceil(-(self._capacity * math.log(self._error_rate)) / (_LN2 * _LN2))
        self._m = max(1, int(m))
        self._k = max(1, round((self._m / self._capacity) * _LN2))

    # ── hashing (pure) ──────────────────────────────────────────────────────────
    def _positions(self, element: Any) -> list[int]:
        digest = hashlib.blake2b(
            repr((self._seed, element)).encode("utf-8"), digest_size=16
        ).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1  # odd → full period under double hashing
        m = self._m
        return [(h1 + i * h2) % m for i in range(self._k)]

    # ── mutation ────────────────────────────────────────────────────────────────
    def add(self, element: Any, count: int = 1) -> int:
        """Add ``count`` occurrences of ``element``; return its updated multiplicity estimate."""
        if not _is_pos_int(count):
            raise SpectralBloomError(count)
        with self._lock:
            pos = self._positions(element)
            for p in pos:
                self._counters[p] += count
            self._num_added += count
            return min(self._counters[p] for p in pos)

    def remove(self, element: Any, count: int = 1) -> int:
        """Remove up to ``count`` occurrences (only if present); return the number removed."""
        if not _is_pos_int(count):
            raise SpectralBloomError(count)
        with self._lock:
            pos = self._positions(element)
            current = min(self._counters[p] for p in pos)
            if current == 0:
                return 0  # not a member — never touch counters
            removed = min(count, current)
            for p in pos:
                self._counters[p] = max(0, self._counters[p] - removed)
            self._num_added -= removed
            return removed

    def reset(
        self, capacity: int | None = None, error_rate: float | None = None, seed: int | None = None
    ) -> None:
        """Clear all counters; optionally reconfigure (re-derives ``m`` and ``k``)."""
        with self._lock:
            nc = self._capacity if capacity is None else capacity
            ne = self._error_rate if error_rate is None else error_rate
            ns = self._seed if seed is None else seed
            self._validate(nc, ne, ns)
            self._capacity, self._error_rate, self._seed = nc, float(ne), ns
            self._size()
            self._counters = [0] * self._m
            self._num_added = 0

    # ── query ───────────────────────────────────────────────────────────────────
    def query(self, element: Any) -> int:
        """Estimated multiplicity of ``element`` — the min counter across its ``k`` positions."""
        with self._lock:
            return min(self._counters[p] for p in self._positions(element))

    def __contains__(self, element: Any) -> bool:
        return self.query(element) > 0

    def __len__(self) -> int:
        with self._lock:
            return self._num_added

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
    def num_bits(self) -> int:
        return self._m

    @property
    def num_hashes(self) -> int:
        return self._k

    def stats(self) -> dict:
        """Summary: ``capacity`` / ``error_rate`` / ``num_bits`` (m) / ``num_hashes`` (k) /
        ``num_added`` (net occurrences) / ``estimated_fill_ratio`` (non-zero counters / m)."""
        with self._lock:
            nonzero = sum(1 for c in self._counters if c)
            return {
                "capacity": self._capacity,
                "error_rate": self._error_rate,
                "num_bits": self._m,
                "num_hashes": self._k,
                "num_added": self._num_added,
                "estimated_fill_ratio": nonzero / self._m,
            }
