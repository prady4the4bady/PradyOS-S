"""Phase 131 — Sovereign Priority Sampling (Duffield, Lund & Thorup, 2007).

*Priority sampling for estimation of arbitrary subset sums* — a **bounded-size weighted
sample that answers unbiased subset-sum queries**, a new sampling capability for the platform.
Where Reservoir/P85 keeps a *uniform* sample (good for counts) and Weighted-Reservoir/P98
draws a single weighted item, priority sampling keeps the `k` "most informative" weighted
items and lets you estimate the summed weight of *any* subset with **provably zero bias**.

Mechanism. Each item `(key, weight > 0)` is given a **priority** `q = weight / u` where
`u ∼ Uniform(0, 1]` is a deterministic per-key hash. The sketch keeps the `k` items with the
largest priorities (a min-heap evicts the smallest). The **threshold** `τ` is the
`(k+1)`-th largest priority — i.e. the largest priority among the *evicted* items (`τ = 0`
while ≤ `k` items have been seen, so the sample is then exact). Each retained item is given an
**adjusted weight** `ŵ = max(weight, τ)`. Then for **any** subset `S`,

    Σ_{i ∈ S ∩ sample} ŵ_i   is an unbiased estimator of   Σ_{i ∈ S} w_i,

because `E[ŵ_i · 1(i sampled)] = w_i` for every item (Duffield–Lund–Thorup). Variance is
`O(1/k)`, and the result is **order-independent** (it depends only on the set of
`(key, priority)` pairs). Subsets are addressed here by an optional **category** tag.

This is *different* from uniform reservoir sampling (which estimates counts, not weighted
sums) and from a single weighted draw: it is the unbiased-aggregate-over-a-bounded-sample
primitive. Pure stdlib (`heapq`, `hashlib.blake2b`); thread-safe via a single
``threading.Lock``; deterministic given the seed.
"""

from __future__ import annotations

import hashlib
import heapq
import threading
from collections.abc import Iterable
from typing import Any

_TWO64 = 1 << 64


