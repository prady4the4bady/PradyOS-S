"""Phase 73 — Sovereign Consistent Hash Ring.

Maps arbitrary keys to a small, changing set of nodes (service instances, shards,
cache servers, ...) such that adding or removing a node reshuffles only the keys
that node owned — never the rest. This is the classic consistent-hashing property
and it is what keeps a distributed cache from stampeding on every membership
change.

Each physical node is placed at ``replicas`` points around a 2^64 hash ring
(``"<node>:<i>"`` hashed with SHA-256) so load spreads evenly; a key is owned by
the first node clockwise from the key's hash. Lookups are O(log V) via
``bisect`` over the sorted virtual-point list (V = replicas × nodes).

Pure stdlib (``hashlib`` + ``bisect``); thread-safe via a single non-reentrant
``threading.Lock`` — the public surface acquires it, internal ``*_locked``
helpers assume it is already held.
"""

from __future__ import annotations

import bisect
import hashlib
import threading
from typing import Iterable


DEFAULT_REPLICAS = 100  # virtual points per physical node


class NodeNotFoundError(Exception):
    """Raised when an operation references a node that is not on the ring.

    The offending name is preserved on the ``node`` attribute.
    """

    def __init__(self, node: str) -> None:
        self.node = node
        super().__init__(f"no such node: {node!r}")


class HashRing:
    """A consistent hash ring with virtual nodes (stdlib only)."""

    def __init__(self, nodes: Iterable[str] | None = None, *, replicas: int = DEFAULT_REPLICAS) -> None:
        if replicas <= 0:
            raise ValueError("replicas must be a positive integer")
        self._replicas = int(replicas)
        self._ring: dict[int, str] = {}     # hash point -> node
        self._sorted: list[int] = []        # sorted hash points for bisect
        self._nodes: set[str] = set()
        self._lock = threading.Lock()
        if nodes:
            for node in nodes:
                self._add_locked(str(node))

    # ── hashing / internal (assume the lock is held) ─────────────────────────
    @staticmethod
    def _hash(value: str) -> int:
        return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")

    def _add_locked(self, node: str) -> None:
        if node in self._nodes:
            return
        self._nodes.add(node)
        for i in range(self._replicas):
            point = self._hash(f"{node}:{i}")
            self._ring[point] = node
            bisect.insort(self._sorted, point)

    # ── membership ────────────────────────────────────────────────────────────
    def add_node(self, node: str) -> None:
        """Add ``node`` to the ring (idempotent)."""
        node = str(node)
        with self._lock:
            self._add_locked(node)

    def remove_node(self, node: str) -> None:
        """Remove ``node`` from the ring. Raises :class:`NodeNotFoundError`."""
        node = str(node)
        with self._lock:
            if node not in self._nodes:
                raise NodeNotFoundError(node)
            self._nodes.discard(node)
            self._ring = {p: n for p, n in self._ring.items() if n != node}
            self._sorted = sorted(self._ring)

    def clear(self) -> None:
        """Reset the ring to empty."""
        with self._lock:
            self._ring.clear()
            self._sorted = []
            self._nodes.clear()

    # ── lookup ────────────────────────────────────────────────────────────────
    def get_node(self, key: str) -> str | None:
        """Return the node that owns ``key``, or None if the ring is empty."""
        key = str(key)
        with self._lock:
            if not self._sorted:
                return None
            idx = bisect.bisect(self._sorted, self._hash(key))
            if idx == len(self._sorted):
                idx = 0  # wrap around the ring
            return self._ring[self._sorted[idx]]

    def get_nodes(self, key: str, count: int) -> list[str]:
        """Return up to ``count`` distinct nodes clockwise from ``key`` (for replication)."""
        key = str(key)
        with self._lock:
            if not self._sorted or count <= 0:
                return []
            total = len(self._sorted)
            start = bisect.bisect(self._sorted, self._hash(key))
            result: list[str] = []
            seen: set[str] = set()
            for offset in range(total):
                node = self._ring[self._sorted[(start + offset) % total]]
                if node not in seen:
                    seen.add(node)
                    result.append(node)
                    if len(result) >= count or len(seen) >= len(self._nodes):
                        break
            return result

    # ── introspection ─────────────────────────────────────────────────────────
    def nodes(self) -> list[str]:
        """All physical node names, sorted."""
        with self._lock:
            return sorted(self._nodes)

    def has_node(self, node: str) -> bool:
        with self._lock:
            return str(node) in self._nodes

    def distribution(self, keys: Iterable[str]) -> dict[str, int]:
        """Count how many of ``keys`` land on each node (for balance inspection)."""
        counts: dict[str, int] = {}
        for key in keys:
            node = self.get_node(key)
            if node is not None:
                counts[node] = counts.get(node, 0) + 1
        return counts

    def stats(self) -> dict:
        """JSON-serialisable snapshot of the ring's configuration and state."""
        with self._lock:
            return {
                "nodes": sorted(self._nodes),
                "node_count": len(self._nodes),
                "replicas": self._replicas,
                "virtual_points": len(self._sorted),
            }
