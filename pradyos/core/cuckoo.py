"""Phase 86 — Sovereign Cuckoo Filter.

A space-efficient probabilistic set-membership structure — like a Bloom filter
(Phase 72) but, crucially, it supports **deletion**. Each item is reduced to a
small ``fingerprint`` stored in one of two candidate buckets chosen by partial-
key cuckoo hashing: ``i1 = h(item) mod m`` and ``i2 = i1 XOR (h(fp) mod m)``.
Because ``i2`` is recoverable from a bucket index and the fingerprint alone, a
fingerprint can be relocated without the original item — so on insert, if both
buckets are full, an existing fingerprint is "kicked" to its alternate bucket and
the cascade repeats up to ``max_kicks`` times.

``contains`` may report a false positive (rate ≈ ``2·bucket_size / 2^fp_bits``)
but — because a failed insert is rolled back atomically — it **never** reports a
false negative for a present item. The bucket count is rounded up to a power of
two so the XOR alternate-index is a clean involution. The hash is injectable
(``hash_fn``) for deterministic tests. Pure stdlib. Thread-safe via a single
``threading.Lock``; the public surface acquires it, and internal helpers that run
under the lock never re-acquire it (the lock is non-reentrant).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from typing import Any


class CuckooError(Exception):
    """Raised for an invalid filter configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid cuckoo filter configuration: {detail!r}")


def _default_hash(item: Any) -> int:
    if isinstance(item, bytes):
        data = item
    elif isinstance(item, str):
        data = item.encode("utf-8")
    else:
        data = repr(item).encode("utf-8")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


def _next_pow2(n: int) -> int:
    return 1 << (n - 1).bit_length() if n > 1 else 1


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


class SovereignCuckooFilter:
    """Probabilistic membership filter with deletion (stdlib only)."""

    def __init__(
        self,
        capacity: int,
        bucket_size: int = 4,
        fingerprint_bits: int = 8,
        max_kicks: int = 500,
        hash_fn: Callable[[Any], int] | None = None,
    ) -> None:
        if not _is_pos_int(capacity):
            raise CuckooError(capacity)
        if not _is_pos_int(bucket_size):
            raise CuckooError(bucket_size)
        if not _is_pos_int(fingerprint_bits) or fingerprint_bits > 32:
            raise CuckooError(fingerprint_bits)
        if not _is_pos_int(max_kicks):
            raise CuckooError(max_kicks)
        self._capacity = _next_pow2(capacity)  # bucket count (power of two)
        self._bucket_size = bucket_size
        self._fp_bits = fingerprint_bits
        self._fp_max = (1 << fingerprint_bits) - 1
        self._max_kicks = max_kicks
        self._hash_fn = hash_fn or _default_hash
        self._buckets: list[list[int]] = [[] for _ in range(self._capacity)]
        self._count = 0
        self._lock = threading.Lock()

    # ── hashing helpers (no lock; pure) ──────────────────────────────────────
    def _fingerprint(self, h: int) -> int:
        fp = h & self._fp_max
        return fp if fp != 0 else 1  # 0 is reserved for "empty"

    def _candidates(self, item: Any) -> tuple[int, int, int]:
        h = self._hash_fn(item)
        fp = self._fingerprint(h)
        i1 = (h >> self._fp_bits) % self._capacity
        i2 = i1 ^ (self._hash_fn(fp) % self._capacity)
        return fp, i1, i2

    def _alt_index(self, index: int, fp: int) -> int:
        return index ^ (self._hash_fn(fp) % self._capacity)

    # ── mutation ──────────────────────────────────────────────────────────────
    def insert(self, item: Any) -> bool:
        """Add ``item``. Returns False if the filter is full after ``max_kicks``."""
        with self._lock:
            fp, i1, i2 = self._candidates(item)
            if len(self._buckets[i1]) < self._bucket_size:
                self._buckets[i1].append(fp)
                self._count += 1
                return True
            if len(self._buckets[i2]) < self._bucket_size:
                self._buckets[i2].append(fp)
                self._count += 1
                return True
            # both full → cuckoo kicks, recording each swap so we can roll back
            cur = i1
            moving = fp
            changes: list[tuple[int, int, int]] = []
            for n in range(self._max_kicks):
                slot = n % self._bucket_size
                changes.append((cur, slot, self._buckets[cur][slot]))
                evicted = self._buckets[cur][slot]
                self._buckets[cur][slot] = moving
                moving = evicted
                cur = self._alt_index(cur, moving)
                if len(self._buckets[cur]) < self._bucket_size:
                    self._buckets[cur].append(moving)
                    self._count += 1
                    return True
            # failed: restore the table exactly (no lost fingerprints → no false negatives)
            for bucket, slot, old in reversed(changes):
                self._buckets[bucket][slot] = old
            return False

    def delete(self, item: Any) -> bool:
        """Remove one fingerprint of ``item``. Returns False if it is not present."""
        with self._lock:
            fp, i1, i2 = self._candidates(item)
            if fp in self._buckets[i1]:
                self._buckets[i1].remove(fp)
                self._count -= 1
                return True
            if fp in self._buckets[i2]:
                self._buckets[i2].remove(fp)
                self._count -= 1
                return True
            return False

    def reset(self) -> None:
        """Clear every bucket."""
        with self._lock:
            self._buckets = [[] for _ in range(self._capacity)]
            self._count = 0

    # ── queries ─────────────────────────────────────────────────────────────
    def contains(self, item: Any) -> bool:
        """Membership test (may false-positive, never false-negative)."""
        with self._lock:
            fp, i1, i2 = self._candidates(item)
            return fp in self._buckets[i1] or fp in self._buckets[i2]

    def __contains__(self, item: Any) -> bool:
        return self.contains(item)

    def __len__(self) -> int:
        with self._lock:
            return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    def stats(self) -> dict:
        """Filter metadata: bucket count, fingerprints stored, load, and config."""
        with self._lock:
            total_slots = self._capacity * self._bucket_size
            return {
                "capacity": self._capacity,
                "count": self._count,
                "load_factor": round(self._count / total_slots, 6) if total_slots else 0.0,
                "fingerprint_bits": self._fp_bits,
                "max_kicks": self._max_kicks,
            }
