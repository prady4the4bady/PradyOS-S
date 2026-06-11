"""Phase 127 — Sovereign Random Projection / Johnson–Lindenstrauss sketch (Johnson & Lindenstrauss, 1984; Achlioptas, 2001).

A **distance-preserving dimensionality-reduction** sketch — a new capability for the
platform. It multiplies each ``d``-dimensional input vector by a fixed random ``k × d``
matrix ``R`` (``k ≪ d``) to produce a ``k``-dimensional sketch. The **Johnson–Lindenstrauss
lemma** guarantees that with ``k = O(ln n / ε²)`` *all* pairwise Euclidean distances (and
dot products) are preserved within a ``(1 ± ε)`` factor with high probability — so
similarity search, clustering and nearest-neighbour work on the small sketches.

The matrix uses **Rademacher** entries ``±1/√k`` (each sign with probability ½); since the
entries are zero-mean and unit-variance after scaling, ``E[‖Rx‖²] = ‖x‖²`` and
``E[⟨Rx, Ry⟩] = ⟨x, y⟩`` — the projection is an *unbiased* isometry in expectation, and the
JL concentration bounds make it tight for the whole point set at once. (Achlioptas's
database-friendly ``{+1, 0, −1}`` variant is the sparse cousin of the same idea.)

This is *different* from the platform's hashing-based sketches (MinHash/SimHash/LSH), which
preserve a single similarity measure: random projection preserves the *geometry* of the
original space — every distance and angle at once — in a dense real sketch. Exposes
``project``, plus ``distance`` and ``dot`` estimators that operate via the projection. The
random matrix is drawn from a seeded ``random.Random`` so projections are reproducible.
Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import math
import random
import threading
from typing import Any


class RandomProjectionError(Exception):
    """Raised for an invalid Random-Projection operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class RandomProjection:
    """Johnson–Lindenstrauss random-projection sketch (distance-preserving)."""

    def __init__(self, input_dim: int = 128, output_dim: int = 16, seed: int = 0) -> None:
        self._validate(input_dim, output_dim, seed)
        self._d = input_dim
        self._k = output_dim
        self._seed = seed
        self._lock = threading.Lock()
        self._configure()

    @staticmethod
    def _validate(input_dim: Any, output_dim: Any, seed: Any) -> None:
        if not _is_pos_int(input_dim):
            raise RandomProjectionError(input_dim)
        if not _is_pos_int(output_dim):
            raise RandomProjectionError(output_dim)
        if not _is_int(seed):
            raise RandomProjectionError(seed)

    def _configure(self) -> None:
        rng = random.Random(self._seed)
        scale = 1.0 / math.sqrt(self._k)
        # k rows × d cols of Rademacher ±1/√k entries.
        self._rows = [
            [scale if rng.random() < 0.5 else -scale for _ in range(self._d)]
            for _ in range(self._k)
        ]

    def _check_vector(self, vector: Any) -> list:
        try:
            vec = list(vector)
        except TypeError as exc:
            raise RandomProjectionError("vector must be a sequence") from exc
        if len(vec) != self._d:
            raise RandomProjectionError(f"vector must have dimension {self._d}")
        if not all(_is_number(x) for x in vec):
            raise RandomProjectionError("vector components must be numbers")
        return vec

    # ── projection ─────────────────────────────────────────────────────────────────────
    def _project_locked(self, vec: list) -> list:
        rows = self._rows
        return [sum(rows[i][j] * vec[j] for j in range(self._d)) for i in range(self._k)]

    def project(self, vector: Any) -> list:
        """Project a ``d``-vector to its ``k``-dimensional sketch."""
        vec = self._check_vector(vector)
        with self._lock:
            return self._project_locked(vec)

    def distance(self, vector_a: Any, vector_b: Any) -> float:
        """Estimated Euclidean distance ``‖a − b‖`` via the projection."""
        va = self._check_vector(vector_a)
        vb = self._check_vector(vector_b)
        with self._lock:
            pa = self._project_locked(va)
            pb = self._project_locked(vb)
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(pa, pb, strict=False)))

    def dot(self, vector_a: Any, vector_b: Any) -> float:
        """Estimated dot product ``⟨a, b⟩`` via the projection."""
        va = self._check_vector(vector_a)
        vb = self._check_vector(vector_b)
        with self._lock:
            pa = self._project_locked(va)
            pb = self._project_locked(vb)
        return sum(x * y for x, y in zip(pa, pb, strict=False))

    def norm(self, vector: Any) -> float:
        """Estimated Euclidean norm ``‖a‖`` via the projection."""
        vec = self._check_vector(vector)
        with self._lock:
            p = self._project_locked(vec)
        return math.sqrt(sum(x * x for x in p))

    def reset(
        self, input_dim: int | None = None, output_dim: int | None = None, seed: int | None = None
    ) -> None:
        """Redraw the matrix; optionally reconfigure ``input_dim`` / ``output_dim`` / ``seed``."""
        with self._lock:
            nd = self._d if input_dim is None else input_dim
            nk = self._k if output_dim is None else output_dim
            ns = self._seed if seed is None else seed
            self._validate(nd, nk, ns)
            self._d, self._k, self._seed = nd, nk, ns
            self._configure()

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def input_dim(self) -> int:
        return self._d

    @property
    def output_dim(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``input_dim`` / ``output_dim`` / ``compression_ratio`` (d/k) / ``seed``."""
        with self._lock:
            return {
                "input_dim": self._d,
                "output_dim": self._k,
                "compression_ratio": round(self._d / self._k, 6),
                "seed": self._seed,
            }