class PrioritySampleError(Exception):
    """Raised for an invalid Priority-Sample operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_pos_int(x: Any) -> bool:
    return _is_int(x) and x >= 1


def _is_pos_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and x > 0


class PrioritySample:
    """Duffield–Lund–Thorup priority sample for unbiased subset-sum estimation."""

    def __init__(self, capacity: int = 256, seed: int = 0) -> None:
        self._validate(capacity, seed)
        self._k = capacity
        self._seed = seed
        self._seed_bytes = repr(seed).encode("ascii")
        self._lock = threading.Lock()
        self._sample: dict[Any, list] = {}  # key -> [weight, priority, category]
        self._heap: list = []  # (priority, key) min-heap; may hold stale entries
        self._tau = 0.0  # (k+1)-th largest priority seen
        self._seen = 0  # distinct keys ever inserted

    # ── validation / hashing ─────────────────────────────────────────────────────────
    @staticmethod
    def _validate(capacity: Any, seed: Any) -> None:
        if not _is_pos_int(capacity):
            raise PrioritySampleError("capacity must be a positive int")
        if not _is_int(seed):
            raise PrioritySampleError("seed must be an int")

    @staticmethod
    def _key_bytes(key: Any) -> bytes:
        if isinstance(key, bool):
            raise PrioritySampleError("key must be str, bytes or int (not bool)")
        if isinstance(key, bytes):
            return b"b" + key
        if isinstance(key, str):
            return b"s" + key.encode("utf-8")
        if isinstance(key, int):
            return b"i" + repr(key).encode("ascii")
        raise PrioritySampleError("key must be str, bytes or int")

    def _u(self, key: Any) -> float:
        digest = hashlib.blake2b(self._seed_bytes + self._key_bytes(key), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        return (h + 1) / (_TWO64 + 1)  # uniform in (0, 1)

    # ── heap helpers (lazy deletion: an entry is valid iff it matches the live sample) ──
    def _purge(self) -> None:
        h, s = self._heap, self._sample
        while h:
            pr, key = h[0]
            entry = s.get(key)
            if entry is not None and entry[1] == pr:
                return
            heapq.heappop(h)  # stale (evicted or superseded priority)

    # ── update ────────────────────────────────────────────────────────────────────────
    def add(self, key: Any, weight: float, category: Any = None) -> bool:
        """Observe ``(key, weight)`` with optional ``category``; returns whether it is sampled."""
        if not _is_pos_number(weight):
            raise PrioritySampleError("weight must be a number > 0")
        if category is not None and not isinstance(category, str):
            raise PrioritySampleError("category must be a string or null")
        kb_key = self._key_bytes(key)  # validates key type (raises before locking)  # noqa: F841
        u = self._u(key)
        q = weight / u
        with self._lock:
            s, h = self._sample, self._heap
            if key in s:  # re-add: last-write-wins, membership unchanged
                s[key] = [float(weight), q, category]
                heapq.heappush(h, (q, key))  # old entry becomes stale
                return True
            self._seen += 1
            if len(s) < self._k:
                s[key] = [float(weight), q, category]
                heapq.heappush(h, (q, key))
                return True
            self._purge()
            min_pr, min_key = h[0]
            if q > min_pr:  # new item beats the weakest → evict it
                heapq.heappop(h)
                del s[min_key]
                if min_pr > self._tau:
                    self._tau = min_pr
                s[key] = [float(weight), q, category]
                heapq.heappush(h, (q, key))
                return True
            if q > self._tau:  # new item itself is below the bar
                self._tau = q
            return False

    def add_many(self, items: Iterable[Any]) -> int:
        """Observe many ``(key, weight)`` or ``(key, weight, category)`` items; returns the count."""
        parsed = []
        for it in items:
            if not isinstance(it, list | tuple) or not (2 <= len(it) <= 3):
                raise PrioritySampleError(
                    "each item must be (key, weight) or (key, weight, category)"
                )
            parsed.append((it[0], it[1], it[2] if len(it) == 3 else None))
        for key, weight, cat in parsed:
            self.add(key, weight, cat)
        return len(parsed)

    # ── estimation ──────────────────────────────────────────────────────────────────
    def estimate(self, category: Any = None) -> float:
        """Unbiased estimate of the total weight of the subset matching ``category`` (all if None)."""
        if category is not None and not isinstance(category, str):
            raise PrioritySampleError("category must be a string or null")
        with self._lock:
            tau = self._tau
            return float(
                sum(
                    max(w, tau)
                    for w, _q, cat in self._sample.values()
                    if category is None or cat == category
                )
            )

    def total(self) -> float:
        """Unbiased estimate of the total weight of the whole stream."""
        return self.estimate(None)

    def sample_keys(self) -> list:
        """The keys currently retained in the sample."""
        with self._lock:
            return list(self._sample.keys())

    def reset(self, capacity: int | None = None, seed: int | None = None) -> None:
        """Clear the sample; optionally reconfigure ``capacity`` / ``seed``."""
        with self._lock:
            nk = self._k if capacity is None else capacity
            ns = self._seed if seed is None else seed
            self._validate(nk, ns)
            self._k = nk
            self._seed = ns
            self._seed_bytes = repr(ns).encode("ascii")
            self._sample = {}
            self._heap = []
            self._tau = 0.0
            self._seen = 0

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._sample)

    @property
    def capacity(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_seen(self) -> int:
        return self._seen

    @property
    def threshold(self) -> float:
        return self._tau

    def stats(self) -> dict:
        """Summary: ``capacity`` / ``sampled`` / ``num_seen`` / ``threshold`` / ``total_estimate`` / ``seed``."""
        with self._lock:
            tau = self._tau
            total = float(sum(max(w, tau) for w, _q, _c in self._sample.values()))
            return {
                "capacity": self._k,
                "sampled": len(self._sample),
                "num_seen": self._seen,
                "threshold": round(tau, 6),
                "total_estimate": round(total, 4),
                "seed": self._seed,
            }
