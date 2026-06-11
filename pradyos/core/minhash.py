"""Phase 88 — Sovereign MinHash.

Estimates the **Jaccard similarity** ``|A ∩ B| / |A ∪ B|`` of two sets in compact
O(num_hashes) space, without ever storing the raw members. For each of
``num_hashes`` independent hash functions ``h_i`` we keep, per named set, the
*minimum* hashed value seen across that set's members — its "signature". A core
property of min-wise hashing is that ``P[min_i(A) == min_i(B)] == Jaccard(A, B)``,
so the **fraction of signature positions where two sets agree is an unbiased
estimate of their Jaccard similarity** (variance ∝ 1/num_hashes).

The hash family is universal: ``h_i(x) = (a_i · x + b_i) mod p`` with ``p`` the
Mersenne prime ``2**61 − 1`` and the coefficients ``(a_i, b_i)`` drawn once at
init from a seeded RNG — so two instances built with the same ``num_hashes`` and
``seed`` produce comparable signatures, and everything is deterministic for tests.
Each member is first folded to a 64-bit integer with a stable BLAKE2b digest
(*not* the salted built-in ``hash``), so determinism holds across processes.

Design note: a literal ``… mod p mod num_hashes`` (as sometimes sketched) would
collapse every hash into ``[0, num_hashes)``, making set minima collide at 0 and
inflating every estimate toward 1.0 — it breaks the estimator. We therefore keep
the full ``mod p`` range; this is the standard, accuracy-preserving construction
(empirically validated before the tests were written).

This object is a multi-set store: it owns the shared hash family plus one
signature per named set, so ``add(name, element)`` updates a set in place and
``similarity(a, b)`` compares two stored signatures. Pure stdlib. Thread-safe via
a single ``threading.Lock``; internal ``_locked`` helpers never re-acquire it.
"""

from __future__ import annotations

import hashlib
import random
import threading
from collections.abc import Iterable
from typing import Any

_MERSENNE = (1 << 61) - 1  # 2**61 - 1, a Mersenne prime — the hash modulus p


class MinHashError(Exception):
    """Raised for an invalid MinHash configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid minhash configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _base_int(element: Any) -> int:
    """Fold an arbitrary element to a stable 64-bit integer (process-independent)."""
    data = repr(element).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


class MinHash:
    """Multi-set MinHash store: shared universal hash family + per-set signatures."""

    def __init__(self, num_hashes: int = 128, seed: int = 0) -> None:
        if not _is_pos_int(num_hashes):
            raise MinHashError(num_hashes)
        if not _is_int(seed):
            raise MinHashError(seed)
        self._k = num_hashes
        self._seed = seed
        self._coeffs = self._make_coeffs(num_hashes, seed)
        self._sets: dict[str, list[int]] = {}  # set name -> signature (length k)
        self._total = 0
        self._lock = threading.Lock()

    @staticmethod
    def _make_coeffs(k: int, seed: int) -> list[tuple[int, int]]:
        rnd = random.Random(seed)
        return [(rnd.randrange(1, _MERSENNE), rnd.randrange(0, _MERSENNE)) for _ in range(k)]

    # ── internal helpers (run under the lock; never re-acquire) ──────────────────
    def _hashes(self, element: Any) -> list[int]:
        x = _base_int(element)
        return [(a * x + b) % _MERSENNE for (a, b) in self._coeffs]

    def _add_locked(self, name: str, element: Any) -> None:
        h = self._hashes(element)
        sig = self._sets.get(name)
        if sig is None:
            self._sets[name] = h  # first member initialises the signature
        else:
            for i in range(self._k):
                if h[i] < sig[i]:
                    sig[i] = h[i]  # element-wise running minimum
        self._total += 1

    # ── mutation ─────────────────────────────────────────────────────────────────
    def add(self, set_name: Any, element: Any) -> None:
        """Add ``element`` to the named set, updating its signature in place."""
        with self._lock:
            self._add_locked(str(set_name), element)

    def add_many(self, set_name: Any, elements: Iterable[Any]) -> int:
        """Add every element to the named set; return how many were added."""
        with self._lock:
            name = str(set_name)
            n = 0
            for element in elements:
                self._add_locked(name, element)
                n += 1
            return n

    def reset(self, num_hashes: int | None = None, seed: int | None = None) -> None:
        """Clear all stored signatures; optionally reconfigure ``num_hashes`` / ``seed``."""
        with self._lock:
            if num_hashes is not None:
                if not _is_pos_int(num_hashes):
                    raise MinHashError(num_hashes)
                self._k = num_hashes
            if seed is not None:
                if not _is_int(seed):
                    raise MinHashError(seed)
                self._seed = seed
            if num_hashes is not None or seed is not None:
                self._coeffs = self._make_coeffs(self._k, self._seed)
            self._sets = {}
            self._total = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def similarity(self, set_a: Any, set_b: Any) -> float:
        """Estimated Jaccard similarity of two named sets (0.0 if either is unknown)."""
        with self._lock:
            sa = self._sets.get(str(set_a))
            sb = self._sets.get(str(set_b))
            if sa is None or sb is None:
                return 0.0
            agree = sum(1 for i in range(self._k) if sa[i] == sb[i])
            return agree / self._k

    def signature(self, set_name: Any) -> list[int] | None:
        """A copy of the named set's signature, or ``None`` if it is unknown."""
        with self._lock:
            sig = self._sets.get(str(set_name))
            return list(sig) if sig is not None else None

    def sets(self) -> list[str]:
        """Sorted names of all stored sets."""
        with self._lock:
            return sorted(self._sets)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sets)

    def __contains__(self, set_name: Any) -> bool:
        with self._lock:
            return str(set_name) in self._sets

    @property
    def num_hashes(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``num_hashes``, number of ``sets``, ``total_added`` observations, ``seed``."""
        with self._lock:
            return {
                "num_hashes": self._k,
                "sets": len(self._sets),
                "total_added": self._total,
                "seed": self._seed,
            }
