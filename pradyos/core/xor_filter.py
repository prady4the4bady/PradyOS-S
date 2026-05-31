"""Phase 100 — Sovereign XOR Filter (Graf–Lemire, 2020).  🎯 centennial.

A **static, space-optimal** approximate-membership filter. Unlike the Phase 72
Bloom filter (incremental) and the Phase 86 Cuckoo filter (incremental, with
deletion), an XOR filter is **built once** from a complete key set and is then
immutable — which is exactly what lets it beat both on space and lookup speed:

  * **Space:** the XOR filter's theoretical bound is ≈ ``1.23 · n · bits_per_entry``
    bits. This implementation sizes each of the three segments at ``⌈1.23·n⌉`` slots
    (≈ ``3.69·n`` total) — the generous regime under which single-pass peeling is
    reliable, trading some space for a one-shot build that essentially never stalls.
  * **Lookup:** exactly three memory probes, no search — ``Bloom`` needs ``k``
    probes and ``Cuckoo`` may scan a bucket.
  * **False-positive rate:** ≈ ``2 ** -bits_per_entry`` (≈ 0.4 % at 8 bits).

Construction (peeling): each key maps to three buckets ``h0, h1, h2`` — one in
each segment. Repeatedly find a bucket touched by exactly one (still-unassigned)
key and "peel" that key, recording (key, bucket); this yields an order in which
every key owns a bucket no later key touches. Fingerprints are then assigned in
reverse peel order: ``F[b] = fingerprint(k) ⊕ F[other1] ⊕ F[other2]``, so a query
satisfies ``fingerprint(k) == F[h0] ⊕ F[h1] ⊕ F[h2]`` for every built key (zero
false negatives). Peeling is probabilistic; at ~1.23·n slots it essentially
always succeeds, but on a rare adversarial input it can stall — then a
:class:`XorFilterError` asks for a different seed.

Fingerprints are the low ``bits_per_entry`` bits of a seeded BLAKE2b digest (the
same hashing pattern as MinHash (P88) and Count Sketch (P94)). Pure stdlib.
Thread-safe via a single ``threading.Lock``; internal ``_*`` helpers run under it.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any


class XorFilterError(Exception):
    """Raised for an invalid XOR-filter configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class XorFilter:
    """Static, space-optimal membership filter built by peeling (Graf–Lemire)."""

    def __init__(self, bits_per_entry: int = 8, seed: int = 0) -> None:
        if not _is_pos_int(bits_per_entry) or bits_per_entry > 64:
            raise XorFilterError(bits_per_entry)
        if not _is_int(seed):
            raise XorFilterError(seed)
        self._bits = bits_per_entry
        self._mask = (1 << bits_per_entry) - 1
        self._seed = seed
        self._array: list[int] = []
        self._segment = 0
        self._n = 0
        self._built = False
        self._lock = threading.Lock()

    # ── hashing (pure) ────────────────────────────────────────────────────────────
    def _digest(self, tag: Any, key: Any) -> int:
        data = repr((self._seed, tag, key)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")

    def _fingerprint(self, key: Any) -> int:
        return self._digest("fp", key) & self._mask

    def _buckets(self, key: Any, segment: int) -> tuple[int, int, int]:
        return (self._digest(0, key) % segment,
                self._digest(1, key) % segment + segment,
                self._digest(2, key) % segment + 2 * segment)

    # ── build (static construction) ──────────────────────────────────────────────
    def build(self, keys: Any) -> None:
        """Construct the filter from a complete key set (replaces any prior filter)."""
        distinct = list(dict.fromkeys(keys))          # dedup, preserve order
        n = len(distinct)
        # ⌈1.23·n⌉ slots PER SEGMENT (3 segments) — the generous sizing under which
        # single-pass peeling essentially never stalls.
        segment = int(math.ceil(1.23 * n)) + 1
        total = 3 * segment

        fps = [self._fingerprint(k) for k in distinct]
        hashes = [self._buckets(k, segment) for k in distinct]

        count = [0] * total
        xor_idx = [0] * total
        for i in range(n):
            for b in hashes[i]:
                count[b] += 1
                xor_idx[b] ^= i

        queue = [b for b in range(total) if count[b] == 1]
        stack: list[tuple[int, int]] = []
        peeled = [False] * n
        while queue:
            b = queue.pop()
            if count[b] != 1:
                continue
            i = xor_idx[b]
            if peeled[i]:
                continue
            peeled[i] = True
            stack.append((i, b))
            for bb in hashes[i]:
                count[bb] -= 1
                xor_idx[bb] ^= i
                if count[bb] == 1:
                    queue.append(bb)

        if len(stack) != n:
            raise XorFilterError("peeling failed — retry with different seed")

        # Assign fingerprints in reverse peel order.
        array = [0] * total
        for i, b in reversed(stack):
            o1, o2 = (x for x in hashes[i] if x != b)
            array[b] = fps[i] ^ array[o1] ^ array[o2]

        with self._lock:
            self._array = array
            self._segment = segment
            self._n = n
            self._built = True

    def reset(self, bits_per_entry: int | None = None, seed: int | None = None) -> None:
        """Clear the filter back to the unbuilt state; optionally reconfigure."""
        with self._lock:
            if bits_per_entry is not None:
                if not _is_pos_int(bits_per_entry) or bits_per_entry > 64:
                    raise XorFilterError(bits_per_entry)
                self._bits = bits_per_entry
                self._mask = (1 << bits_per_entry) - 1
            if seed is not None:
                if not _is_int(seed):
                    raise XorFilterError(seed)
                self._seed = seed
            self._array = []
            self._segment = 0
            self._n = 0
            self._built = False

    # ── query ────────────────────────────────────────────────────────────────────
    def contains(self, key: Any) -> bool:
        """Membership test (no false negatives for built keys; ``≈2**-bits`` false positives)."""
        with self._lock:
            if not self._built:
                raise XorFilterError("filter not built — call build() first")
            segment = self._segment
            array = self._array
            fp = self._fingerprint(key)
            h0, h1, h2 = self._buckets(key, segment)
            return fp == (array[h0] ^ array[h1] ^ array[h2])

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def bits_per_entry(self) -> int:
        return self._bits

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def built(self) -> bool:
        with self._lock:
            return self._built

    @property
    def array_size(self) -> int:
        with self._lock:
            return len(self._array)

    def stats(self) -> dict:
        """Summary: ``bits_per_entry``, ``built``, key count ``n``, ``array_size``,
        ``segment_size``, and the ``≈2**-bits`` false-positive rate."""
        with self._lock:
            return {
                "bits_per_entry": self._bits,
                "built": self._built,
                "n": self._n,
                "array_size": len(self._array),
                "segment_size": self._segment,
                "false_positive_rate": 2.0 ** (-self._bits),
            }
