"""Phase 72 — Sovereign Bloom Filter.

A space-efficient probabilistic set-membership structure. Items are hashed into
a fixed bit array; :meth:`contains` may return a false positive (says "present"
when it isn't) but **never** a false negative (if an item was added,
``contains`` is guaranteed ``True``). This makes it ideal for cheap "have I seen
this before?" guards — dedup of campaign ids, already-processed events, etc. —
without storing every key.

The bit count ``m`` and hash count ``k`` are derived from the target
``capacity`` (expected number of items ``n``) and ``error_rate`` (target false-
positive probability ``p``) using the standard optimal sizing::

    m = ceil(-(n * ln p) / (ln 2)^2)
    k = round((m / n) * ln 2)

Hashing uses the Kirsch–Mitzenmacher double-hashing technique — two 64-bit
halves of a single SHA-256 digest generate all ``k`` indices — so the structure
is fully deterministic and pure stdlib (``hashlib`` + a ``bytearray``).
Thread-safe via a single non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any, Iterable


class BloomFilter:
    """A deterministic, thread-safe Bloom filter (stdlib only)."""

    def __init__(self, capacity: int = 1000, error_rate: float = 0.01) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        if not 0.0 < error_rate < 1.0:
            raise ValueError("error_rate must be between 0 and 1 (exclusive)")
        self._capacity = int(capacity)
        self._error_rate = float(error_rate)
        # Optimal bit count (m) and hash count (k).
        m = math.ceil(-(self._capacity * math.log(self._error_rate)) / (math.log(2) ** 2))
        self._bits = max(1, int(m))
        k = round((self._bits / self._capacity) * math.log(2))
        self._hashes = max(1, int(k))
        self._array = bytearray((self._bits + 7) // 8)
        self._count = 0
        self._lock = threading.Lock()

    # ── hashing / bit helpers (no lock; callers that mutate hold the lock) ────
    def _indices(self, item: Any) -> list[int]:
        data = item.encode("utf-8") if isinstance(item, str) else repr(item).encode("utf-8")
        digest = hashlib.sha256(data).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") | 1  # force odd ⇒ never a zero step
        return [(h1 + i * h2) % self._bits for i in range(self._hashes)]

    def _get_bit(self, idx: int) -> int:
        return (self._array[idx >> 3] >> (idx & 7)) & 1

    def _set_bit(self, idx: int) -> None:
        self._array[idx >> 3] |= 1 << (idx & 7)

    # ── mutation ──────────────────────────────────────────────────────────────
    def add(self, item: Any) -> bool:
        """Add ``item``. Returns True if it was (probably) new, False if every
        target bit was already set (already present, or a hash collision)."""
        with self._lock:
            was_new = False
            for idx in self._indices(item):
                if not self._get_bit(idx):
                    was_new = True
                    self._set_bit(idx)
            if was_new:
                self._count += 1
            return was_new

    def add_many(self, items: Iterable[Any]) -> int:
        """Add every item in ``items``; return how many were (probably) new."""
        return sum(1 for item in items if self.add(item))

    def clear(self) -> None:
        """Reset to empty (all bits cleared, count zero)."""
        with self._lock:
            self._array = bytearray((self._bits + 7) // 8)
            self._count = 0

    # ── queries ─────────────────────────────────────────────────────────────
    def contains(self, item: Any) -> bool:
        """True if ``item`` *may* be present (no false negatives)."""
        with self._lock:
            return all(self._get_bit(idx) for idx in self._indices(item))

    def __contains__(self, item: Any) -> bool:
        return self.contains(item)

    def __len__(self) -> int:
        """Approximate number of distinct items added."""
        with self._lock:
            return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def error_rate(self) -> float:
        return self._error_rate

    @property
    def bits(self) -> int:
        return self._bits

    @property
    def hashes(self) -> int:
        return self._hashes

    def fill_ratio(self) -> float:
        """Fraction of bits currently set (0.0 – 1.0)."""
        with self._lock:
            set_bits = sum(bin(byte).count("1") for byte in self._array)
            return set_bits / self._bits

    def estimated_false_positive_rate(self) -> float:
        """Current estimated false-positive probability: (1 - e^(-k·n/m))^k."""
        with self._lock:
            n, k, m = self._count, self._hashes, self._bits
        return (1.0 - math.exp(-k * n / m)) ** k

    def stats(self) -> dict:
        """JSON-serialisable snapshot of the filter's configuration and state."""
        with self._lock:
            set_bits = sum(bin(byte).count("1") for byte in self._array)
            n, k, m = self._count, self._hashes, self._bits
        return {
            "capacity": self._capacity,
            "error_rate": self._error_rate,
            "bits": m,
            "hashes": k,
            "count": n,
            "fill_ratio": round(set_bits / m, 6),
            "est_false_positive_rate": round((1.0 - math.exp(-k * n / m)) ** k, 6),
        }
