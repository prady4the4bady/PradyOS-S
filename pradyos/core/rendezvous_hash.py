"""Phase 119 — Sovereign Rendezvous Hashing / HRW (Thaler & Ravishankar, 1998).

*Highest Random Weight* hashing — a distributed **key→node assignment** scheme. Like the
platform's Hash Ring (P73, consistent hashing) it spreads keys uniformly over the nodes
and reassigns only a minimal fraction of keys when the node set changes, but by an
entirely different mechanism: every key ``k`` is assigned to the node ``n`` that
**maximises a score** ``score(k, n)`` derived from ``hash(k, n)`` — the "highest random
weight". No ring, no virtual nodes: a lookup simply evaluates the score against each of
the ``N`` nodes and takes the argmax (``O(N)`` per lookup).

Two properties fall out for free:

* **Uniform load** — for a fixed key, the ``N`` scores are i.i.d., so each node is the
  maximum with probability ``1/N`` (weighted: in proportion to its weight).
* **Minimal disruption** — adding a node only captures the keys for which it becomes the
  new maximum (≈ ``1/(N+1)`` of them) and disturbs *no other* assignment; removing a node
  reassigns *only its own* keys, each to its second-best node. (Consistent hashing needs
  virtual nodes to approximate this; HRW gives it exactly.)

Weighted nodes use the standard transform ``score = −weight / ln(h)`` with ``h ∈ (0, 1)``
(a node of weight ``2w`` wins twice as often as one of weight ``w``); unweighted reduces
to ``argmax h``. ``get_replicas(key, k)`` returns the ``k`` highest-scoring nodes — the
natural way to place ``k`` replicas. The hash is a seeded BLAKE2b of ``(seed, key, node)``,
so assignments are deterministic and reproducible. Pure stdlib; thread-safe via a single
``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

_DENOM = (1 << 64) + 1  # maps a 64-bit digest into the open interval (0, 1)


class RendezvousError(Exception):
    """Raised for an invalid Rendezvous operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_pos_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and x > 0


class RendezvousHash:
    """Highest-Random-Weight (HRW) key→node assignment with weights and replicas."""

    def __init__(self, nodes: Any = None, seed: int = 0) -> None:
        if not _is_int(seed):
            raise RendezvousError(seed)
        self._seed = seed
        self._lock = threading.Lock()
        self._weights: dict[Any, float] = {}
        if nodes is not None:
            try:
                iterator = list(nodes)
            except TypeError as exc:
                raise RendezvousError(nodes) from exc
            for node in iterator:
                self._add_locked(node, 1.0)

    # ── scoring (pure) ───────────────────────────────────────────────────────────────
    def _score(self, key: Any, node: Any, weight: float) -> float:
        data = repr((self._seed, key, node)).encode("utf-8")
        digest = int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")
        h = (digest + 1) / _DENOM  # h in (0, 1), never 0 or 1
        return -weight / math.log(h)  # ln(h) < 0 → score > 0

    # ── node management ────────────────────────────────────────────────────────────────
    def _add_locked(self, node: Any, weight: float) -> None:
        if not _is_pos_number(weight):
            raise RendezvousError(weight)
        self._weights[node] = float(weight)

    def add_node(self, node: Any, weight: float = 1.0) -> None:
        """Add (or re-weight) ``node`` with a positive ``weight``."""
        with self._lock:
            self._add_locked(node, weight)

    def remove_node(self, node: Any) -> bool:
        """Remove ``node``; return True if it was present."""
        with self._lock:
            if node in self._weights:
                del self._weights[node]
                return True
            return False

    def contains(self, node: Any) -> bool:
        with self._lock:
            return node in self._weights

    def __contains__(self, node: Any) -> bool:
        return self.contains(node)

    def __len__(self) -> int:
        with self._lock:
            return len(self._weights)

    # ── assignment ─────────────────────────────────────────────────────────────────────
    def assign(self, key: Any) -> Any:
        """Return the node responsible for ``key`` (the highest-scoring node)."""
        with self._lock:
            if not self._weights:
                raise RendezvousError("no nodes")
            best_node = None
            best_score = float("-inf")
            for node, weight in self._weights.items():
                s = self._score(key, node, weight)
                # tie-break deterministically by stringified node id.
                if s > best_score or (s == best_score and str(node) < str(best_node)):
                    best_score = s
                    best_node = node
            return best_node

    def get_replicas(self, key: Any, k: int) -> list:
        """Return the ``k`` highest-scoring nodes for ``key`` (replica placement)."""
        if not _is_int(k) or k < 1:
            raise RendezvousError(k)
        with self._lock:
            if not self._weights:
                raise RendezvousError("no nodes")
            ranked = sorted(
                self._weights.items(),
                key=lambda item: (-self._score(key, item[0], item[1]), str(item[0])),
            )
            return [node for node, _w in ranked[:k]]

    def reset(self, seed: int | None = None) -> None:
        """Remove all nodes; optionally reconfigure ``seed``."""
        with self._lock:
            if seed is not None:
                if not _is_int(seed):
                    raise RendezvousError(seed)
                self._seed = seed
            self._weights = {}

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def seed(self) -> int:
        return self._seed

    @property
    def nodes(self) -> list:
        with self._lock:
            return sorted(self._weights, key=str)

    def weight_of(self, node: Any) -> float:
        with self._lock:
            if node not in self._weights:
                raise RendezvousError(node)
            return self._weights[node]

    def stats(self) -> dict:
        """Summary: ``num_nodes`` / ``nodes`` / ``total_weight`` / ``seed``."""
        with self._lock:
            return {
                "num_nodes": len(self._weights),
                "nodes": sorted(self._weights, key=str),
                "total_weight": round(sum(self._weights.values()), 6),
                "seed": self._seed,
            }
