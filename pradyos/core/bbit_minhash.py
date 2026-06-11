"""Phase 122 — Sovereign b-bit MinHash (Li & König, 2010 — *b-bit minwise hashing*).

A **space-compressed** similarity sketch. The platform's MinHash (P88) stores ``k`` full
64-bit minimum-hash values per set; b-bit MinHash keeps only the **lowest ``b`` bits** of
each (often ``b = 1`` or ``2``), shrinking a signature by ``~b/64×`` while preserving
Jaccard accuracy through a **bias-corrected estimator**.

For ``k`` independent hash permutations, ``signature[i]`` is the low ``b`` bits of the
minimum hash over the set's elements. Two sets of Jaccard similarity ``J`` agree on a
given full minimum with probability ``J``; when they *do* agree the low ``b`` bits agree,
and when they *don't* (prob ``1 − J``) the low bits still coincide by chance with
probability ``C = 2^(−b)``. Hence the observed agreement rate is

    match_rate = J + (1 − J)·C        ⇒        Ĵ = (match_rate − C) / (1 − C).

A larger ``b`` shrinks ``C`` (less correction, lower variance) toward full MinHash; a
smaller ``b`` saves more space at the cost of variance. This is a *different* algorithm
from MinHash/P88 (full signatures) and MinHash-LSH/P115 (a banded nearest-neighbour
index): it is the compact estimator you store or transmit at scale.

Internally the builder keeps the full running minimums (needed to fold elements
incrementally); :meth:`signature` exposes the compact ``b``-bit form, and
:meth:`jaccard` / :func:`estimate_jaccard` compare two signatures with the correction.
Universal hashing ``(a_i·x + b_i) mod (2⁶¹ − 1)`` with seeded coefficients makes results
deterministic. Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import random
import threading
from typing import Any

_PRIME = (1 << 61) - 1


class BBitMinHashError(Exception):
    """Raised for an invalid b-bit MinHash operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _base_hash(item: Any) -> int:
    return (
        int.from_bytes(hashlib.blake2b(repr(item).encode("utf-8"), digest_size=8).digest(), "big")
        % _PRIME
    )


def estimate_jaccard(sig_a: Any, sig_b: Any, b: int) -> float:
    """Bias-corrected Jaccard estimate from two ``b``-bit signatures of equal length."""
    if not _is_pos_int(b) or b > 32:
        raise BBitMinHashError(b)
    a = list(sig_a)
    bb = list(sig_b)
    if len(a) != len(bb) or not a:
        raise BBitMinHashError("signatures must be non-empty and equal length")
    match_rate = sum(1 for x, y in zip(a, bb, strict=False) if x == y) / len(a)
    c = 2.0 ** (-b)
    est = (match_rate - c) / (1.0 - c)
    return min(1.0, max(0.0, est))


class BBitMinHash:
    """Compressed MinHash signature (low ``b`` bits per permutation) with corrected Jaccard."""

    def __init__(self, num_perm: int = 128, b: int = 2, seed: int = 0) -> None:
        if not _is_pos_int(num_perm):
            raise BBitMinHashError(num_perm)
        if not _is_pos_int(b) or b > 32:
            raise BBitMinHashError(b)
        if not _is_int(seed):
            raise BBitMinHashError(seed)
        self._k = num_perm
        self._b = b
        self._mask = (1 << b) - 1
        self._seed = seed
        self._lock = threading.Lock()
        self._configure()

    def _configure(self) -> None:
        rng = random.Random(self._seed)
        self._a = [rng.randrange(1, _PRIME) for _ in range(self._k)]
        self._b_coef = [rng.randrange(0, _PRIME) for _ in range(self._k)]
        self._mins = [_PRIME] * self._k  # full running minimums (max sentinel)
        self._count = 0

    # ── mutation ──────────────────────────────────────────────────────────────────────
    def add(self, item: Any) -> None:
        """Fold ``item`` into the running minimums."""
        with self._lock:
            self._add_locked(item)
            self._count += 1

    def _add_locked(self, item: Any) -> None:
        base = _base_hash(item)
        a, bc, mins = self._a, self._b_coef, self._mins
        for i in range(self._k):
            h = (a[i] * base + bc[i]) % _PRIME
            if h < mins[i]:
                mins[i] = h

    def add_many(self, items: Any) -> None:
        try:
            iterator = iter(items)
        except TypeError as exc:
            raise BBitMinHashError(items) from exc
        with self._lock:
            for item in iterator:
                self._add_locked(item)
                self._count += 1

    # ── signature & similarity ─────────────────────────────────────────────────────────
    def signature(self) -> tuple:
        """The compact ``b``-bit signature (low ``b`` bits of each running minimum)."""
        with self._lock:
            return tuple(m & self._mask for m in self._mins)

    def jaccard(self, other: BBitMinHash) -> float:
        """Bias-corrected Jaccard estimate against another compatible sketch."""
        if not isinstance(other, BBitMinHash):
            raise BBitMinHashError("other must be a BBitMinHash")
        if other._k != self._k or other._b != self._b or other._seed != self._seed:
            raise BBitMinHashError("incompatible sketches (num_perm / b / seed differ)")
        return estimate_jaccard(self.signature(), other.signature(), self._b)

    def reset(
        self, num_perm: int | None = None, b: int | None = None, seed: int | None = None
    ) -> None:
        """Clear the sketch; optionally reconfigure ``num_perm`` / ``b`` / ``seed``."""
        with self._lock:
            nk = self._k if num_perm is None else num_perm
            nb = self._b if b is None else b
            ns = self._seed if seed is None else seed
            if not _is_pos_int(nk):
                raise BBitMinHashError(nk)
            if not _is_pos_int(nb) or nb > 32:
                raise BBitMinHashError(nb)
            if not _is_int(ns):
                raise BBitMinHashError(ns)
            self._k, self._b, self._seed = nk, nb, ns
            self._mask = (1 << nb) - 1
            self._configure()

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        with self._lock:
            return self._count

    @property
    def num_perm(self) -> int:
        return self._k

    @property
    def b(self) -> int:
        return self._b

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def signature_bits(self) -> int:
        """Total bits in the compact signature (``num_perm · b``)."""
        return self._k * self._b

    def stats(self) -> dict:
        """Summary: ``num_perm`` (k) / ``b`` / ``count`` / ``signature_bits`` / ``seed``."""
        with self._lock:
            return {
                "num_perm": self._k,
                "b": self._b,
                "count": self._count,
                "signature_bits": self._k * self._b,
                "seed": self._seed,
            }
