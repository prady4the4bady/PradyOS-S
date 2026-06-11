"""Phase 130 — Sovereign AMS sketch / tug-of-war estimator (Alon, Matias & Szegedy, 1996).

The Gödel-Prize *frequency-moments* sketch — a **streaming `F₂` (second-moment / squared-L2-
norm / self-join-size) and inner-product estimator**, a new aggregate-estimation capability
for the platform. It answers a *scalar question about the whole frequency vector*, not a
per-key one.

Mechanism (*tug of war*). Pick a sign hash `ε : keys → {−1, +1}`. Maintain a single counter
`X = Σ_i f_i · ε(i)`, updated incrementally (`X += count · ε(key)`). Because the signs are
zero-mean and (≥2-wise) independent, the cross terms cancel in expectation:

    E[X²] = Σ_i f_i² · E[ε(i)²] + Σ_{i≠j} f_i f_j · E[ε(i)ε(j)] = Σ_i f_i² = F₂.

So `X²` is an *unbiased* estimator of `F₂` — but a noisy one (`Var[X²] ≤ 2·F₂²` under 4-wise
independence). The classic **median-of-means** construction tames it: average `X²` across
`width` independent counters (variance ↓ by `width`, relative SE `≈ √(2/width)`) and take the
**median** across `depth` such rows (failure probability ↓ exponentially). With the *same*
sign hashes, two sketches estimate the **inner product** `Σ_i f_i·g_i` (join size between two
streams) via `median_r mean_c (Xᶠ · Xᵍ)`, and sketches are **mergeable** by counter-wise
addition (the sketch is linear in the counts, so it natively supports the turnstile model with
negative updates).

This is *different* from CountSketch/P94 and Count-Min/P76, which answer *point queries*
(per-key frequency): AMS estimates a *scalar aggregate* of the entire frequency vector — its
second moment, L2 norm, or join size. Pure stdlib (`hashlib.blake2b` for the sign hashes);
thread-safe via a single `threading.Lock`; deterministic given the seed.
"""

from __future__ import annotations

import hashlib
import statistics
import threading
from collections.abc import Iterable
from typing import Any

_MAX_COUNTERS = 65536


