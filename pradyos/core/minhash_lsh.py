"""Phase 115 — Sovereign MinHash LSH (Indyk & Motwani, 1998; Broder, 1997).

**Locality-sensitive hashing** over MinHash signatures — a *similarity-search index*
for fast approximate near-duplicate / nearest-neighbour retrieval over sets. The
platform already *estimates* set similarity (MinHash/P88, SimHash/P89); LSH turns that
into an **index** answering "which stored sets are similar to this query set?" in
sublinear time.

Each item's token set is reduced to a **MinHash signature** of ``k = bands·rows``
values: with universal hashing ``h_i(t) = (a_i·base(t) + b_i) mod p`` (``p = 2⁶¹−1``,
seeded coefficients), ``signature[i] = min_t h_i(t)``. Two sets agree on a given
signature position with probability equal to their **Jaccard similarity** ``s``, so the
mean agreement over the ``k`` positions is an unbiased estimate of ``s``.

The signature is split into ``bands`` **bands** of ``rows`` consecutive values; an item
is indexed into a per-band bucket keyed by that band's whole ``rows``-tuple. Two items
land in the same bucket of a band iff their signatures agree on *every* row of it
(probability ``s^rows``), so they share **at least one** band — and become query
candidates — with probability ``1 − (1 − s^rows)^bands``. That is the classic LSH
**S-curve**: a sharp threshold near ``(1/bands)^(1/rows)`` below which dissimilar items
rarely collide and above which similar items almost always do. ``query`` gathers the
candidates sharing any band bucket, then refines them by the signature-agreement
estimate and returns those at or above a similarity threshold.

Fully deterministic given the seed (universal-hash coefficients are seeded; results are
sorted by estimated similarity then by stringified id, so output never depends on set
iteration order). Pure stdlib (``hashlib`` + ``random`` for the seeded coefficients);
thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import random
import threading
from typing import Any

_PRIME = (1 << 61) - 1  # Mersenne prime 2^61 - 1 (universal hashing modulus)


class MinHashLSHError(Exception):
    """Raised for an invalid MinHash-LSH operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _base_hash(token: Any) -> int:
    """Stable 64-bit fold of a token into ``[0, PRIME)`` (process-independent)."""
    digest = hashlib.blake2b(repr(token).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % _PRIME


class MinHashLSH:
    """Banded MinHash LSH index for sublinear approximate similarity search."""

    def __init__(self, bands: int = 16, rows: int = 4, seed: int = 0) -> None:
        self._validate(bands, rows, seed)
        self._bands = bands
        self._rows = rows
        self._k = bands * rows
        self._seed = seed
        self._lock = threading.Lock()
        self._configure()

    @staticmethod
    def _validate(bands: Any, rows: Any, seed: Any) -> None:
        if not _is_pos_int(bands):
            raise MinHashLSHError(bands)
        if not _is_pos_int(rows):
            raise MinHashLSHError(rows)
        if not _is_int(seed):
            raise MinHashLSHError(seed)

    def _configure(self) -> None:
        rng = random.Random(self._seed)
        self._a = [rng.randrange(1, _PRIME) for _ in range(self._k)]
        self._b = [rng.randrange(0, _PRIME) for _ in range(self._k)]
        self._buckets: list[dict[tuple, set]] = [{} for _ in range(self._bands)]
        self._sigs: dict[Any, tuple] = {}

    # ── signature (pure) ─────────────────────────────────────────────────────────────
    def _signature(self, tokens: Any) -> tuple:
        try:
            bases = {_base_hash(t) for t in tokens}
        except TypeError as exc:
            raise MinHashLSHError("tokens must be an iterable of hashable items") from exc
        if not bases:
            return tuple([_PRIME] * self._k)  # empty set → max signature
        a, b = self._a, self._b
        return tuple(min((a[i] * base + b[i]) % _PRIME for base in bases) for i in range(self._k))

    def _band_key(self, sig: tuple, band_idx: int) -> tuple:
        start = band_idx * self._rows
        return sig[start : start + self._rows]

    # ── mutation ──────────────────────────────────────────────────────────────────────
    def insert(self, item_id: Any, tokens: Any) -> None:
        """Index ``item_id`` by the MinHash signature of its ``tokens`` set.

        Re-inserting an existing id replaces its prior signature/buckets."""
        sig = self._signature(tokens)
        with self._lock:
            if item_id in self._sigs:
                self._remove_locked(item_id)
            self._sigs[item_id] = sig
            for bi in range(self._bands):
                self._buckets[bi].setdefault(self._band_key(sig, bi), set()).add(item_id)

    def remove(self, item_id: Any) -> bool:
        """Remove ``item_id`` from the index; return True if it was present."""
        with self._lock:
            if item_id not in self._sigs:
                return False
            self._remove_locked(item_id)
            return True

    def _remove_locked(self, item_id: Any) -> None:
        sig = self._sigs.pop(item_id)
        for bi in range(self._bands):
            key = self._band_key(sig, bi)
            bucket = self._buckets[bi].get(key)
            if bucket is not None:
                bucket.discard(item_id)
                if not bucket:
                    del self._buckets[bi][key]

    def reset(
        self, bands: int | None = None, rows: int | None = None, seed: int | None = None
    ) -> None:
        """Clear the index; optionally reconfigure ``bands`` / ``rows`` / ``seed``."""
        with self._lock:
            nb = self._bands if bands is None else bands
            nr = self._rows if rows is None else rows
            ns = self._seed if seed is None else seed
            self._validate(nb, nr, ns)
            self._bands, self._rows, self._seed = nb, nr, ns
            self._k = nb * nr
            self._configure()

    # ── query ─────────────────────────────────────────────────────────────────────────
    def query(self, tokens: Any, threshold: float = 0.0) -> list[tuple[Any, float]]:
        """Return ``[(item_id, similarity), ...]`` for indexed items sharing a band
        bucket with the query and estimated to be at least ``threshold`` similar,
        sorted by descending similarity (ties broken by stringified id)."""
        if not _is_number(threshold) or not (0.0 <= threshold <= 1.0):
            raise MinHashLSHError(threshold)
        sig = self._signature(tokens)
        with self._lock:
            candidates: set = set()
            for bi in range(self._bands):
                bucket = self._buckets[bi].get(self._band_key(sig, bi))
                if bucket:
                    candidates |= bucket
            k = self._k
            results = []
            for cid in candidates:
                csig = self._sigs[cid]
                est = sum(1 for x, y in zip(sig, csig, strict=False) if x == y) / k
                if est >= threshold:
                    results.append((cid, est))
        results.sort(key=lambda p: (-p[1], str(p[0])))
        return results

    def similarity(self, tokens_a: Any, tokens_b: Any) -> float:
        """Estimated Jaccard similarity of two token sets (signature agreement)."""
        sa = self._signature(tokens_a)
        sb = self._signature(tokens_b)
        return sum(1 for x, y in zip(sa, sb, strict=False) if x == y) / self._k

    # ── introspection ──────────────────────────────────────────────────────────────────
    def contains(self, item_id: Any) -> bool:
        with self._lock:
            return item_id in self._sigs

    def __contains__(self, item_id: Any) -> bool:
        return self.contains(item_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sigs)

    def threshold_estimate(self) -> float:
        """The LSH S-curve inflection point ``(1/bands)^(1/rows)``."""
        return (1.0 / self._bands) ** (1.0 / self._rows)

    @property
    def bands(self) -> int:
        return self._bands

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def num_perm(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``num_items`` / ``bands`` / ``rows`` / ``num_perm`` (k) /
        ``threshold_estimate`` / ``seed``."""
        with self._lock:
            return {
                "num_items": len(self._sigs),
                "bands": self._bands,
                "rows": self._rows,
                "num_perm": self._k,
                "threshold_estimate": round(self.threshold_estimate(), 6),
                "seed": self._seed,
            }
