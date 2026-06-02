"""Phase 124 — Sovereign Jump Consistent Hash (Lamping & Veach, 2014).

*A Fast, Minimal Memory, Consistent Hash Algorithm* — Google's strikingly compact
consistent-hashing scheme and the **fourth** distributed key→bucket assignment algorithm
in the platform, alongside the Hash Ring (P73), Rendezvous/HRW (P119) and Maglev (P120).
Its entire state is a single integer — the **bucket count** — with no ring, score array,
or lookup table.

``assign`` runs a short loop that, using the key's 64-bit hash as a seeded LCG, "jumps"
forward through candidate bucket indices and returns the last index below the bucket
count:

    b = -1, j = 0
    while j < num_buckets:
        b = j
        key = key * 2862933555777941757 + 1        (64-bit LCG step)
        j = floor((b + 1) * (2^31 / ((key >> 33) + 1)))
    return b

This is ``O(ln N)`` time and ``O(1)`` space with zero allocation. It provably gives
**uniform load** (each bucket ≈ ``1/N`` of keys) and **optimal minimal disruption**:
growing the bucket count from ``N`` to ``N + 1`` moves *exactly* ``1/(N+1)`` of keys, and
only into the new bucket — the information-theoretic minimum. The trade-off versus the
ring / HRW / Maglev is that buckets are an *ordered range* ``[0, N)`` with no arbitrary
names, and only the **last** bucket can be removed cheaply.

The key is folded to a stable 64-bit integer (seeded BLAKE2b); the jump loop is otherwise
deterministic, so assignments are reproducible. Pure stdlib; thread-safe via a single
``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

_MASK64 = (1 << 64) - 1
_LCG_MULT = 2862933555777941757
_TWO31 = float(1 << 31)


class JumpHashError(Exception):
    """Raised for an invalid Jump-hash operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def jump_consistent_hash(key_hash: int, num_buckets: int) -> int:
    """The core Lamping–Veach jump algorithm: map a 64-bit ``key_hash`` to ``[0, num_buckets)``."""
    if not _is_pos_int(num_buckets):
        raise JumpHashError(num_buckets)
    key = key_hash & _MASK64
    b = -1
    j = 0
    while j < num_buckets:
        b = j
        key = (key * _LCG_MULT + 1) & _MASK64
        j = int((b + 1) * (_TWO31 / float((key >> 33) + 1)))
    return b


class JumpHash:
    """Jump consistent hashing — stateless O(1)-space key→bucket assignment."""

    def __init__(self, num_buckets: int = 1, seed: int = 0) -> None:
        if not _is_pos_int(num_buckets):
            raise JumpHashError(num_buckets)
        if not _is_int(seed):
            raise JumpHashError(seed)
        self._num_buckets = num_buckets
        self._seed = seed
        self._lock = threading.Lock()

    def _key_hash(self, key: Any) -> int:
        data = repr((self._seed, key)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")

    # ── assignment ─────────────────────────────────────────────────────────────────────
    def assign(self, key: Any) -> int:
        """Return the bucket in ``[0, num_buckets)`` responsible for ``key``."""
        with self._lock:
            return jump_consistent_hash(self._key_hash(key), self._num_buckets)

    def assign_for(self, key: Any, num_buckets: int) -> int:
        """Bucket for ``key`` under an arbitrary ``num_buckets`` (does not change state)."""
        with self._lock:
            return jump_consistent_hash(self._key_hash(key), num_buckets)

    # ── bucket-count management ──────────────────────────────────────────────────────
    def set_buckets(self, num_buckets: int) -> None:
        """Set the bucket count (``≥ 1``)."""
        with self._lock:
            if not _is_pos_int(num_buckets):
                raise JumpHashError(num_buckets)
            self._num_buckets = num_buckets

    def add_bucket(self) -> int:
        """Append one bucket (only ≈ ``1/(N+1)`` of keys move); return the new count."""
        with self._lock:
            self._num_buckets += 1
            return self._num_buckets

    def remove_bucket(self) -> int:
        """Remove the **last** bucket; return the new count. Raises if only one remains."""
        with self._lock:
            if self._num_buckets <= 1:
                raise JumpHashError("cannot remove the last bucket")
            self._num_buckets -= 1
            return self._num_buckets

    def reset(self, num_buckets: int | None = None, seed: int | None = None) -> None:
        """Optionally reconfigure ``num_buckets`` / ``seed``."""
        with self._lock:
            if num_buckets is not None:
                if not _is_pos_int(num_buckets):
                    raise JumpHashError(num_buckets)
                self._num_buckets = num_buckets
            if seed is not None:
                if not _is_int(seed):
                    raise JumpHashError(seed)
                self._seed = seed

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def num_buckets(self) -> int:
        with self._lock:
            return self._num_buckets

    @property
    def seed(self) -> int:
        return self._seed

    def load_distribution(self, keys: Any) -> dict:
        """Count how many of ``keys`` land in each bucket (diagnostic)."""
        with self._lock:
            n = self._num_buckets
            dist = {i: 0 for i in range(n)}
            for key in keys:
                dist[jump_consistent_hash(self._key_hash(key), n)] += 1
            return dist

    def stats(self) -> dict:
        """Summary: ``num_buckets`` / ``seed``."""
        with self._lock:
            return {"num_buckets": self._num_buckets, "seed": self._seed}
