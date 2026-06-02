"""Phase 121 — Sovereign Invertible Bloom Lookup Table (Goodrich & Mitzenmacher, 2011).

A probabilistic **key→value store that can be fully enumerated and differenced** — a
capability the platform's filters and sketches lack. Each of ``m`` cells holds four XOR
accumulators: a ``count`` of entries hashed there, a ``key_sum`` (XOR of folded keys), a
``value_sum`` (XOR of folded values), and a ``key_hash_sum`` (XOR of a *second* hash of
each key, used to recognise "pure" cells reliably). ``insert`` / ``delete`` XOR a key's
``(key, value)`` into its ``k`` cells and adjust their counts by ``±1`` (a ``delete`` may
drive counts negative — that is exactly what powers set reconciliation).

The cells are **partitioned** into ``k`` sub-tables (one cell per sub-table per key), so a
key always touches ``k`` distinct cells. Beyond ``get``, two operations make it invertible:

* **``list_entries()``** decodes the whole table by **peeling** — repeatedly find a *pure*
  cell (``|count| == 1`` whose ``key_hash_sum`` matches the hash of its ``key_sum``), emit
  its ``(key, value)``, and XOR it out of its other cells, which may expose new pure cells.
  Below a load threshold (≈ ``m / (k·1.2)`` entries) this recovers **every** entry w.h.p.
* **``subtract(other)``** combines two tables cellwise (counts subtract, sums XOR) into an
  IBLT of the **symmetric difference**; peeling it yields exactly the keys in one set but
  not the other (positive count → only in *self*, negative → only in *other*) — the basis
  of efficient **set reconciliation**.

Keys/values may be any hashable object: each is folded to a stable 64-bit id (BLAKE2b) and
a registry maps ids back to originals for output (auxiliary — an integer-keyed IBLT needs
no registry). Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

_MASK64 = (1 << 64) - 1


class IBLTError(Exception):
    """Raised for an invalid IBLT operation / configuration / decode. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _fold(value: Any, salt: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(repr(value).encode("utf-8"),
                                          digest_size=8, salt=salt).digest(), "big")


