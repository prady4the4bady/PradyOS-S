"""Phase 126 — Sovereign Cosine / Random-Hyperplane LSH (Charikar, 2002; Indyk & Motwani, 1998).

A **similarity-search index for cosine similarity over vectors** — the cosine counterpart
to the platform's MinHash-LSH (P115, which indexes *Jaccard* over sets), and the *indexed
search* that the SimHash estimator (P89) lacks.

Each item vector is reduced to a `k`-bit **SimHash** signature by ``k`` random hyperplanes:
bit ``i`` is the sign of the vector's dot product with hyperplane ``i`` (1 if ``≥ 0`` else
0). Two vectors at angle ``θ`` agree on a given bit with probability ``1 − θ/π`` — the
random-hyperplane LSH property — so the fraction of matching bits estimates the angle, and
``cos(π·(1 − bit_agreement))`` estimates their cosine similarity.

The signature is split into ``bands`` bands of ``rows`` bits (``k = bands·rows``) and
bucketed per band; two vectors collide in a band iff they match **every** bit of it,
giving the tunable LSH S-curve — now over *angular* distance. ``query(vector)`` gathers the
candidates sharing any band bucket and refines them by estimated cosine similarity,
returning those at/above a threshold (sorted by descending similarity).

A *different* index from MinHash-LSH/P115 (min-hashes over sets) — random hyperplanes over
real vectors. The hyperplanes are drawn from a seeded ``random.Random`` (standard-normal
components), so the index is deterministic and reproducible. Pure stdlib; thread-safe via a
single ``threading.Lock``.
"""

from __future__ import annotations

import math
import random
import threading
from typing import Any


class SimHashLSHError(Exception):
    """Raised for an invalid SimHash-LSH operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class SimHashLSH:
    """Random-hyperplane (cosine) LSH index for approximate angular similarity search."""

    def __init__(self, dim: int = 64, bands: int = 16, rows: int = 4, seed: int = 0) -> None:
        self._validate(dim, bands, rows, seed)
        self._dim = dim
        self._bands = bands
        self._rows = rows
        self._k = bands * rows
        self._seed = seed
        self._lock = threading.Lock()
        self._configure()

    @staticmethod
    def _validate(dim: Any, bands: Any, rows: Any, seed: Any) -> None:
        if not _is_pos_int(dim):
            raise SimHashLSHError(dim)
        if not _is_pos_int(bands):
            raise SimHashLSHError(bands)
        if not _is_pos_int(rows):
            raise SimHashLSHError(rows)
        if not _is_int(seed):
            raise SimHashLSHError(seed)

    def _configure(self) -> None:
        rng = random.Random(self._seed)
        # k random hyperplanes, each a dim-vector of standard-normal components.
        self._planes = [[rng.gauss(0.0, 1.0) for _ in range(self._dim)] for _ in range(self._k)]
        self._buckets: list[dict[tuple, set]] = [{} for _ in range(self._bands)]
        self._sigs: dict[Any, tuple] = {}

    # ── signature (pure) ─────────────────────────────────────────────────────────────
    def _check_vector(self, vector: Any) -> list:
        try:
            vec = list(vector)
        except TypeError as exc:
            raise SimHashLSHError("vector must be a sequence") from exc
        if len(vec) != self._dim:
            raise SimHashLSHError(f"vector must have dimension {self._dim}")
        if not all(_is_number(x) for x in vec):
            raise SimHashLSHError("vector components must be numbers")
        return vec

    def _signature(self, vec: list) -> tuple:
        planes = self._planes
        return tuple(
            1 if sum(vec[j] * planes[i][j] for j in range(self._dim)) >= 0.0 else 0
            for i in range(self._k)
        )

    def _band_key(self, sig: tuple, band_idx: int) -> tuple:
        start = band_idx * self._rows
        return sig[start : start + self._rows]

    @staticmethod
    def _cosine_from_agreement(sig_a: tuple, sig_b: tuple, k: int) -> float:
        agree = sum(1 for x, y in zip(sig_a, sig_b, strict=False) if x == y) / k
        return math.cos(math.pi * (1.0 - agree))

    # ── mutation ──────────────────────────────────────────────────────────────────────
    def insert(self, item_id: Any, vector: Any) -> None:
        """Index ``item_id`` by the SimHash signature of its ``vector``."""
        vec = self._check_vector(vector)
        with self._lock:
            sig = self._signature(vec)
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
        self,
        dim: int | None = None,
        bands: int | None = None,
        rows: int | None = None,
        seed: int | None = None,
    ) -> None:
        """Clear the index; optionally reconfigure ``dim`` / ``bands`` / ``rows`` / ``seed``."""
        with self._lock:
            nd = self._dim if dim is None else dim
            nb = self._bands if bands is None else bands
            nr = self._rows if rows is None else rows
            ns = self._seed if seed is None else seed
            self._validate(nd, nb, nr, ns)
            self._dim, self._bands, self._rows, self._seed = nd, nb, nr, ns
            self._k = nb * nr
            self._configure()

    # ── query ─────────────────────────────────────────────────────────────────────────
    def query(self, vector: Any, threshold: float = 0.0) -> list[tuple[Any, float]]:
        """Return ``[(item_id, cosine), ...]`` for indexed items sharing a band bucket with
        the query and estimated to be at least ``threshold`` cosine-similar, sorted by
        descending similarity (ties broken by stringified id)."""
        if not (_is_number(threshold) and -1.0 <= threshold <= 1.0):
            raise SimHashLSHError(threshold)
        vec = self._check_vector(vector)
        with self._lock:
            sig = self._signature(vec)
            candidates: set = set()
            for bi in range(self._bands):
                bucket = self._buckets[bi].get(self._band_key(sig, bi))
                if bucket:
                    candidates |= bucket
            k = self._k
            results = []
            for cid in candidates:
                est = self._cosine_from_agreement(sig, self._sigs[cid], k)
                if est >= threshold:
                    results.append((cid, est))
        results.sort(key=lambda p: (-p[1], str(p[0])))
        return results

    def similarity(self, vector_a: Any, vector_b: Any) -> float:
        """Estimated cosine similarity of two vectors (random-hyperplane bit agreement)."""
        va = self._check_vector(vector_a)
        vb = self._check_vector(vector_b)
        with self._lock:
            return self._cosine_from_agreement(self._signature(va), self._signature(vb), self._k)

    # ── introspection ──────────────────────────────────────────────────────────────────
    def contains(self, item_id: Any) -> bool:
        with self._lock:
            return item_id in self._sigs

    def __contains__(self, item_id: Any) -> bool:
        return self.contains(item_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sigs)

    @property
    def dim(self) -> int:
        return self._dim

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
        """Summary: ``num_items`` / ``dim`` / ``bands`` / ``rows`` / ``num_perm`` (k) / ``seed``."""
        with self._lock:
            return {
                "num_items": len(self._sigs),
                "dim": self._dim,
                "bands": self._bands,
                "rows": self._rows,
                "num_perm": self._k,
                "seed": self._seed,
            }
