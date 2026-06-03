"""Phase 132 — Sovereign Cuckoo Hash Table (Pagh & Rodler, 2001).

An **exact key→value dictionary with worst-case `O(1)` lookup** — a new capability for the
platform. This is categorically different from the Cuckoo *Filter* of P86 (which is an
*approximate set-membership* sketch with a false-positive rate): a Cuckoo Hash *Table* stores
the actual key/value pairs and answers `get`/`contains` with **zero error** in **at most two
slot probes**, regardless of load.

Mechanism. Two tables `T1`, `T2` (each `m` slots) and two independent hashes give every key
exactly two candidate homes — `T1[h1(key)]` and `T2[h2(key)]`. An item lives in exactly one
of its two homes, so:

  * **lookup** checks both homes — *worst-case two probes, O(1)*;
  * **insert** seats the item in its `T1` home, and if occupied **evicts** the resident,
    which is re-seated in *its* `T2` home, displacing the next resident, and so on (the
    "cuckoo" kicking chain). If the chain exceeds a bound, the table **rehashes** (new hash
    seeds, growing if needed) and replays every item — amortised `O(1)` insert.

The lookup cost is independent of the number of items or the load factor — the defining
guarantee of cuckoo hashing. Pure stdlib (`hashlib.blake2b` for the two hashes); thread-safe
via a single ``threading.Lock``; deterministic given the seed (the rehash sequence is a pure
function of the operation order).
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Iterable

_SENTINEL = object()


class CuckooHashError(Exception):
    """Raised for an invalid Cuckoo-hash-table operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_pos_int(x: Any) -> bool:
    return _is_int(x) and x >= 1


