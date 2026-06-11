"""Phase 109 — Sovereign Vacuum Filter (Wang, Zhou, Yang, Du, Yang & Uhlig, 2019).

A space-efficient approximate-membership filter in the **cuckoo-fingerprint**
family (cf. the Phase 86 cuckoo filter) that supports both **insertion** and
**deletion** while using *less* space than the cuckoo filter — and competitive
with the static XOR/fuse filters — at the same false-positive rate.

The cuckoo filter stores a small ``fingerprint`` of each item in one of two
candidate buckets, where the alternate bucket is recovered from the current one
by ``i2 = i1 XOR H(fp)``. For that XOR to be an *involution* over ``[0, m)`` the
bucket count ``m`` **must be rounded up to a power of two** — wasting on average
~1.5× (up to 2×) the space actually needed.

The Vacuum Filter removes that constraint with an **Alternate Range** ``L``: the
two candidate buckets of an item are confined to the same ``L``-aligned *chunk*
of ``L`` consecutive buckets, where ``L`` is a power of two. The displacement is

    i2 = i1 XOR (H(fp) mod L)            (L a power of two)

Because ``H(fp) mod L < L`` flips only the low ``log2(L)`` bits, ``i1`` and
``i2`` always share the same ``L``-aligned chunk ``[⌊i1/L⌋·L, ⌊i1/L⌋·L + L)``.
The bucket count only has to be a **multiple of L** (``m = num_chunks · L``) — it
need *not* be a power of two — so ``m`` can sit much closer to the true required
size. Each chunk is itself an independent power-of-two cuckoo sub-table, so
within a chunk the standard partial-key cuckoo kicking reaches high occupancy,
while the chunk count absorbs the rest at fine granularity. The XOR stays an
involution because ``⌊i1/L⌋·L`` is a multiple of ``L`` (its low ``log2(L)`` bits
are zero) and ``m`` is a multiple of ``L`` (so ``chunk_base + L ≤ m``); the
displacement ``H(fp) mod L`` depends only on the fingerprint, identical when
probing from either bucket, so ``alt(alt(i, fp), fp) == i``. Confinement is
absolute — a kicked fingerprint never leaves its origin chunk — so the filter
**never reports a false negative** for a present item (a failed insert is rolled
back atomically), while ``contains`` may false-positive at rate
``≈ 2·bucket_size / 2^fingerprint_bits`` exactly as the cuckoo filter does.

This is the single-alternate-range design; the paper's further *alternate-range
selection* (a small per-fingerprint set of ranges) squeezes load to ~95–97% on
near-power-of-two sizes, but the single range already delivers the headline
property — a non-power-of-two table — and the resulting space saving.

The hash is injectable (``hash_fn``) for deterministic tests, and a ``seed``
salts the default stable BLAKE2b fold (process-independent). Pure stdlib.
Thread-safe via a single ``threading.Lock``; the public surface acquires it and
internal helpers that run under the lock never re-acquire it (the lock is
non-reentrant).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from typing import Any

_MASK64 = (1 << 64) - 1


class VacuumFilterError(Exception):
    """Raised for an invalid filter configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid vacuum filter configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_pow2(x: Any) -> bool:
    return _is_pos_int(x) and (x & (x - 1)) == 0


def _next_pow2(n: int) -> int:
    return 1 << (n - 1).bit_length() if n > 1 else 1


def _prev_pow2(n: int) -> int:
    return 1 << (n.bit_length() - 1) if n >= 1 else 1


def _auto_alt_range(num_buckets: int) -> int:
    """Pick a sensible alternate range (chunk size, a power of two).

    Aims for ~8 large chunks: large chunks keep cross-chunk load variance low and
    give the intra-chunk cuckoo sub-table room to reach high occupancy, while a
    non-power-of-two chunk count is what buys the space saving over the cuckoo
    filter. Never exceeds ``_prev_pow2(num_buckets)`` so the range always fits."""
    if num_buckets < 8:
        return 1
    target = _prev_pow2(num_buckets // 8)
    return max(1, min(target, _prev_pow2(num_buckets)))


def _default_hash_factory(seed: int) -> Callable[[Any], int]:
    """Return a stable, process-independent 64-bit hash salted by ``seed``."""
    salt = (seed & _MASK64).to_bytes(8, "big")

    def _h(x: Any) -> int:
        if isinstance(x, bytes):
            data = x
        elif isinstance(x, str):
            data = x.encode("utf-8")
        else:
            data = repr(x).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8, salt=salt).digest(), "big")

    return _h


