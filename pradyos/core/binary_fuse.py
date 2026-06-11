"""Phase 108 — Sovereign Binary Fuse Filter (Graf & Lemire, 2022).

A **static, space-optimal** approximate-membership filter — the segmented
refinement of the fuse-graph construction (Dietzfelbinger & Walzer). Like the
Phase 100 XOR filter it is **built once** from a complete key set and is then
immutable; a query XORs three fingerprint slots and compares against the key's
own fingerprint, so there are **zero false negatives** and a false-positive rate
of ``≈ 2**-8 = 1/256`` for the 8-bit fingerprints used here. The binary-fuse
layout uses three segments sized at ``⌈1.23·n / 3⌉ + 4`` slots each (``m = 3·segment``,
≈ **9.9 bits/key** at the 8-bit fingerprint width here) and peels in near-linear time.

Hashing — a single seeded **xxhash-style** 64-bit integer mix (pure Python, no
external dependency):

    mix(x, seed) = ((x ^ seed) * 0x517cc1b727220a95) & MASK64

The 64-bit output is sliced into three segment-local indices and a fingerprint:

    h_i = (mix >> (i*21)) % segment_size       (i = 0, 1, 2)
    f   = mix & 0xFF

The three probed slots live in consecutive segments — ``array[h0]``,
``array[h1 + seg]``, ``array[h2 + 2·seg]`` — and a built key satisfies
``f == array[h0] ^ array[h1+seg] ^ array[h2+2·seg]``.

Construction (peeling + back-substitution): map every key to its three slots,
repeatedly **peel** a slot touched by exactly one still-unassigned key (recording
the (key, slot) order), then assign fingerprints in reverse peel order so each
key's equation holds. Peeling is probabilistic; if it fails to converge in 32
rounds the build **retries with an incremented seed** (up to 3 attempts) before
raising :class:`BinaryFuseError`.

The filter is **immutable after build** — there is no incremental ``add``; call
``build`` with the full key set, or ``reset`` to return to the unbuilt state.
Keys are sorted internally before construction, so build order does not affect
the result. Pure stdlib; thread-safe via a single ``threading.RLock`` (``build``
and ``contains`` can race).
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


class BinaryFuseError(Exception):
    """Raised for an invalid Binary-Fuse operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _key_to_u64(key: Any) -> int:
    """Fold an arbitrary key to a stable 64-bit integer (process-independent)."""
    data = repr(key).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


class BinaryFuseFilter:
    """Static, space-optimal membership filter (Graf–Lemire binary fuse, 8-bit)."""

    def __init__(self, seed: int = 0) -> None:
        if not _is_int(seed):
            raise BinaryFuseError(seed)
        self._seed = seed
        self._lock = threading.RLock()
        self._array: list[int] = []
        self._segment = 0
        self._n = 0
        self._built = False
        self._build_seed = seed  # the seed that actually produced the current filter

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
        f = mix & 0xFF
        return h0, h1, h2, f

    # ── build (static construction) ──────────────────────────────────────────────────
    def build(self, keys: Any) -> None:
        """Construct the filter from a complete key set (replaces any prior filter).

        Raises :class:`BinaryFuseError` on duplicate keys, or if peeling fails to
        converge after the internal seed retries."""
        try:
            key_list = list(keys)
        except TypeError as exc:
            raise BinaryFuseError(keys) from exc

        u64s = [_key_to_u64(k) for k in key_list]
        if len(set(u64s)) != len(u64s):
            raise BinaryFuseError("duplicate keys")

        # Sort internally so build order does not affect the result.
        u64s.sort()
        n = len(u64s)

        if n == 0:
            with self._lock:
                self._array = []
                self._segment = 0
                self._n = 0
                self._built = True
                self._build_seed = self._seed
            return

        m = math.ceil(1.23 * n / 3)
        segment = max(1, m) + 4
        total = 3 * segment

        seed = self._seed
        for _attempt in range(_MAX_SEED_RETRIES + 1):
            result = self._try_build(u64s, seed, segment, total)
            if result is not None:
                with self._lock:
                    self._array = result
                    self._segment = segment
                    self._n = n
                    self._built = True
                    self._build_seed = seed
                return
            seed = (seed + 1) & _MASK64
        raise BinaryFuseError("build failed: cycle detected")

    def _try_build(self, u64s: list[int], seed: int, segment: int, total: int) -> list[int] | None:
        """One peeling + back-substitution attempt; return the array or ``None`` on stall."""
        n = len(u64s)
        slots = []
        for u in u64s:
            h0, h1, h2, f = self._slots(u, seed, segment)
            slots.append((h0, h1 + segment, h2 + 2 * segment, f))

        count = [0] * total
        xor_idx = [0] * total
        for i in range(n):
            h0, h1, h2, _f = slots[i]
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
            h0, h1, h2, _f = slots[i]
            for bb in (h0, h1, h2):
                count[bb] -= 1
                xor_idx[bb] ^= i
                if count[bb] == 1:
                    queue.append(bb)

        if len(stack) != n:
            return None

        array = [0] * total
        for i, b in reversed(stack):
            h0, h1, h2, f = slots[i]
            others = [x for x in (h0, h1, h2) if x != b]
            val = f
            for o in others:
                val ^= array[o]
            array[b] = val
        return array

    # ── query ──────────────────────────────────────────────────────────────────────────
    def contains(self, key: Any) -> bool:
        """Membership test; raises if the filter has not been built yet."""
        with self._lock:
            if not self._built:
                raise BinaryFuseError("filter not built")
            if self._n == 0:
                return False
            segment = self._segment
            array = self._array
            h0, h1, h2, f = self._slots(_key_to_u64(key), self._build_seed, segment)
            return f == (array[h0] ^ array[h1 + segment] ^ array[h2 + 2 * segment])

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
                    raise BinaryFuseError(seed)
                self._seed = seed
            self._array = []
            self._segment = 0
            self._n = 0
            self._built = False
            self._build_seed = self._seed

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def built(self) -> bool:
        with self._lock:
            return self._built

    @property
    def array_size(self) -> int:
        with self._lock:
            return len(self._array)

    def stats(self) -> dict:
        """Summary: ``built`` / ``num_keys`` (n) / ``array_size`` (m) /
        ``bits_per_key`` (``8·m/n`` if built and non-empty, else ``None``) / ``seed``."""
        with self._lock:
            n = self._n
            m = len(self._array)
            bpk = (8.0 * m / n) if (self._built and n > 0) else None
            return {
                "built": self._built,
                "num_keys": n,
                "array_size": m,
                "bits_per_key": bpk,
                "seed": self._seed,
            }