class AMSError(Exception):
    """Raised for an invalid AMS-sketch operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_pos_int(x: Any) -> bool:
    return _is_int(x) and x >= 1


class AMSSketch:
    """Alon–Matias–Szegedy tug-of-war sketch for `F₂` / L2-norm / inner-product estimation."""

    def __init__(self, width: int = 64, depth: int = 7, seed: int = 0) -> None:
        self._validate(width, depth, seed)
        self._width = width
        self._depth = depth
        self._n = width * depth
        self._seed = seed
        self._seed_bytes = repr(seed).encode("ascii")
        self._nbytes = (self._n + 7) // 8
        self._lock = threading.Lock()
        self._counters = [0] * self._n

    # ── validation / sign hashing ─────────────────────────────────────────────────────
    @staticmethod
    def _validate(width: Any, depth: Any, seed: Any) -> None:
        if not _is_pos_int(width):
            raise AMSError("width must be a positive int")
        if not _is_pos_int(depth):
            raise AMSError("depth must be a positive int")
        if width * depth > _MAX_COUNTERS:
            raise AMSError(f"width*depth must be <= {_MAX_COUNTERS}")
        if not _is_int(seed):
            raise AMSError("seed must be an int")

    @staticmethod
    def _to_bytes(key: Any) -> bytes:
        if isinstance(key, bool):
            raise AMSError("key must be str, bytes or int (not bool)")
        if isinstance(key, bytes):
            return b"b" + key
        if isinstance(key, str):
            return b"s" + key.encode("utf-8")
        if isinstance(key, int):
            return b"i" + repr(key).encode("ascii")
        raise AMSError("key must be str, bytes or int")

    def _signs(self, key: Any) -> list[int]:
        """Return the ``n`` independent ±1 signs for ``key`` (bit k of a wide digest)."""
        kb = self._to_bytes(key)
        raw = bytearray()
        block = 0
        while len(raw) < self._nbytes:
            raw += hashlib.blake2b(
                self._seed_bytes + block.to_bytes(4, "big") + kb,
                digest_size=min(64, self._nbytes - len(raw)),
            ).digest()
            block += 1
        return [1 if (raw[k >> 3] >> (k & 7)) & 1 else -1 for k in range(self._n)]

    # ── update ────────────────────────────────────────────────────────────────────────
    def update(self, key: Any, count: int = 1) -> None:
        """Apply ``+count`` (may be negative — turnstile) occurrences of ``key``."""
        if not _is_int(count):
            raise AMSError("count must be an int")
        signs = self._signs(key)
        with self._lock:
            c = self._counters
            for k in range(self._n):
                c[k] += count * signs[k]

    def update_many(self, keys: Iterable[Any]) -> int:
        """Apply ``+1`` for each key in ``keys``; returns the number consumed."""
        sign_vectors = [self._signs(k) for k in keys]  # hash outside the lock
        with self._lock:
            c = self._counters
            for signs in sign_vectors:
                for k in range(self._n):
                    c[k] += signs[k]
        return len(sign_vectors)

    # ── estimation ──────────────────────────────────────────────────────────────────
    def _row_means(self, products) -> list[float]:
        w = self._width
        return [sum(products[r * w : (r + 1) * w]) / w for r in range(self._depth)]

    def _f2_locked(self) -> float:
        squares = [x * x for x in self._counters]
        return statistics.median(self._row_means(squares))

    def f2(self) -> float:
        """Estimated second frequency moment ``F₂ = Σ f_i²`` (self-join size)."""
        with self._lock:
            return self._f2_locked()

    def second_moment(self) -> float:
        return self.f2()

    def l2_norm(self) -> float:
        """Estimated Euclidean norm ``√F₂`` of the frequency vector."""
        return self.f2() ** 0.5

    def inner_product(self, other: AMSSketch) -> float:
        """Estimated inner product ``Σ f_i·g_i`` (join size) with ``other`` (configs must match)."""
        if not isinstance(other, AMSSketch):
            raise AMSError("can only take the inner product with another AMSSketch")
        if (other._width, other._depth, other._seed) != (self._width, self._depth, self._seed):
            raise AMSError("cannot combine sketches with different width/depth/seed")
        with self._lock:
            a = self._counters
            b = a if other is self else list(other._counters)
            products = [a[k] * b[k] for k in range(self._n)]
            return statistics.median(self._row_means(products))

    # ── merge ─────────────────────────────────────────────────────────────────────────
    def merge(self, other: AMSSketch) -> None:
        """Fold ``other`` in by counter-wise addition (linearity; configs must match)."""
        if not isinstance(other, AMSSketch):
            raise AMSError("can only merge another AMSSketch")
        if (other._width, other._depth, other._seed) != (self._width, self._depth, self._seed):
            raise AMSError("cannot merge sketches with different width/depth/seed")
        with self._lock:
            snapshot = self._counters[:] if other is self else list(other._counters)
            for k in range(self._n):
                self._counters[k] += snapshot[k]

    def reset(
        self, width: int | None = None, depth: int | None = None, seed: int | None = None
    ) -> None:
        """Zero all counters; optionally reconfigure ``width`` / ``depth`` / ``seed``."""
        with self._lock:
            nw = self._width if width is None else width
            nd = self._depth if depth is None else depth
            ns = self._seed if seed is None else seed
            self._validate(nw, nd, ns)
            self._width, self._depth, self._n = nw, nd, nw * nd
            self._seed = ns
            self._seed_bytes = repr(ns).encode("ascii")
            self._nbytes = (self._n + 7) // 8
            self._counters = [0] * self._n

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def width(self) -> int:
        return self._width

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_counters(self) -> int:
        return self._n

    @property
    def standard_error(self) -> float:
        """Relative standard error of the `F₂` estimate, ``≈ √(2/width)``."""
        return (2.0 / self._width) ** 0.5

    def stats(self) -> dict:
        """Summary: ``width`` / ``depth`` / ``f2`` / ``l2_norm`` / ``standard_error`` / ``seed``."""
        with self._lock:
            f2 = self._f2_locked()
        return {
            "width": self._width,
            "depth": self._depth,
            "f2": round(f2, 4),
            "l2_norm": round(f2**0.5, 4),
            "standard_error": round((2.0 / self._width) ** 0.5, 6),
            "seed": self._seed,
        }