class CuckooHashTable:
    """Exact key→value map backed by two-table cuckoo hashing (worst-case O(1) lookup)."""

    def __init__(self, capacity: int = 16, seed: int = 0) -> None:
        self._validate(capacity, seed)
        self._m = capacity                       # slots per table
        self._seed = seed
        self._round = 0                          # bumped on every rehash → fresh hashes
        self._rehashes = 0
        self._size = 0
        self._t1: list = [None] * capacity
        self._t2: list = [None] * capacity
        self._lock = threading.Lock()

    # ── validation / hashing ─────────────────────────────────────────────────────────
    @staticmethod
    def _validate(capacity: Any, seed: Any) -> None:
        if not _is_pos_int(capacity):
            raise CuckooHashError("capacity must be a positive int")
        if not _is_int(seed):
            raise CuckooHashError("seed must be an int")

    @staticmethod
    def _key_bytes(key: Any) -> bytes:
        if isinstance(key, bool):
            raise CuckooHashError("key must be str, bytes or int (not bool)")
        if isinstance(key, bytes):
            return b"b" + key
        if isinstance(key, str):
            return b"s" + key.encode("utf-8")
        if isinstance(key, int):
            return b"i" + repr(key).encode("ascii")
        raise CuckooHashError("key must be str, bytes or int")

    def _salt(self, table: int) -> bytes:
        return repr(self._seed).encode("ascii") + b":" + repr(self._round).encode("ascii") + bytes([table])

    def _h1(self, key_bytes: bytes) -> int:
        return int.from_bytes(hashlib.blake2b(self._salt(1) + key_bytes, digest_size=8).digest(), "big") % self._m

    def _h2(self, key_bytes: bytes) -> int:
        return int.from_bytes(hashlib.blake2b(self._salt(2) + key_bytes, digest_size=8).digest(), "big") % self._m

    def _max_kicks(self) -> int:
        return max(32, 8 * self._m.bit_length())

    # ── insertion (cuckoo kicking + rehash) ──────────────────────────────────────────
    def _seat(self, key: Any, value: Any, kb: bytes):
        """Seat ``(key, value)`` via eviction. Returns ``True`` if seated, else the homeless
        ``(key, value, key_bytes)`` triple that could not be placed within the kick bound."""
        cur = (key, value, kb)
        for _ in range(self._max_kicks()):
            i1 = self._h1(cur[2])
            if self._t1[i1] is None:
                self._t1[i1] = cur
                return True
            cur, self._t1[i1] = self._t1[i1], cur
            i2 = self._h2(cur[2])
            if self._t2[i2] is None:
                self._t2[i2] = cur
                return True
            cur, self._t2[i2] = self._t2[i2], cur
        return cur

    def _all_items(self) -> list:
        return [e for e in self._t1 if e is not None] + [e for e in self._t2 if e is not None]

    def _rebuild(self, pending) -> None:
        items = self._all_items()
        items.append(pending)
        grow = False
        while True:
            if grow:
                self._m *= 2
            self._round += 1
            self._rehashes += 1
            self._t1 = [None] * self._m
            self._t2 = [None] * self._m
            if all(self._seat(k, v, kb) is True for (k, v, kb) in items):
                return
            grow = True                          # seed change wasn't enough → grow and retry

    def put(self, key: Any, value: Any) -> None:
        """Insert or update ``key → value`` (exact; updates in place if present)."""
        kb = self._key_bytes(key)
        with self._lock:
            i1 = self._h1(kb)
            e1 = self._t1[i1]
            if e1 is not None and e1[0] == key:
                self._t1[i1] = (key, value, kb)
                return
            i2 = self._h2(kb)
            e2 = self._t2[i2]
            if e2 is not None and e2[0] == key:
                self._t2[i2] = (key, value, kb)
                return
            self._size += 1
            homeless = self._seat(key, value, kb)
            if homeless is not True:
                self._rebuild(homeless)

    def put_many(self, items: Iterable[Any]) -> int:
        """Insert/update many ``(key, value)`` pairs; returns the count consumed."""
        parsed = []
        for it in items:
            if not isinstance(it, (list, tuple)) or len(it) != 2:
                raise CuckooHashError("each item must be a (key, value) pair")
            parsed.append((it[0], it[1]))
        for key, value in parsed:
            self.put(key, value)
        return len(parsed)

    # ── lookup / delete ────────────────────────────────────────────────────────────────
    def get(self, key: Any, default: Any = None) -> Any:
        """Return the value for ``key`` (≤ 2 slot probes), or ``default`` if absent."""
        kb = self._key_bytes(key)
        with self._lock:
            e1 = self._t1[self._h1(kb)]
            if e1 is not None and e1[0] == key:
                return e1[1]
            e2 = self._t2[self._h2(kb)]
            if e2 is not None and e2[0] == key:
                return e2[1]
            return default

    def contains(self, key: Any) -> bool:
        return self.get(key, _SENTINEL) is not _SENTINEL

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def remove(self, key: Any) -> bool:
        """Delete ``key``; returns whether it was present."""
        kb = self._key_bytes(key)
        with self._lock:
            i1 = self._h1(kb)
            e1 = self._t1[i1]
            if e1 is not None and e1[0] == key:
                self._t1[i1] = None
                self._size -= 1
                return True
            i2 = self._h2(kb)
            e2 = self._t2[i2]
            if e2 is not None and e2[0] == key:
                self._t2[i2] = None
                self._size -= 1
                return True
            return False

    def reset(self, capacity: int | None = None, seed: int | None = None) -> None:
        """Empty the table; optionally reconfigure ``capacity`` / ``seed``."""
        with self._lock:
            nc = self._m if capacity is None else capacity
            ns = self._seed if seed is None else seed
            self._validate(nc, ns)
            self._m = nc
            self._seed = ns
            self._round = 0
            self._rehashes = 0
            self._size = 0
            self._t1 = [None] * nc
            self._t2 = [None] * nc

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._size

    def keys(self) -> list:
        with self._lock:
            return [e[0] for e in self._all_items()]

    @property
    def capacity(self) -> int:
        return self._m

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def size(self) -> int:
        return self._size

    @property
    def num_rehashes(self) -> int:
        return self._rehashes

    @property
    def load_factor(self) -> float:
        return self._size / (2 * self._m) if self._m else 0.0

    def stats(self) -> dict:
        """Summary: ``size`` / ``capacity`` (slots/table) / ``total_slots`` / ``load_factor`` /
        ``num_rehashes`` / ``seed``."""
        with self._lock:
            total = 2 * self._m
            return {
                "size": self._size,
                "capacity": self._m,
                "total_slots": total,
                "load_factor": round(self._size / total, 6) if total else 0.0,
                "num_rehashes": self._rehashes,
                "seed": self._seed,
            }
