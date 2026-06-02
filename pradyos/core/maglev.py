"""Phase 120 — Sovereign Maglev Hashing (Eisenbud, Cilingiroglu et al., 2016).

Google's consistent-hashing scheme from *Maglev: A Fast and Reliable Software Network
Load Balancer* — the **third** distributed key→node assignment algorithm in the
platform, alongside the Hash Ring (P73, consistent-hashing ring) and Rendezvous/HRW
(P119, highest-random-weight). Where the ring places nodes at positions and HRW takes a
per-key argmax over ``N`` nodes, Maglev precomputes a fixed **lookup table** of ``M``
entries (``M`` prime, ``M ≫ N``) so that a lookup is a single ``O(1)`` array index.

**Table population.** Each node ``i`` proposes a pseudo-random *permutation* of the ``M``
slots from two seeded hashes — ``offset = h1(node) mod M`` and ``skip = h2(node) mod
(M − 1) + 1`` — giving ``permutation[i][j] = (offset + j·skip) mod M``. Because ``M`` is
prime and ``1 ≤ skip ≤ M − 1``, that sequence visits every slot. Nodes then take turns,
round-robin: on its turn a node claims its next-most-preferred slot that is still empty,
until all ``M`` slots are filled. The result is **near-perfect even load** (each node owns
``≈ M/N`` slots — far tighter than ring hashing) and good behaviour under membership
change (a rebuild keeps most assignments stable, disturbing mainly the changed node's
share), with the fastest lookups of the three schemes.

``lookup(key) = table[hash(key) mod M]``. The table is rebuilt when the node set changes.
The hashes are seeded BLAKE2b, so the table is deterministic and reproducible. Pure
stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any


class MaglevError(Exception):
    """Raised for an invalid Maglev operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    if n % 3 == 0:
        return n == 3
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def _next_prime(n: int) -> int:
    candidate = max(2, n)
    while not _is_prime(candidate):
        candidate += 1
    return candidate


class MaglevHash:
    """Lookup-table consistent hashing (Maglev) — O(1) lookups, near-even load."""

    def __init__(self, nodes: Any = None, table_size: int = 65537, seed: int = 0) -> None:
        if not (_is_int(table_size) and table_size >= 2):
            raise MaglevError(table_size)
        if not _is_int(seed):
            raise MaglevError(seed)
        self._table_size = _next_prime(table_size)   # M must be prime
        self._seed = seed
        self._lock = threading.Lock()
        self._nodes: list[Any] = []
        if nodes is not None:
            try:
                iterator = list(nodes)
            except TypeError as exc:
                raise MaglevError(nodes) from exc
            seen = set()
            for node in iterator:
                if node not in seen:
                    seen.add(node)
                    self._nodes.append(node)
        self._table: list[int] = []
        self._build_locked()

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _two_hashes(self, value: Any) -> tuple[int, int]:
        data = repr((self._seed, value)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=16).digest()
        return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:], "big")

    def _key_slot(self, key: Any) -> int:
        data = repr((self._seed, "key", key)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big") % self._table_size

    # ── table population (Maglev permutation fill) ──────────────────────────────────
    def _build_locked(self) -> None:
        m = self._table_size
        nodes = sorted(self._nodes, key=str)          # deterministic, order-independent
        self._nodes = nodes
        n = len(nodes)
        if n == 0:
            self._table = []
            return
        if n > m:
            raise MaglevError("more nodes than table slots")
        offsets = []
        skips = []
        for node in nodes:
            h1, h2 = self._two_hashes(node)
            offsets.append(h1 % m)
            skips.append((h2 % (m - 1)) + 1)
        next_idx = [0] * n
        table = [-1] * m
        filled = 0
        while filled < m:
            for i in range(n):
                c = (offsets[i] + next_idx[i] * skips[i]) % m
                while table[c] != -1:
                    next_idx[i] += 1
                    c = (offsets[i] + next_idx[i] * skips[i]) % m
                table[c] = i
                next_idx[i] += 1
                filled += 1
                if filled == m:
                    break
        self._table = table

    # ── node management ────────────────────────────────────────────────────────────────
    def add_node(self, node: Any) -> bool:
        """Add ``node`` and rebuild the table; return True if newly added."""
        with self._lock:
            if node in self._nodes:
                return False
            self._nodes.append(node)
            self._build_locked()
            return True

    def remove_node(self, node: Any) -> bool:
        """Remove ``node`` and rebuild the table; return True if it was present."""
        with self._lock:
            if node not in self._nodes:
                return False
            self._nodes.remove(node)
            self._build_locked()
            return True

    def contains(self, node: Any) -> bool:
        with self._lock:
            return node in self._nodes

    def __contains__(self, node: Any) -> bool:
        return self.contains(node)

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)

    # ── lookup ─────────────────────────────────────────────────────────────────────────
    def lookup(self, key: Any) -> Any:
        """Return the node responsible for ``key`` (O(1) table index)."""
        with self._lock:
            if not self._nodes:
                raise MaglevError("no nodes")
            return self._nodes[self._table[self._key_slot(key)]]

    def assign(self, key: Any) -> Any:
        """Alias for :meth:`lookup`."""
        return self.lookup(key)

    def reset(self, table_size: int | None = None, seed: int | None = None) -> None:
        """Remove all nodes; optionally reconfigure ``table_size`` / ``seed``."""
        with self._lock:
            if table_size is not None:
                if not (_is_int(table_size) and table_size >= 2):
                    raise MaglevError(table_size)
                self._table_size = _next_prime(table_size)
            if seed is not None:
                if not _is_int(seed):
                    raise MaglevError(seed)
                self._seed = seed
            self._nodes = []
            self._table = []

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def table_size(self) -> int:
        return self._table_size

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def nodes(self) -> list:
        with self._lock:
            return list(self._nodes)

    def load_distribution(self) -> dict:
        """Number of table slots owned by each node."""
        with self._lock:
            dist = {node: 0 for node in self._nodes}
            for idx in self._table:
                dist[self._nodes[idx]] += 1
            return dist

    def stats(self) -> dict:
        """Summary: ``num_nodes`` / ``table_size`` / ``nodes`` / ``min_load`` /
        ``max_load`` / ``load_ratio`` (max/min, 1.0 = perfectly even) / ``seed``."""
        with self._lock:
            loads = [0] * len(self._nodes)
            for idx in self._table:
                loads[idx] += 1
            min_load = min(loads) if loads else 0
            max_load = max(loads) if loads else 0
            ratio = (max_load / min_load) if min_load > 0 else (1.0 if not loads else 0.0)
            return {
                "num_nodes": len(self._nodes),
                "table_size": self._table_size,
                "nodes": sorted(self._nodes, key=str),
                "min_load": min_load,
                "max_load": max_load,
                "load_ratio": round(ratio, 4),
                "seed": self._seed,
            }
