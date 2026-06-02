"""Phase 114 — Sovereign Bloomier Filter (Chazelle, Kilian, Rubinfeld & Tal, 2004).

*The Bloomier filter: an efficient data structure for static support lookup tables*
— the **associative** generalisation of a Bloom filter. Where a Bloom filter answers
*is `x` in the set?*, a Bloomier filter answers *what value is associated with `x`?*
for a **static** key→value map, in near-optimal space.

Construction is the same **XOR-peeling** used by the platform's XOR (P100) and
Binary-Fuse (P108) membership filters, generalised from storing a fingerprint to
storing a *payload*. Each key hashes (one seeded mix, sliced into three segment-
local indices) to three cells of a table; the cells are assigned by peeling the
3-XOR hypergraph (repeatedly removing a cell touched by exactly one unassigned key)
and then back-substituting in reverse peel order so that, for every key,

    array[h0] XOR array[h1] XOR array[h2] == payload(key)

where ``payload = (fingerprint << value_bits) | value_index``. A lookup XORs the
three cells, splits out the fingerprint and the value index, and — **only if the
fingerprint matches the key's own** — returns ``value_table[value_index]``. So
*members* are answered **exactly**, while a *non-member* is reported as *not-found*
with probability ``1 − 2^(−fingerprint_bits)`` (a fingerprint collision is the sole
false-positive path, exactly as in the XOR filter).

The filter is **static**: it is built once from a complete mapping via ``build`` and
then immutable (``get`` to look up, ``reset`` to clear). Keys are folded to a stable
64-bit value (process-independent BLAKE2b of ``repr(key)``); peeling is probabilistic,
so a stall triggers a deterministic **seed retry**. Values may be *any* object
(stored verbatim in a value table, indexed positionally — no hashing of values, so
unhashable values are fine). Pure stdlib (``hashlib`` + integer mixing); thread-safe
via a single ``threading.RLock`` (``build`` and ``get`` can race).
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

_MASK64 = (1 << 64) - 1
_MIX_CONST = 0x517CC1B727220A95
_MAX_PEEL_ROUNDS = 32
_MAX_SEED_RETRIES = 100


class BloomierError(Exception):
    """Raised for an invalid Bloomier operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _key_to_u64(key: Any) -> int:
    """Fold an arbitrary key to a stable 64-bit integer (process-independent)."""
    data = repr(key).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