class InvertibleBloomLookupTable:
    """Listable, differenceable probabilistic key→value store (IBLT)."""

    _KEY_SALT = b"iblt-key"
    _VAL_SALT = b"iblt-val"

    def __init__(self, num_cells: int = 1000, num_hashes: int = 4, seed: int = 0) -> None:
        if not _is_pos_int(num_cells):
            raise IBLTError(num_cells)
        if not _is_pos_int(num_hashes):
            raise IBLTError(num_hashes)
        if not _is_int(seed):
            raise IBLTError(seed)
        self._k = num_hashes
        self._sub = max(1, num_cells // num_hashes)
        self._m = self._sub * self._k
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    def _init_state(self) -> None:
        self._count = [0] * self._m
        self._key_sum = [0] * self._m
        self._val_sum = [0] * self._m
        self._khash_sum = [0] * self._m
        self._size = 0
        self._key_reg: dict[int, Any] = {}
        self._val_reg: dict[int, Any] = {}

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _key_hash(self, kid: int) -> int:
        # secondary hash of the (already-folded) key id, salted by seed.
        salt = (self._seed & _MASK64).to_bytes(8, "big")
        return int.from_bytes(hashlib.blake2b(kid.to_bytes(8, "big"),
                                              digest_size=8, salt=salt).digest(), "big")

    def _cells(self, kid: int) -> list[int]:
        """The ``k`` partitioned cell indices for a folded key id (one per sub-table)."""
        cells = []
        for i in range(self._k):
            salt = (self._seed + i + 1 & _MASK64).to_bytes(8, "big")
            h = int.from_bytes(hashlib.blake2b(kid.to_bytes(8, "big"),
                                               digest_size=8, salt=salt).digest(), "big")
            cells.append(i * self._sub + (h % self._sub))
        return cells

    # ── mutation ──────────────────────────────────────────────────────────────────────
    def _apply(self, kid: int, vid: int, kh: int, delta: int) -> None:
        for c in self._cells(kid):
            self._count[c] += delta
            self._key_sum[c] ^= kid
            self._val_sum[c] ^= vid
            self._khash_sum[c] ^= kh

    def insert(self, key: Any, value: Any) -> None:
        """Insert the ``(key, value)`` pair."""
        with self._lock:
            kid = _fold(key, self._KEY_SALT)
            vid = _fold(value, self._VAL_SALT)
            self._key_reg[kid] = key
            self._val_reg[vid] = value
            self._apply(kid, vid, self._key_hash(kid), 1)
            self._size += 1

    def delete(self, key: Any, value: Any) -> None:
        """Delete the ``(key, value)`` pair (XOR is self-inverse; counts go down)."""
        with self._lock:
            kid = _fold(key, self._KEY_SALT)
            vid = _fold(value, self._VAL_SALT)
            self._apply(kid, vid, self._key_hash(kid), -1)
            self._size -= 1

    def reset(self) -> None:
        """Clear all cells."""
        with self._lock:
            self._init_state()

    # ── query ─────────────────────────────────────────────────────────────────────────
    def _get_locked(self, key: Any, default: Any) -> Any:
        kid = _fold(key, self._KEY_SALT)
        kh = self._key_hash(kid)
        for c in self._cells(kid):
            if self._count[c] == 0 and self._key_sum[c] == 0 and self._khash_sum[c] == 0:
                return default                                   # empty cell ⇒ key absent
            if self._count[c] == 1 and self._key_sum[c] == kid and self._khash_sum[c] == kh:
                return self._val_reg.get(self._val_sum[c], default)   # found
            if self._count[c] == 1 and self._key_sum[c] != kid:
                return default                                   # a different single key ⇒ absent
        return default                                           # overloaded ⇒ best-effort absent

    def get(self, key: Any, default: Any = None) -> Any:
        """Return the value for ``key`` (decoded from a pure cell), else ``default``."""
        with self._lock:
            return self._get_locked(key, default)

    def contains(self, key: Any) -> bool:
        sentinel = object()
        with self._lock:
            return self._get_locked(key, sentinel) is not sentinel

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def __len__(self) -> int:
        with self._lock:
            return self._size

    # ── peeling / listing ───────────────────────────────────────────────────────────
    def _peel(self) -> tuple[list[tuple[int, int, int]], bool]:
        """Peel pure cells from a working copy. Returns ((sign, kid, vid)*, complete)."""
        count = list(self._count)
        key_sum = list(self._key_sum)
        val_sum = list(self._val_sum)
        khash_sum = list(self._khash_sum)
        m = self._m

        def is_pure(c: int) -> bool:
            return abs(count[c]) == 1 and khash_sum[c] == self._key_hash(key_sum[c])

        results: list[tuple[int, int, int]] = []
        queue = [c for c in range(m) if is_pure(c)]
        while queue:
            c = queue.pop()
            if not is_pure(c):
                continue
            sign = count[c]
            kid = key_sum[c]
            vid = val_sum[c]
            kh = khash_sum[c]
            results.append((sign, kid, vid))
            for cc in self._cells(kid):
                count[cc] -= sign
                key_sum[cc] ^= kid
                val_sum[cc] ^= vid
                khash_sum[cc] ^= kh
            for cc in self._cells(kid):
                if is_pure(cc):
                    queue.append(cc)
        complete = all(count[c] == 0 and key_sum[c] == 0 and val_sum[c] == 0
                       and khash_sum[c] == 0 for c in range(m))
        return results, complete

    def list_entries(self) -> list[tuple[Any, Any]]:
        """Decode and return every ``(key, value)`` pair; raise if it cannot fully decode."""
        with self._lock:
            decoded, complete = self._peel()
            if not complete:
                raise IBLTError("could not fully decode (overloaded)")
            return [(self._key_reg.get(kid, kid), self._val_reg.get(vid, vid))
                    for _sign, kid, vid in decoded]

    def is_listable(self) -> bool:
        """True iff :meth:`list_entries` would fully decode at the current load."""
        with self._lock:
            return self._peel()[1]

    # ── set reconciliation ──────────────────────────────────────────────────────────
    def _check_compatible(self, other: "InvertibleBloomLookupTable") -> None:
        if not isinstance(other, InvertibleBloomLookupTable):
            raise IBLTError("other must be an IBLT")
        if other._m != self._m or other._k != self._k or other._seed != self._seed:
            raise IBLTError("incompatible IBLTs (cells / hashes / seed differ)")

    def subtract(self, other: "InvertibleBloomLookupTable") -> "InvertibleBloomLookupTable":
        """Return ``self − other`` cellwise — an IBLT of the symmetric difference."""
        self._check_compatible(other)
        out = InvertibleBloomLookupTable(num_cells=self._m, num_hashes=self._k, seed=self._seed)
        with self._lock, other._lock:
            for c in range(self._m):
                out._count[c] = self._count[c] - other._count[c]
                out._key_sum[c] = self._key_sum[c] ^ other._key_sum[c]
                out._val_sum[c] = self._val_sum[c] ^ other._val_sum[c]
                out._khash_sum[c] = self._khash_sum[c] ^ other._khash_sum[c]
            out._key_reg = {**self._key_reg, **other._key_reg}
            out._val_reg = {**self._val_reg, **other._val_reg}
            out._size = self._size - other._size
        return out

    def decode_difference(self) -> tuple[list, list]:
        """Peel a subtracted table into ``(only_in_self, only_in_other)`` entry lists.

        Raises :class:`IBLTError` if the difference is too large to decode."""
        with self._lock:
            decoded, complete = self._peel()
            if not complete:
                raise IBLTError("could not fully decode the difference (too large)")
            positive, negative = [], []
            for sign, kid, vid in decoded:
                pair = (self._key_reg.get(kid, kid), self._val_reg.get(vid, vid))
                (positive if sign > 0 else negative).append(pair)
            return positive, negative

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def num_cells(self) -> int:
        return self._m

    @property
    def num_hashes(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``size`` / ``num_cells`` / ``num_hashes`` / ``listable`` / ``seed``."""
        with self._lock:
            return {
                "size": self._size,
                "num_cells": self._m,
                "num_hashes": self._k,
                "listable": self._peel()[1],
                "seed": self._seed,
            }
