"""Phase 117 — Sovereign HyperMinHash (Yu & Weber, 2017 — *MinHash in LogLog space*).

A single compact sketch that estimates **both cardinality and Jaccard similarity**
(hence union and intersection sizes) — where the platform otherwise keeps those
separate (HyperLogLog/P74 & Theta/P93 for cardinality; MinHash/P88 for similarity).

Each element is hashed to 64 bits: the top ``p`` bits choose one of ``m = 2^p``
**buckets**, and the remaining ``w = 64 − p`` bits supply two things — a HyperLogLog
**rank** (``leading_zeros + 1`` of those bits) and an ``r``-bit **mantissa** (their low
``r`` bits). Because the element with the *smallest* remaining hash has the *most*
leading zeros, "keep the bucket minimum" and "keep the bucket's HLL maximum rank"
coincide; each bucket therefore stores the ``(rank, mantissa)`` of its extremal element
(max rank; ties broken by min mantissa — a rule that is order-independent and
**mergeable** by bucketwise max-rank/min-mantissa).

* **Cardinality** uses only the ranks: the standard HyperLogLog estimator
  ``α_m·m² / Σ 2^(−rank)`` with the small-range linear-counting correction.
* **Jaccard** counts buckets where two sketches agree on *both* rank and mantissa.
  The raw agreement rate is ``J + (1−J)·C`` where ``C`` is the chance two *different*
  extremal elements coincidentally share ``(rank, mantissa)``; ``C`` is estimated from
  the union sketch's rank histogram as ``(Σ_k q_k²)·2^(−r)`` and removed:
  ``Ĵ = (agree_rate − C) / (1 − C)``. The mantissa makes ``C`` tiny, so — unlike plain
  MinHash — the estimate stays accurate even at very low similarity, in little space.

Mergeable (bucketwise max rank, keep the surviving rank's mantissa). Fully deterministic
given the seed. Pure stdlib (``hashlib``); thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

_MASK64 = (1 << 64) - 1


class HyperMinHashError(Exception):
    """Raised for an invalid HyperMinHash operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _alpha(m: int) -> float:
    if m == 16:
        return 0.673
    if m == 32:
        return 0.697
    if m == 64:
        return 0.709
    return 0.7213 / (1.0 + 1.079 / m)


