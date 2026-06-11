"""Phase 116 — Sovereign TinyLFU (Einziger, Friedman & Manes, 2017).

*TinyLFU: a highly efficient cache admission policy* — a **frequency sketch with
aging**, the recency-aware estimator behind modern cache-admission policies (e.g.
Caffeine's W-TinyLFU). A plain Count-Min sketch (P76) estimates frequencies but never
forgets, so on a long access stream every counter saturates and old popularity is
indistinguishable from current popularity. TinyLFU adds the two ingredients a cache
needs:

* a **doorkeeper** — a small Bloom filter that absorbs *one-hit wonders*: a key's first
  access only sets a doorkeeper bit; the (larger) Count-Min array is touched only from
  the second access on, so singletons never consume real counters. The estimate adds
  back the doorkeeper bit: ``estimate(x) = countmin(x) + (1 if x in doorkeeper else 0)``.
* a **reset / aging** rule — a running access counter is bumped on every access, and
  once it reaches the **sample size** ``W`` the sketch *ages*: every Count-Min counter
  is **halved** (``c >>= 1``) and the doorkeeper is cleared. This makes the estimate
  track a *sliding* frequency that decays stale popularity instead of accumulating it.

The headline operation is ``admit(candidate, victim)`` → ``estimate(candidate) >
estimate(victim)``: the frequency-based decision a cache uses to decide whether a new
key is worth evicting an incumbent for.

This is a *new feature-class* — **windowed / aging frequency for admission** — distinct
from the platform's plain frequency sketches (Count-Min/P76, Count-Sketch/P94) and
heavy-hitter trackers (Space-Saving/P87, Misra-Gries/P99, HeavyKeeper/P102), none of
which age. Counters are one byte each (saturating at 255) in a flat ``bytearray``;
hashing is double-hashing from one seeded BLAKE2b digest (the Counting-Bloom/P107
idiom). Fully deterministic given the seed. Pure stdlib (``array``-free: ``bytearray``
+ ``hashlib``); thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

_MAX_COUNTER = 255  # one byte per Count-Min counter (saturating)
_DOORKEEPER_FP = 0.01  # target doorkeeper false-positive rate at the sample size


class TinyLFUError(Exception):
    """Raised for an invalid TinyLFU operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class TinyLFU:
    """Aging approximate-frequency sketch with a doorkeeper, for cache admission."""

    def __init__(
        self, sample_size: int = 1000, width: int | None = None, depth: int = 4, seed: int = 0
    ) -> None:
        if width is None:
            width = sample_size
        self._validate(sample_size, width, depth, seed)
        self._sample_size = sample_size
        self._width = width
        self._depth = depth
        self._seed = seed
        self._lock = threading.Lock()
        self._configure()

    @staticmethod
    def _validate(sample_size: Any, width: Any, depth: Any, seed: Any) -> None:
        if not _is_pos_int(sample_size):
            raise TinyLFUError(sample_size)
        if not _is_pos_int(width):
            raise TinyLFUError(width)
        if not _is_pos_int(depth):
            raise TinyLFUError(depth)
        if not _is_int(seed):
            raise TinyLFUError(seed)

    def _configure(self) -> None:
        # Doorkeeper Bloom sized for ~1% FP at the sample size (standard Bloom formulae).
        n = self._sample_size
        m_dk = max(1, math.ceil(-n * math.log(_DOORKEEPER_FP) / (math.log(2) ** 2)))
        k_dk = max(1, round((m_dk / n) * math.log(2)))
        self._dk_bits = m_dk
        self._dk_hashes = k_dk
        self._init_state()

    def _init_state(self) -> None:
        self._counters = bytearray(self._width * self._depth)
        self._doorkeeper = bytearray((self._dk_bits + 7) // 8)
        self._accesses = 0  # accesses since the last reset (drives aging)
        self._total = 0  # lifetime accesses
        self._resets = 0

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _digest(self, key: Any) -> tuple[int, int]:
        data = repr((self._seed, key)).encode("utf-8")
        d = hashlib.blake2b(data, digest_size=16).digest()
        h1 = int.from_bytes(d[:8], "big")
        h2 = int.from_bytes(d[8:], "big") | 1  # odd → full period under mod
        return h1, h2

    def _sketch_indices(self, h1: int, h2: int) -> list[int]:
        w = self._width
        return [(r * w) + ((h1 + r * h2) % w) for r in range(self._depth)]

    def _dk_positions(self, h1: int, h2: int) -> list[int]:
        m = self._dk_bits
        off = self._depth  # offset so dk hashes differ from sketch
        return [(h1 + (off + j) * h2) % m for j in range(self._dk_hashes)]

    # ── doorkeeper helpers (no lock) ───────────────────────────────────────────────────
    def _dk_contains(self, positions: list[int]) -> bool:
        dk = self._doorkeeper
        return all(dk[p >> 3] & (1 << (p & 7)) for p in positions)

    def _dk_add(self, positions: list[int]) -> None:
        dk = self._doorkeeper
        for p in positions:
            dk[p >> 3] |= 1 << (p & 7)

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, key: Any) -> None:
        """Record an access to ``key`` (doorkeeper on first sight, Count-Min after); ages
        the sketch once ``sample_size`` accesses have accrued."""
        with self._lock:
            h1, h2 = self._digest(key)
            dk_pos = self._dk_positions(h1, h2)
            if self._dk_contains(dk_pos):
                counters = self._counters
                for idx in self._sketch_indices(h1, h2):
                    if counters[idx] < _MAX_COUNTER:
                        counters[idx] += 1
            else:
                self._dk_add(dk_pos)
            self._accesses += 1
            self._total += 1
            if self._accesses >= self._sample_size:
                self._age()

    def _age(self) -> None:
        counters = self._counters
        for i in range(len(counters)):
            counters[i] >>= 1  # halve every counter
        self._doorkeeper = bytearray((self._dk_bits + 7) // 8)
        self._accesses = 0
        self._resets += 1

    def estimate(self, key: Any) -> int:
        """Approximate access frequency of ``key`` (Count-Min min + doorkeeper bit)."""
        with self._lock:
            h1, h2 = self._digest(key)
            counters = self._counters
            base = min(counters[idx] for idx in self._sketch_indices(h1, h2))
            if self._dk_contains(self._dk_positions(h1, h2)):
                base += 1
            return base

    def admit(self, candidate: Any, victim: Any) -> bool:
        """Cache-admission decision: should ``candidate`` displace ``victim``?

        True iff the candidate's estimated frequency exceeds the victim's."""
        return self.estimate(candidate) > self.estimate(victim)

    def reset(
        self,
        sample_size: int | None = None,
        width: int | None = None,
        depth: int | None = None,
        seed: int | None = None,
    ) -> None:
        """Clear all state; optionally reconfigure ``sample_size`` / ``width`` / ``depth`` / ``seed``."""
        with self._lock:
            ns = self._sample_size if sample_size is None else sample_size
            nw = self._width if width is None else width
            nd = self._depth if depth is None else depth
            nseed = self._seed if seed is None else seed
            self._validate(ns, nw, nd, nseed)
            self._sample_size, self._width, self._depth, self._seed = ns, nw, nd, nseed
            self._configure()

    @property
    def sample_size(self) -> int:
        return self._sample_size

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
    def total(self) -> int:
        """Lifetime number of accesses recorded."""
        with self._lock:
            return self._total

    @property
    def resets(self) -> int:
        """Number of aging resets performed."""
        with self._lock:
            return self._resets

    def stats(self) -> dict:
        """Summary: ``sample_size`` / ``width`` / ``depth`` / ``doorkeeper_bits`` /
        ``total`` / ``accesses_since_reset`` / ``resets`` / ``seed``."""
        with self._lock:
            return {
                "sample_size": self._sample_size,
                "width": self._width,
                "depth": self._depth,
                "doorkeeper_bits": self._dk_bits,
                "total": self._total,
                "accesses_since_reset": self._accesses,
                "resets": self._resets,
                "seed": self._seed,
            }
