"""Phase 101 — Sovereign Ribbon Filter (Dillinger–Walzer, 2021).

A **static, retrieval-based** approximate-membership filter — the space-efficient
successor to the Phase 100 XOR filter. Where the XOR filter solves a 3-uniform
hypergraph by *peeling* (and our peeling build needs ≈ 3.69·n slots to never
stall), the Ribbon filter frames membership as a **sparse linear system over
GF(2)** and solves it by structured Gaussian elimination down a narrow diagonal
*ribbon* band — which packs far tighter:

  * **Space:** ``m = ⌈n / LOAD⌉ + w`` slots of ``bits_per_entry`` bits each
    (here ``LOAD = 0.85``, ribbon width ``w = 64``) — an overhead of ≈ ``1.18×``
    at scale, *below* the XOR filter's ``1.23×`` theoretical bound and far below
    its ``3.69×`` peeling construction. Wider ``w`` pushes the achievable load
    toward ``1.0`` (the information-theoretic ``n · bits`` limit) — the ribbon's
    defining advantage.
  * **Lookup:** recompute the key's band and XOR ≤ ``w`` slots (``O(w)``).
  * **False-positive rate:** ≈ ``2 ** -bits_per_entry`` (≈ 0.4 % at 8 bits).

Construction. Each key ``k`` maps to a start column ``s(k) ∈ [0, m-w]``, a
``w``-bit coefficient row ``c(k)`` anchored at ``s`` (bit 0 forced to 1), and a
``bits_per_entry``-bit fingerprint ``f(k)``. Its equation is
``⊕_{j: c(k)[j]=1} Z[s(k)+j] = f(k)`` over a slot table ``Z``. Rows are inserted
one at a time into a row-echelon form keyed by pivot column: a row is shifted to
its leftmost set coefficient, and if that pivot column is occupied it is XORed
against the resident pivot (clearing the bit) and shifted on — the band never
widens past ``w``, so each insert is ``O(w)``. A back-substitution from the high
column down then fills ``Z``. If a row reduces to all-zero coefficients with a
non-zero residual the rows are linearly dependent — :class:`RibbonFilterError`
asks for a different seed (with ``LOAD = 0.85`` this is astronomically rare).

A query recomputes ``s, c`` and XORs the selected slots; because ``Z`` solves
every member's equation exactly, ``⊕ Z[s+j] == f(k)`` holds for every built key
(**zero false negatives**), while a non-member matches only by fingerprint
collision (``≈ 2**-bits``). All ``bits_per_entry`` bit-planes share one
coefficient matrix, so the solve runs once on packed ``bits``-wide words.

Fingerprint / start / coefficient are slices of a seeded BLAKE2b digest (the
hashing pattern of MinHash (P88), Count Sketch (P94) and the XOR filter (P100)).
Pure stdlib. Thread-safe via a single ``threading.Lock``; the heavy solve runs
lock-free on a snapshot and is published with one locked assignment.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

# Ribbon geometry. ``_W`` is the band width (slots a single key's equation can
# span); ``_LOAD`` is the target load factor n/m. Width 64 with load 0.85 keeps
# the banded GF(2) system full-rank with overwhelming probability while holding
# the space overhead (≈ 1.18× at scale) below the XOR filter's 1.23× bound.
_W = 64
_LOAD = 0.85
_WMASK = (1 << _W) - 1


class RibbonFilterError(Exception):
    """Raised for an invalid Ribbon-filter configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class RibbonFilter:
    """Static, space-efficient membership filter built by GF(2) ribbon retrieval."""

    def __init__(self, bits_per_entry: int = 8, seed: int = 0) -> None:
        if not _is_pos_int(bits_per_entry) or bits_per_entry > 64:
            raise RibbonFilterError(bits_per_entry)
        if not _is_int(seed):
            raise RibbonFilterError(seed)
        self._bits = bits_per_entry
        self._mask = (1 << bits_per_entry) - 1
        self._seed = seed
        self._slots: list[int] = []
        self._m = 0
        self._n = 0
        self._built = False
        self._lock = threading.Lock()

    # ── hashing (pure) ────────────────────────────────────────────────────────────
    def _digest(self, tag: Any, key: Any, seed: int) -> int:
        data = repr((seed, tag, key)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")

    def _row(self, key: Any, seed: int, m: int) -> tuple[int, int, int]:
        """The key's (start column, w-bit coefficient row, fingerprint)."""
        s = self._digest("s", key, seed) % (m - _W + 1)
        coeff = (self._digest("c", key, seed) & _WMASK) | 1  # anchor: bit 0 set
        fp = self._digest("fp", key, seed) & self._mask
        return s, coeff, fp

    # ── build (static construction) ──────────────────────────────────────────────
    def build(self, keys: Any) -> None:
        """Construct the filter from a complete key set (replaces any prior filter)."""
        distinct = list(dict.fromkeys(keys))  # dedup, preserve order
        n = len(distinct)
        with self._lock:  # snapshot config for a race-free solve
            seed = self._seed

        if n == 0:
            with self._lock:
                self._slots = []
                self._m = 0
                self._n = 0
                self._built = True
            return

        m = int(math.ceil(n / _LOAD)) + _W
        span = m - _W + 1  # number of legal start columns (≥ 2)

        # Incremental row-echelon form: at most one pivot row per column, stored
        # relative to its pivot column (bit 0 = the pivot, always set).
        piv_coeff = [0] * m
        piv_rhs = [0] * m
        for key in distinct:
            s = self._digest("s", key, seed) % span
            c = (self._digest("c", key, seed) & _WMASK) | 1
            rhs = self._digest("fp", key, seed) & self._mask
            i = s
            while True:
                if c == 0:
                    # Row reduced away: consistent only if the residual is zero.
                    if rhs != 0:
                        raise RibbonFilterError(
                            "construction failed — linearly dependent rows (retry with different seed)"
                        )
                    break
                tz = (c & -c).bit_length() - 1  # shift to the leftmost set bit
                i += tz
                c >>= tz
                if piv_coeff[i] == 0:  # free pivot column → install row
                    piv_coeff[i] = c
                    piv_rhs[i] = rhs
                    break
                c ^= piv_coeff[i]  # eliminate (both have bit 0 set)
                rhs ^= piv_rhs[i]

        # Back-substitution from the high column down: every Z[i+j] (j ≥ 1) is solved.
        slots = [0] * m
        for i in range(m - 1, -1, -1):
            c = piv_coeff[i]
            if c == 0:
                continue  # free variable → 0
            val = piv_rhs[i]
            rest = c >> 1
            j = 1
            while rest:
                if rest & 1:
                    val ^= slots[i + j]
                rest >>= 1
                j += 1
            slots[i] = val

        with self._lock:
            self._slots = slots
            self._m = m
            self._n = n
            self._built = True

    def reset(self, bits_per_entry: int | None = None, seed: int | None = None) -> None:
        """Clear the filter back to the unbuilt state; optionally reconfigure."""
        with self._lock:
            if bits_per_entry is not None:
                if not _is_pos_int(bits_per_entry) or bits_per_entry > 64:
                    raise RibbonFilterError(bits_per_entry)
                self._bits = bits_per_entry
                self._mask = (1 << bits_per_entry) - 1
            if seed is not None:
                if not _is_int(seed):
                    raise RibbonFilterError(seed)
                self._seed = seed
            self._slots = []
            self._m = 0
            self._n = 0
            self._built = False

    # ── query ────────────────────────────────────────────────────────────────────
    def contains(self, key: Any) -> bool:
        """Membership test (no false negatives for built keys; ``≈2**-bits`` false positives)."""
        with self._lock:
            if not self._built:
                raise RibbonFilterError("filter not built — call build() first")
            if self._n == 0:
                return False
            m = self._m
            slots = self._slots
            s = self._digest("s", key, self._seed) % (m - _W + 1)
            coeff = (self._digest("c", key, self._seed) & _WMASK) | 1
            fp = self._digest("fp", key, self._seed) & self._mask
            result = 0
            j = 0
            c = coeff
            while c:
                if c & 1:
                    result ^= slots[s + j]
                c >>= 1
                j += 1
            return result == fp

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def __len__(self) -> int:
        with self._lock:
            return self._n

    @property
    def bits_per_entry(self) -> int:
        return self._bits

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def built(self) -> bool:
        with self._lock:
            return self._built

    @property
    def slots(self) -> int:
        with self._lock:
            return self._m

    @property
    def ribbon_width(self) -> int:
        return _W

    def stats(self) -> dict:
        """Summary: ``bits_per_entry``, ``built``, key count ``n``, ``slots`` (table
        size ``m``), ``ribbon_width``, ``load_factor`` (n/m), and the ``≈2**-bits``
        false-positive rate."""
        with self._lock:
            return {
                "bits_per_entry": self._bits,
                "built": self._built,
                "n": self._n,
                "slots": self._m,
                "ribbon_width": _W,
                "load_factor": (self._n / self._m) if self._m else 0.0,
                "false_positive_rate": 2.0 ** (-self._bits),
            }
