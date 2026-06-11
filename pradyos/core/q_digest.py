"""Phase 105 — Sovereign Q-Digest (Shrivastava, Buragohain, Agrawal & Suri, 2004).

A **mergeable quantile sketch** for streaming percentile estimation. A Q-Digest
lays a *complete binary tree* over the value universe ``[0, value_range)`` — the
root spans the whole universe, each leaf is a single value — and keeps only the
nodes whose counts matter, collapsing light subtrees into their parents. The
result answers approximate rank / quantile queries in bounded space ``O(k·log σ)``
(``σ = value_range``) and merges two digests by node-wise addition.

Tree layout (heap numbering, 1-indexed)
---------------------------------------
The universe is rounded up to a power-of-two ``capacity ≥ value_range`` so the
tree is complete. Node ``1`` is the root spanning ``[0, capacity)``; node ``i``'s
children are ``2i`` (left) and ``2i+1`` (right); the leaf for value ``x`` lives at
id ``capacity + x`` and spans ``[x, x+1)``. A node ``i`` at depth ``d`` spans a
window of width ``capacity / 2**d``. Only nodes with a positive count are stored
(a ``dict`` ``{node_id: count}``) — the empty regions of a sparse universe cost
nothing, which is why a universe of 65536 stays cheap when the data lives in a
small sub-range.

Compression (the Q-Digest property)
------------------------------------
With compression factor ``k`` and ``n`` total elements the threshold is
``⌊n/k⌋``. After every ``add`` / ``merge`` the tree is swept **bottom-up**: for a
node ``v``, its sibling ``s`` and parent ``p``, if
``count(v) + count(s) + count(p) < ⌊n/k⌋`` the two children are *merged upward*
into the parent and deleted. This enforces the digest property — no light triple
survives — and as a byproduct keeps every non-leaf node at ``count ≤ ⌊n/k⌋``,
bounding the digest to ``O(k·log σ)`` nodes. Heavy values legitimately keep
high-count leaves; only sparse, low-count regions get coarsened, so the data
region is resolved to fine buckets while empty regions vanish.

Quantile / rank
---------------
``quantile(q)`` walks the stored nodes in increasing order of their upper
boundary, accumulating counts until the running sum reaches ``q·n``, and reports
that node's maximum value — so ``≈ q·n`` elements are ``≤`` the answer.
``rank(value)`` sums the counts of every node lying entirely at or below
``value``.

The structure is fully deterministic (no randomness — the ``seed`` is carried for
API parity with the other sovereign sketches and reported in ``stats``). Pure
stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import threading
from typing import Any


class QDigestError(Exception):
    """Raised for an invalid Q-Digest configuration / operation. Offending value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class QDigest:
    """Compressed binary-tree quantile sketch over the universe ``[0, value_range)``."""

    def __init__(
        self, compression_factor: int = 100, value_range: int = 65536, seed: int = 0
    ) -> None:
        self._validate(compression_factor, value_range, seed)
        self._k = compression_factor
        self._value_range = value_range
        self._seed = seed
        self._capacity = self._next_pow2(value_range)
        self._levels = self._capacity.bit_length() - 1  # depth of the leaf level
        self._lock = threading.Lock()
        self._init_state()

    # ── validation / construction helpers ───────────────────────────────────────────
    @staticmethod
    def _validate(compression_factor: Any, value_range: Any, seed: Any) -> None:
        if not _is_pos_int(compression_factor):
            raise QDigestError(compression_factor)
        if not (_is_pos_int(value_range) and value_range >= 2):
            raise QDigestError(value_range)
        if not _is_int(seed):
            raise QDigestError(seed)

    @staticmethod
    def _next_pow2(n: int) -> int:
        cap = 1
        while cap < n:
            cap <<= 1
        return cap

    def _init_state(self) -> None:
        self._tree: dict[int, int] = {}
        self._total = 0

    # ── geometry (pure) ──────────────────────────────────────────────────────────────
    def _node_range(self, node_id: int) -> tuple[int, int]:
        """Return the ``[lower, upper)`` value window covered by ``node_id``."""
        depth = node_id.bit_length() - 1
        span = self._capacity >> depth
        pos = node_id - (1 << depth)
        lower = pos * span
        return lower, lower + span

    # ── compression (the digest property) ─────────────────────────────────────────────
    def _compress(self) -> None:
        threshold = self._total // self._k
        if threshold < 1:
            return  # n < k → keep full resolution; no light triple can fall below 0
        by_level: dict[int, list[int]] = {}
        for nid in self._tree:
            by_level.setdefault(nid.bit_length() - 1, []).append(nid)
        if not by_level:
            return
        for level in range(max(by_level), 0, -1):
            queue = by_level.get(level, [])
            idx = 0
            while idx < len(queue):
                nid = queue[idx]
                idx += 1
                if nid not in self._tree:
                    continue
                parent = nid >> 1
                sibling = nid ^ 1
                triple = (
                    self._tree.get(nid, 0) + self._tree.get(sibling, 0) + self._tree.get(parent, 0)
                )
                if triple < threshold:
                    merged = self._tree.pop(nid, 0) + self._tree.pop(sibling, 0)
                    if merged:
                        self._tree[parent] = self._tree.get(parent, 0) + merged
                        by_level.setdefault(level - 1, []).append(parent)

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, value: int, count: int = 1) -> None:
        """Add ``count`` occurrences of ``value`` (in ``[0, value_range)``), then recompress."""
        if not (_is_int(value) and 0 <= value < self._value_range):
            raise QDigestError(value)
        if not _is_pos_int(count):
            raise QDigestError(count)
        with self._lock:
            leaf = self._capacity + value
            self._tree[leaf] = self._tree.get(leaf, 0) + count
            self._total += count
            self._compress()

    def quantile(self, q: float) -> int:
        """Return value ``v`` such that ``≈ q·n`` elements are ``≤ v`` (``q`` strictly in (0, 1))."""
        if isinstance(q, bool) or not isinstance(q, int | float):
            raise QDigestError(q)
        if not (0.0 < q < 1.0):
            raise QDigestError(q)
        with self._lock:
            if self._total == 0:
                raise QDigestError("empty")
            target = q * self._total
            nodes = sorted(
                self._tree.items(),
                key=lambda kv: (self._node_range(kv[0])[1], self._node_range(kv[0])[0]),
            )
            cum = 0
            upper = self._value_range
            for nid, cnt in nodes:
                cum += cnt
                upper = self._node_range(nid)[1]
                if cum >= target:
                    return upper - 1
            return upper - 1

    def rank(self, value: int) -> int:
        """Estimated number of elements ``≤ value`` (counts nodes lying entirely at/below it)."""
        if not _is_int(value):
            raise QDigestError(value)
        with self._lock:
            total = 0
            for nid, cnt in self._tree.items():
                if self._node_range(nid)[1] - 1 <= value:
                    total += cnt
            return total

    def merge(self, other: QDigest) -> QDigest:
        """Merge ``other`` (same universe) into this digest: node-wise add, then recompress."""
        if not isinstance(other, QDigest):
            raise QDigestError(other)
        with other._lock:
            if other._value_range != self._value_range:
                raise QDigestError(other._value_range)
            other_tree = dict(other._tree)
            other_total = other._total
        with self._lock:
            for nid, cnt in other_tree.items():
                self._tree[nid] = self._tree.get(nid, 0) + cnt
            self._total += other_total
            self._compress()
        return self

    def reset(
        self,
        compression_factor: int | None = None,
        value_range: int | None = None,
        seed: int | None = None,
    ) -> None:
        """Clear the tree; optionally reconfigure ``compression_factor`` / ``value_range`` / ``seed``."""
        with self._lock:
            nk = self._k if compression_factor is None else compression_factor
            nvr = self._value_range if value_range is None else value_range
            ns = self._seed if seed is None else seed
            self._validate(nk, nvr, ns)
            self._k, self._value_range, self._seed = nk, nvr, ns
            self._capacity = self._next_pow2(nvr)
            self._levels = self._capacity.bit_length() - 1
            self._init_state()

    def __len__(self) -> int:
        with self._lock:
            return self._total

    @property
    def compression_factor(self) -> int:
        return self._k

    @property
    def value_range(self) -> int:
        return self._value_range

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_nodes(self) -> int:
        with self._lock:
            return len(self._tree)

    @property
    def total_count(self) -> int:
        with self._lock:
            return self._total

    def stats(self) -> dict:
        """Summary: ``compression_factor`` / ``value_range`` / ``total_count`` (n) /
        ``num_nodes`` / ``theoretical_max_nodes`` (the ``O(k·log σ)`` space bound)."""
        with self._lock:
            return {
                "compression_factor": self._k,
                "value_range": self._value_range,
                "total_count": self._total,
                "num_nodes": len(self._tree),
                "theoretical_max_nodes": self._k * self._levels,
            }
