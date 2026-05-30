"""Phase 82 — Sovereign Union-Find (disjoint-set forest).

Tracks a partition of ``n`` elements into disjoint sets and answers
connectivity queries — "are a and b in the same component?" — in effectively
constant amortised time. Two optimisations combine to give the near-O(α(n))
bound (α = inverse Ackermann, ≤ 4 for any practical n):

* **Union by rank** — the shorter tree is hung under the taller one, keeping
  trees shallow. ``rank`` is an upper bound on tree height (the canonical
  union heuristic for a path-compressed forest, distinct from the element
  count tracked separately for :meth:`component_size`).
* **Path halving** — :meth:`find` is iterative and, on the way to the root,
  points every other node at its grandparent, flattening the tree as a side
  effect of the query.

Elements are 1-based (``1..n``). Pure stdlib; thread-safe via a single
non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import threading


class UnionFind:
    """A 1-indexed disjoint-set forest with union-by-rank + path halving."""

    def __init__(self, size: int) -> None:
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            raise ValueError("size must be a positive integer")
        self._n = size
        self._parent = list(range(size + 1))   # 1-indexed; slot 0 unused
        self._rank = [0] * (size + 1)
        self._comp = [1] * (size + 1)           # element count per root
        self._count = size                       # number of disjoint sets
        self._largest = 1
        self._lock = threading.Lock()

    # ── bounds (assume lock held) ────────────────────────────────────────────
    def _check(self, a, name: str = "element") -> None:
        if not isinstance(a, int) or isinstance(a, bool):
            raise ValueError(f"{name} must be an integer")
        if not 1 <= a <= self._n:
            raise ValueError(f"{name} {a} out of bounds [1, {self._n}]")

    def _find_locked(self, a: int) -> int:
        while self._parent[a] != a:
            self._parent[a] = self._parent[self._parent[a]]   # path halving
            a = self._parent[a]
        return a

    # ── operations ────────────────────────────────────────────────────────────
    def find(self, a: int) -> int:
        """Return the representative (root) of ``a``'s component."""
        with self._lock:
            self._check(a)
            return self._find_locked(a)

    def union(self, a: int, b: int) -> bool:
        """Merge the components of ``a`` and ``b``.

        Returns True if they were distinct (a merge happened), False if they
        were already connected (a no-op, including a self-union).
        """
        with self._lock:
            self._check(a, "a")
            self._check(b, "b")
            ra, rb = self._find_locked(a), self._find_locked(b)
            if ra == rb:
                return False
            if self._rank[ra] < self._rank[rb]:
                ra, rb = rb, ra
            self._parent[rb] = ra
            self._comp[ra] += self._comp[rb]
            if self._rank[ra] == self._rank[rb]:
                self._rank[ra] += 1
            self._count -= 1
            if self._comp[ra] > self._largest:
                self._largest = self._comp[ra]
            return True

    def connected(self, a: int, b: int) -> bool:
        """True if ``a`` and ``b`` belong to the same component."""
        with self._lock:
            self._check(a, "a")
            self._check(b, "b")
            return self._find_locked(a) == self._find_locked(b)

    def component_size(self, a: int) -> int:
        """Number of elements in ``a``'s component."""
        with self._lock:
            self._check(a)
            return self._comp[self._find_locked(a)]

    def component_count(self) -> int:
        """Current number of disjoint components."""
        with self._lock:
            return self._count

    def reset(self) -> None:
        """Restore ``n`` singleton components."""
        with self._lock:
            self._parent = list(range(self._n + 1))
            self._rank = [0] * (self._n + 1)
            self._comp = [1] * (self._n + 1)
            self._count = self._n
            self._largest = 1

    # ── introspection ─────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        with self._lock:
            return self._n

    def stats(self) -> dict:
        """JSON-serialisable snapshot: element count, components, largest set."""
        with self._lock:
            return {
                "size": self._n,
                "components": self._count,
                "largest_component": self._largest,
            }