class VacuumFilter:
    """Approximate-membership filter with deletion and non-power-of-two sizing."""

    def __init__(
        self,
        capacity: int,
        bucket_size: int = 4,
        fingerprint_bits: int = 8,
        max_kicks: int = 500,
        alt_range: int | None = None,
        seed: int = 0,
        hash_fn: Callable[[Any], int] | None = None,
    ) -> None:
        if not _is_pos_int(capacity):
            raise VacuumFilterError(capacity)
        if not _is_pos_int(bucket_size):
            raise VacuumFilterError(bucket_size)
        if not _is_pos_int(fingerprint_bits) or fingerprint_bits > 32:
            raise VacuumFilterError(fingerprint_bits)
        if not _is_pos_int(max_kicks):
            raise VacuumFilterError(max_kicks)
        if not _is_int(seed):
            raise VacuumFilterError(seed)
        if alt_range is None:
            alt_range = _auto_alt_range(capacity)
        elif not _is_pow2(alt_range):
            raise VacuumFilterError(alt_range)

        # Round the requested bucket count up to a multiple of the alternate range
        # (chunk size) — NOT up to a power of two as the cuckoo filter must.
        alt_range = min(alt_range, _prev_pow2(capacity)) if capacity >= 1 else alt_range
        alt_range = max(1, alt_range)
        num_chunks = (capacity + alt_range - 1) // alt_range
        num_chunks = max(1, num_chunks)

        self._L = alt_range
        self._num_chunks = num_chunks
        self._m = num_chunks * alt_range
        self._bucket_size = bucket_size
        self._fp_bits = fingerprint_bits
        self._fp_max = (1 << fingerprint_bits) - 1
        self._max_kicks = max_kicks
        self._seed = seed
        self._hash_fn = hash_fn or _default_hash_factory(seed)
        self._buckets: list[list[int]] = [[] for _ in range(self._m)]
        self._count = 0
        self._lock = threading.Lock()

    # ── hashing helpers (no lock; pure) ──────────────────────────────────────
    def _fingerprint(self, h: int) -> int:
        fp = h & self._fp_max
        return fp if fp != 0 else 1  # 0 is reserved for "empty"

    def _candidates(self, item: Any) -> tuple[int, int, int]:
        h = self._hash_fn(item)
        fp = self._fingerprint(h)
        i1 = (h >> self._fp_bits) % self._m
        i2 = i1 ^ (self._hash_fn(fp) & (self._L - 1))  # alternate within the chunk
        return fp, i1, i2

    def _alt_index(self, index: int, fp: int) -> int:
        return index ^ (self._hash_fn(fp) & (self._L - 1))

    # ── mutation ──────────────────────────────────────────────────────────────
    def insert(self, item: Any) -> bool:
        """Add ``item``. Returns False if its chunk is full after ``max_kicks``."""
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
            # both full → cuckoo kicks within the chunk, recording each swap to roll back
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
            self._buckets = [[] for _ in range(self._m)]
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
        """Number of buckets (a multiple of the alternate range)."""
        return self._m

    @property
    def alt_range(self) -> int:
        return self._L

    @property
    def num_chunks(self) -> int:
        return self._num_chunks

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Filter metadata: bucket count, chunk layout, fingerprints stored, load, config."""
        with self._lock:
            total_slots = self._m * self._bucket_size
            return {
                "capacity": self._m,
                "num_chunks": self._num_chunks,
                "alt_range": self._L,
                "count": self._count,
                "load_factor": round(self._count / total_slots, 6) if total_slots else 0.0,
                "fingerprint_bits": self._fp_bits,
                "max_kicks": self._max_kicks,
            }