class HyperMinHash:
    """Joint cardinality + Jaccard sketch (HyperLogLog rank + r-bit MinHash mantissa)."""

    def __init__(self, p: int = 8, r: int = 8, seed: int = 0) -> None:
        if not _is_int(p) or p < 4 or p > 20:
            raise HyperMinHashError(p)
        if not _is_int(r) or r < 1 or r > 8:
            raise HyperMinHashError(r)
        if not _is_int(seed):
            raise HyperMinHashError(seed)
        self._p = p
        self._r = r
        self._seed = seed
        self._m = 1 << p
        self._w = 64 - p  # bits available for rank + mantissa
        self._lock = threading.Lock()
        self._init_state()

    def _init_state(self) -> None:
        self._ranks = bytearray(self._m)  # 0 == empty bucket
        self._mantissas = bytearray(self._m)

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _hash64(self, element: Any) -> int:
        data = repr((self._seed, element)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")

    def _bucket_rank_mantissa(self, element: Any) -> tuple[int, int, int]:
        h = self._hash64(element)
        bucket = h >> self._w  # top p bits
        rest = h & ((1 << self._w) - 1)  # low w bits
        lz = self._w - rest.bit_length()  # leading zeros within w bits
        rank = lz + 1  # 1..w+1 (w+1 only when rest == 0)
        mantissa = rest & ((1 << self._r) - 1)
        return bucket, rank, mantissa

    # ── mutation ──────────────────────────────────────────────────────────────────────
    def add(self, element: Any) -> None:
        """Add ``element`` to the sketch."""
        with self._lock:
            bucket, rank, mantissa = self._bucket_rank_mantissa(element)
            self._update(bucket, rank, mantissa)

    def _update(self, bucket: int, rank: int, mantissa: int) -> None:
        cur = self._ranks[bucket]
        if rank > cur or (rank == cur and mantissa < self._mantissas[bucket]):
            self._ranks[bucket] = rank
            self._mantissas[bucket] = mantissa

    def add_many(self, elements: Any) -> None:
        try:
            iterator = iter(elements)
        except TypeError as exc:
            raise HyperMinHashError(elements) from exc
        with self._lock:
            for element in iterator:
                bucket, rank, mantissa = self._bucket_rank_mantissa(element)
                self._update(bucket, rank, mantissa)

    # ── cardinality (HyperLogLog estimator) ───────────────────────────────────────────
    def cardinality(self) -> float:
        """Estimated number of distinct elements added (HyperLogLog on the ranks)."""
        with self._lock:
            return self._cardinality_locked(self._ranks)

    def _cardinality_locked(self, ranks: bytearray) -> float:
        m = self._m
        inv_sum = 0.0
        zeros = 0
        for reg in ranks:
            inv_sum += 2.0 ** (-reg)  # empty (reg 0) contributes 1.0
            if reg == 0:
                zeros += 1
        estimate = _alpha(m) * m * m / inv_sum
        if estimate <= 2.5 * m and zeros > 0:  # small-range linear-counting correction
            return m * math.log(m / zeros)
        return estimate

    # ── similarity ─────────────────────────────────────────────────────────────────────
    def _check_compatible(self, other: HyperMinHash) -> None:
        if not isinstance(other, HyperMinHash):
            raise HyperMinHashError("other must be a HyperMinHash")
        if other._p != self._p or other._r != self._r or other._seed != self._seed:
            raise HyperMinHashError("incompatible sketches (p / r / seed differ)")

    def jaccard(self, other: HyperMinHash) -> float:
        """Estimated Jaccard similarity with ``other`` (collision-corrected agreement)."""
        self._check_compatible(other)
        with self._lock, other._lock:
            ra, rb = self._ranks, other._ranks
            ma, mb = self._mantissas, other._mantissas
            m = self._m
            agree = 0
            both = 0
            hist_a: dict[int, int] = {}
            hist_b: dict[int, int] = {}
            for i in range(m):
                ea, eb = ra[i] > 0, rb[i] > 0
                if ea:
                    hist_a[ra[i]] = hist_a.get(ra[i], 0) + 1
                if eb:
                    hist_b[rb[i]] = hist_b.get(rb[i], 0) + 1
                if ea and eb:
                    both += 1
                    if ra[i] == rb[i] and ma[i] == mb[i]:
                        agree += 1
            if both == 0:
                return 0.0
            agree_rate = agree / both
            # Expected random-collision rate: two independent winners share a rank with
            # probability Σ_k P_A(k)·P_B(k) (each from its OWN rank distribution), and the
            # r-bit mantissa then coincides with probability 2^-r.
            na = sum(hist_a.values())
            nb = sum(hist_b.values())
            if na == 0 or nb == 0:
                return 0.0
            same_rank = sum((hist_a[k] / na) * (hist_b.get(k, 0) / nb) for k in hist_a)
            c = same_rank * (2.0 ** (-self._r))
            if c >= 1.0:
                return 0.0
            est = (agree_rate - c) / (1.0 - c)
            return min(1.0, max(0.0, est))

    def merge(self, other: HyperMinHash) -> HyperMinHash:
        """Return a new sketch for the union (bucketwise max rank / min mantissa)."""
        self._check_compatible(other)
        out = HyperMinHash(p=self._p, r=self._r, seed=self._seed)
        with self._lock, other._lock:
            ra, rb = self._ranks, other._ranks
            ma, mb = self._mantissas, other._mantissas
            for i in range(self._m):
                if ra[i] > rb[i]:
                    out._ranks[i], out._mantissas[i] = ra[i], ma[i]
                elif rb[i] > ra[i]:
                    out._ranks[i], out._mantissas[i] = rb[i], mb[i]
                elif ra[i] > 0:  # equal rank → keep min mantissa
                    out._ranks[i] = ra[i]
                    out._mantissas[i] = ma[i] if ma[i] <= mb[i] else mb[i]
        return out

    def union_cardinality(self, other: HyperMinHash) -> float:
        """Estimated cardinality of the union."""
        return self.merge(other).cardinality()

    def intersection_cardinality(self, other: HyperMinHash) -> float:
        """Estimated cardinality of the intersection (Jaccard × union)."""
        return self.jaccard(other) * self.union_cardinality(other)

    # ── introspection ──────────────────────────────────────────────────────────────────
    def reset(self, p: int | None = None, r: int | None = None, seed: int | None = None) -> None:
        """Clear the sketch; optionally reconfigure ``p`` / ``r`` / ``seed``."""
        with self._lock:
            np_ = self._p if p is None else p
            nr = self._r if r is None else r
            ns = self._seed if seed is None else seed
            if not _is_int(np_) or np_ < 4 or np_ > 20:
                raise HyperMinHashError(np_)
            if not _is_int(nr) or nr < 1 or nr > 8:
                raise HyperMinHashError(nr)
            if not _is_int(ns):
                raise HyperMinHashError(ns)
            self._p, self._r, self._seed = np_, nr, ns
            self._m = 1 << np_
            self._w = 64 - np_
            self._init_state()

    @property
    def p(self) -> int:
        return self._p

    @property
    def r(self) -> int:
        return self._r

    @property
    def num_buckets(self) -> int:
        return self._m

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``p`` / ``r`` / ``num_buckets`` / ``filled`` / ``cardinality`` / ``seed``."""
        with self._lock:
            filled = sum(1 for x in self._ranks if x > 0)
            return {
                "p": self._p,
                "r": self._r,
                "num_buckets": self._m,
                "filled": filled,
                "cardinality": self._cardinality_locked(self._ranks),
                "seed": self._seed,
            }
