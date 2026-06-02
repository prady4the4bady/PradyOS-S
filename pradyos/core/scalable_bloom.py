"""Phase 118 — Sovereign Scalable Bloom Filter (Almeida, Baquero, Preguiça & Hutchison, 2007).

A Bloom variant for **sets of unknown, growing size**. A classic Bloom (P72) must be
sized for a fixed capacity up front; exceed it and the false-positive rate blows past
the target. The Scalable Bloom Filter keeps a **list of ordinary Bloom layers**: when
the active layer fills to its capacity it is frozen and a **new layer** is appended —
**larger** (capacity grows by a factor ``growth``) and with a **tighter** target error
(``error × ratio`` per layer, ``ratio < 1``). A lookup is the logical OR over all
layers (so there are still **no false negatives**).

Because the per-layer error rates form a geometric series, the compounded false-positive
probability over *all* layers is bounded for **any** number of elements:

    P_total ≈ Σ_i P_i = P₀·(1 − ratio)·Σ ratio^i = P₀·(1 − ratio)/(1 − ratio) = P_target

(choosing layer-``i`` error ``P_i = P_target·(1 − ratio)·ratio^i``). So the structure
grows to fit the data while still guaranteeing the target FP — the **capacity-free**
membership filter, distinct from the fixed-capacity Bloom (P72), the deletion-supporting
Counting Bloom (P107) and the forgetting Stable Bloom (P110).

Each layer is sized by the standard Bloom formulae (``m = ⌈−n·ln(P_i)/(ln2)²⌉``,
``k = ⌈(m/n)·ln2⌉``); bits live in a ``bytearray`` and hashing is double-hashing from a
seeded BLAKE2b digest salted by the layer index (so layers hash independently). Pure
stdlib; thread-safe via a single ``threading.Lock`` (the public surface acquires it;
layer helpers run under it and never re-acquire).
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any


class ScalableBloomError(Exception):
    """Raised for an invalid Scalable-Bloom operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class _Layer:
    """One fixed-capacity Bloom filter layer (bit array + k hashes)."""

    __slots__ = ("capacity", "error_rate", "index", "m", "k", "bits", "count")

    def __init__(self, capacity: int, error_rate: float, index: int) -> None:
        m = math.ceil(-capacity * math.log(error_rate) / (math.log(2) ** 2))
        m = max(1, m)
        k = max(1, math.ceil((m / capacity) * math.log(2)))
        self.capacity = capacity
        self.error_rate = error_rate
        self.index = index
        self.m = m
        self.k = k
        self.bits = bytearray((m + 7) // 8)
        self.count = 0

    def _positions(self, seed: int, element: Any) -> list[int]:
        data = repr((seed, self.index, element)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1
        return [(h1 + i * h2) % self.m for i in range(self.k)]

    def contains(self, seed: int, element: Any) -> bool:
        bits = self.bits
        return all(bits[p >> 3] & (1 << (p & 7)) for p in self._positions(seed, element))

    def add(self, seed: int, element: Any) -> None:
        bits = self.bits
        for p in self._positions(seed, element):
            bits[p >> 3] |= (1 << (p & 7))
        self.count += 1


class ScalableBloomFilter:
    """Capacity-free Bloom filter: grows by appending tighter, larger layers."""

    def __init__(self, initial_capacity: int = 1000, error_rate: float = 0.01,
                 ratio: float = 0.9, growth: int = 2, seed: int = 0) -> None:
        self._validate(initial_capacity, error_rate, ratio, growth, seed)
        self._initial_capacity = initial_capacity
        self._error_rate = error_rate
        self._ratio = ratio
        self._growth = growth
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _validate(initial_capacity: Any, error_rate: Any, ratio: Any,
                  growth: Any, seed: Any) -> None:
        if not _is_pos_int(initial_capacity):
            raise ScalableBloomError(initial_capacity)
        if not (_is_number(error_rate) and 0.0 < error_rate < 1.0):
            raise ScalableBloomError(error_rate)
        if not (_is_number(ratio) and 0.0 < ratio < 1.0):
            raise ScalableBloomError(ratio)
        if not (_is_int(growth) and growth >= 2):
            raise ScalableBloomError(growth)
        if not _is_int(seed):
            raise ScalableBloomError(seed)

    def _layer_error(self, index: int) -> float:
        # P_i = P_target * (1 - ratio) * ratio^i ⇒ Σ_i P_i = P_target.
        return self._error_rate * (1.0 - self._ratio) * (self._ratio ** index)

    def _layer_capacity(self, index: int) -> int:
        return self._initial_capacity * (self._growth ** index)

    def _new_layer(self) -> _Layer:
        idx = len(self._layers)
        return _Layer(self._layer_capacity(idx), self._layer_error(idx), idx)

    def _init_state(self) -> None:
        self._layers: list[_Layer] = [_Layer(self._layer_capacity(0), self._layer_error(0), 0)]
        self._count = 0

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, element: Any) -> bool:
        """Add ``element``. Returns True if newly added, False if already present.

        Appends a fresh (larger, tighter) layer first when the active layer is full."""
        with self._lock:
            if self._contains_locked(element):
                return False
            active = self._layers[-1]
            if active.count >= active.capacity:
                active = self._new_layer()
                self._layers.append(active)
            active.add(self._seed, element)
            self._count += 1
            return True

    def contains(self, element: Any) -> bool:
        """Membership test — logical OR over every layer (no false negatives)."""
        with self._lock:
            return self._contains_locked(element)

    def _contains_locked(self, element: Any) -> bool:
        return any(layer.contains(self._seed, element) for layer in self._layers)

    def __contains__(self, element: Any) -> bool:
        return self.contains(element)

    def __len__(self) -> int:
        with self._lock:
            return self._count

    def false_positive_rate(self) -> float:
        """Compounded false-positive bound ``1 − Π(1 − P_i)`` over the current layers."""
        with self._lock:
            return self._fpr_locked()

    def _fpr_locked(self) -> float:
        prod = 1.0
        for layer in self._layers:
            prod *= (1.0 - layer.error_rate)
        return 1.0 - prod

    def reset(self, initial_capacity: int | None = None, error_rate: float | None = None,
              ratio: float | None = None, growth: int | None = None,
              seed: int | None = None) -> None:
        """Clear all layers; optionally reconfigure."""
        with self._lock:
            ic = self._initial_capacity if initial_capacity is None else initial_capacity
            er = self._error_rate if error_rate is None else error_rate
            rt = self._ratio if ratio is None else ratio
            gr = self._growth if growth is None else growth
            sd = self._seed if seed is None else seed
            self._validate(ic, er, rt, gr, sd)
            self._initial_capacity, self._error_rate = ic, er
            self._ratio, self._growth, self._seed = rt, gr, sd
            self._init_state()

    @property
    def initial_capacity(self) -> int:
        return self._initial_capacity

    @property
    def error_rate(self) -> float:
        return self._error_rate

    @property
    def ratio(self) -> float:
        return self._ratio

    @property
    def growth(self) -> int:
        return self._growth

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_layers(self) -> int:
        with self._lock:
            return len(self._layers)

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def stats(self) -> dict:
        """Summary: ``count`` / ``num_layers`` / ``initial_capacity`` / ``error_rate`` /
        ``ratio`` / ``growth`` / ``total_bits`` / ``false_positive_rate`` / ``seed``."""
        with self._lock:
            return {
                "count": self._count,
                "num_layers": len(self._layers),
                "initial_capacity": self._initial_capacity,
                "error_rate": self._error_rate,
                "ratio": self._ratio,
                "growth": self._growth,
                "total_bits": sum(layer.m for layer in self._layers),
                "false_positive_rate": self._fpr_locked(),
                "seed": self._seed,
            }