class BloomierFilter:
    """Static key→value lookup table (Bloomier filter; XOR-peeling construction)."""

    def __init__(self, fingerprint_bits: int = 8, seed: int = 0) -> None:
        if not _is_int(fingerprint_bits) or fingerprint_bits < 1 or fingerprint_bits > 32:
            raise BloomierError(fingerprint_bits)
        if not _is_int(seed):
            raise BloomierError(seed)
        self._fp_bits = fingerprint_bits
        self._fp_mask = (1 << fingerprint_bits) - 1
        self._seed = seed
        self._lock = threading.RLock()
        self._reset_state()

    def _reset_state(self) -> None:
        self._array: list[int] = []
        self._values: list[Any] = []
        self._segment = 0
        self._value_bits = 0
        self._n = 0
        self._built = False
        self._build_seed = self._seed

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    @staticmethod
    def _mix(x: int, seed: int) -> int:
        return ((x ^ seed) * _MIX_CONST) & _MASK64

    def _slots(self, u64: int, seed: int, segment: int) -> tuple[int, int, int, int]:
        """Return ``(h0, h1, h2, fingerprint)`` for a folded key under ``seed``."""
        mix = self._mix(u64, seed)
        h0 = mix % segment
        h1 = (mix >> 21) % segment
        h2 = (mix >> 42) % segment
        f = mix & self._fp_mask
        return h0, h1, h2, f

    # ── build (static construction) ──────────────────────────────────────────────────
    def build(self, mapping: Any) -> None:
        """Construct the filter from a complete ``{key: value}`` mapping.

        Raises :class:`BloomierError` on a key hash-collision or if peeling fails to
        converge after the internal seed retries."""
        try:
            items = list(mapping.items())
        except AttributeError as exc:
            raise BloomierError("mapping must be a dict-like with .items()") from exc

        keys = [k for k, _ in items]
        values = [v for _, v in items]
        u64s = [_key_to_u64(k) for k in keys]
        if len(set(u64s)) != len(u64s):
            raise BloomierError("duplicate/colliding keys")

        n = len(items)
        if n == 0:
            with self._lock:
                self._reset_state()
                self._built = True
            return

        # Sort by folded key so build order does not affect the result; the value at
        # sorted position j is value_table[j], and the key's value_index is j.
        order = sorted(range(n), key=lambda i: u64s[i])
        sorted_u64 = [u64s[i] for i in order]
        value_table = [values[i] for i in order]
        value_bits = (n - 1).bit_length()          # bits to index 0..n-1 (0 when n == 1)

        m = math.ceil(1.23 * n / 3)
        segment = max(1, m) + 4
        total = 3 * segment

        seed = self._seed
        for _attempt in range(_MAX_SEED_RETRIES + 1):
            array = self._try_build(sorted_u64, seed, segment, total, value_bits)
            if array is not None:
                with self._lock:
                    self._array = array
                    self._values = value_table
                    self._segment = segment
                    self._value_bits = value_bits
                    self._n = n
                    self._built = True
                    self._build_seed = seed
                return
            seed = (seed + 1) & _MASK64
        raise BloomierError("build failed: cycle detected")

    def _try_build(self, u64s: list[int], seed: int, segment: int, total: int,
                   value_bits: int) -> list[int] | None:
        """One peeling + back-substitution attempt; return the array or ``None`` on stall."""
        n = len(u64s)
        slots = []
        for j, u in enumerate(u64s):
            h0, h1, h2, f = self._slots(u, seed, segment)
            payload = (f << value_bits) | j           # encode fingerprint + value index
            slots.append((h0, h1 + segment, h2 + 2 * segment, payload))

        count = [0] * total
        xor_idx = [0] * total
        for i in range(n):
            h0, h1, h2, _p = slots[i]
            for b in (h0, h1, h2):
                count[b] += 1
                xor_idx[b] ^= i

        queue = [b for b in range(total) if count[b] == 1]
        stack: list[tuple[int, int]] = []
        peeled = [False] * n
        rounds = 0
        while queue:
            rounds += 1
            if rounds > _MAX_PEEL_ROUNDS * max(1, total):
                return None
            b = queue.pop()
            if count[b] != 1:
                continue
            i = xor_idx[b]
            if peeled[i]:
                continue
            peeled[i] = True
            stack.append((i, b))
            h0, h1, h2, _p = slots[i]
            for bb in (h0, h1, h2):
                count[bb] -= 1
                xor_idx[bb] ^= i
                if count[bb] == 1:
                    queue.append(bb)

        if len(stack) != n:
            return None

        array = [0] * total
        for i, b in reversed(stack):
            h0, h1, h2, payload = slots[i]
            val = payload
            for o in (h0, h1, h2):
                if o != b:
                    val ^= array[o]
            array[b] = val
        return array

    # ── query ──────────────────────────────────────────────────────────────────────────
    def get(self, key: Any, default: Any = None) -> Any:
        """Return the value mapped to ``key`` (exact for members), else ``default``.

        Raises :class:`BloomierError` if the filter has not been built."""
        with self._lock:
            if not self._built:
                raise BloomierError("filter not built")
            if self._n == 0:
                return default
            segment = self._segment
            array = self._array
            h0, h1, h2, f = self._slots(_key_to_u64(key), self._build_seed, segment)
            payload = array[h0] ^ array[h1 + segment] ^ array[h2 + 2 * segment]
            value_index = payload & ((1 << self._value_bits) - 1) if self._value_bits else 0
            fingerprint = payload >> self._value_bits
            if fingerprint == f and 0 <= value_index < self._n:
                return self._values[value_index]
            return default

    def contains(self, key: Any) -> bool:
        """True iff ``key``'s fingerprint matches (a member, or a `2^(−bits)` false positive)."""
        with self._lock:
            if not self._built:
                raise BloomierError("filter not built")
            if self._n == 0:
                return False
            segment = self._segment
            array = self._array
            h0, h1, h2, f = self._slots(_key_to_u64(key), self._build_seed, segment)
            payload = array[h0] ^ array[h1 + segment] ^ array[h2 + 2 * segment]
            return (payload >> self._value_bits) == f

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def __len__(self) -> int:
        with self._lock:
            return self._n

    def reset(self, seed: int | None = None) -> None:
        """Clear the filter back to the unbuilt state; optionally reconfigure ``seed``."""
        with self._lock:
            if seed is not None:
                if not _is_int(seed):
                    raise BloomierError(seed)
                self._seed = seed
            self._reset_state()

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def built(self) -> bool:
        with self._lock:
            return self._built

    @property
    def fingerprint_bits(self) -> int:
        return self._fp_bits

    @property
    def num_cells(self) -> int:
        with self._lock:
            return len(self._array)

    def stats(self) -> dict:
        """Summary: ``built`` / ``num_keys`` / ``num_cells`` / ``fingerprint_bits`` /
        ``value_bits`` / ``bits_per_key`` (payload-bits·cells/keys, None when empty) / ``seed``."""
        with self._lock:
            n = self._n
            cells = len(self._array)
            payload_bits = self._fp_bits + self._value_bits
            bpk = (payload_bits * cells / n) if (self._built and n > 0) else None
            return {
                "built": self._built,
                "num_keys": n,
                "num_cells": cells,
                "fingerprint_bits": self._fp_bits,
                "value_bits": self._value_bits,
                "bits_per_key": bpk,
                "seed": self._seed,
            }
