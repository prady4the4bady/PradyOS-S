"""Compact, sortable, human-readable IDs for tasks, incidents, records."""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"  # Crockford-ish, no ambiguous chars


def _b32(n: int, width: int) -> str:
    out = []
    for _ in range(width):
        out.append(_ALPHABET[n & 31])
        n >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    """Return a sortable ID like ``ti_01hnq8mz4x_a3b7gp1y``.

    40-bit time component (centiseconds since epoch) + 40 random bits.
    Sorts roughly chronologically. Collision-safe across any throughput
    a single Sovereign machine produces.
    """
    ts = int(time.time() * 100) & ((1 << 40) - 1)
    rand = secrets.randbits(40)
    return f"{prefix}_{_b32(ts, 8)}_{_b32(rand, 8)}"
