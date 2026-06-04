"""Phase 161 — Sovereign Binary Lifting (LCA / k-th ancestor).

A **rooted-tree ancestor-query structure**. Given a rooted forest as a parent array, it
precomputes a **jump table** `up[k][v]` = the `2ᵏ`-th ancestor of `v` in `O(n log n)`, then answers
each of these in `O(log n)`:

* `lca(u, v)` — lowest common ancestor (``None`` if `u`, `v` lie in different trees),
* `kth_ancestor(v, k)` — the `k`-th ancestor of `v` (``None`` if `k` exceeds its depth),
* `depth(v)` — distance from `v` to its root,
* `is_ancestor(u, v)` — whether `u` lies on the root→`v` path (reflexive).

A query for `2ᵏ`-th ancestor jumps directly via `up[k]`; `kth_ancestor` decomposes `k` into its set
bits; `lca` equalizes depths then lifts both nodes in lockstep from the highest level down. This is
the platform's first *tree-query-preprocessing* structure — it operates on a *given* rooted forest
rather than maintaining an ordered set or heap, distinct from every search tree and priority queue
shipped so far.

Build does a BFS from the roots (detecting cycles / invalid parents); the jump table has
`⌈log₂ n⌉` levels, so every operation is iterative and structurally bounded. Pure stdlib;
thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

import threading

_NIL = -1


class BinaryLiftingError(Exception):
    """Raised for an invalid binary-lifting operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class BinaryLifting:
    """Rooted-forest ancestor queries: O(log n) lca / kth_ancestor via a 2^k-ancestor jump table."""

    def __init__(self, parents: Any = None) -> None:
        self._lock = threading.Lock()
        self._clear()
        if parents is not None:
            self.build(parents)

    def _clear(self) -> None:
        self._n = 0
        self._log = 0
        self._depth: list[int] = []
        self._up: list[list[int]] = []        # up[k][v] = 2^k-th ancestor of v, or _NIL

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, parents: Any) -> None:
        """(Re)build from ``parents`` (``parents[v]`` = parent of ``v``, or ``-1`` for a root)."""
        try:
            par = list(parents)
        except TypeError as exc:
            raise BinaryLiftingError("parents must be iterable") from exc
        n = len(par)
        for p in par:
            if not _is_int(p) or not (-1 <= p < n):
                raise BinaryLiftingError(f"each parent must be an int in [-1, {n})")
        for v, p in enumerate(par):
            if p == v:
                raise BinaryLiftingError(f"node {v} cannot be its own parent")
        with self._lock:
            self._clear()
            if n == 0:
                return
            children: list[list[int]] = [[] for _ in range(n)]
            roots = []
            for v, p in enumerate(par):
                if p == -1:
                    roots.append(v)
                else:
                    children[p].append(v)
            if not roots:
                raise BinaryLiftingError("parents form a cycle (no root)")
            depth = [-1] * n
            dq = deque()
            for r in roots:
                depth[r] = 0
                dq.append(r)
            seen = 0
            while dq:
                u = dq.popleft()
                seen += 1
                for c in children[u]:
                    depth[c] = depth[u] + 1
                    dq.append(c)
            if seen != n:
                raise BinaryLiftingError("parents form a cycle")
            log = max(1, (n - 1).bit_length())
            up = [[ _NIL] * n for _ in range(log)]
            up[0] = list(par)
            for k in range(1, log):
                upk = up[k]
                upk1 = up[k - 1]
                for v in range(n):
                    mid = upk1[v]
                    upk[v] = upk1[mid] if mid != _NIL else _NIL
            self._n = n
            self._log = log
            self._depth = depth
            self._up = up

    # ── helpers (read-only; safe to call under or without the lock) ──────────────────────
    def _kth(self, v: int, k: int) -> int:
        if k > self._depth[v]:
            return _NIL
        cur = v
        bit = 0
        while k:
            if k & 1:
                cur = self._up[bit][cur]
                if cur == _NIL:
                    return _NIL
            k >>= 1
            bit += 1
        return cur

    def _check_node(self, v: Any) -> None:
        if not _is_int(v):
            raise BinaryLiftingError("node must be an int")
        if not (0 <= v < self._n):
            raise BinaryLiftingError(f"node must be in [0, {self._n})")

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def depth(self, v: int) -> int:
        """Depth of ``v`` (root = 0)."""
        with self._lock:
            self._check_node(v)
            return self._depth[v]

    def kth_ancestor(self, v: int, k: int) -> Optional[int]:
        """The ``k``-th ancestor of ``v`` (``None`` if ``k`` exceeds its depth)."""
        if not _is_int(k) or k < 0:
            raise BinaryLiftingError("k must be a non-negative int")
        with self._lock:
            self._check_node(v)
            r = self._kth(v, k)
            return None if r == _NIL else r

    def lca(self, u: int, v: int) -> Optional[int]:
        """Lowest common ancestor of ``u`` and ``v`` (``None`` if in different trees)."""
        with self._lock:
            self._check_node(u)
            self._check_node(v)
            ru = self._kth(u, self._depth[u])
            rv = self._kth(v, self._depth[v])
            if ru != rv:
                return None                              # different trees
            if self._depth[u] < self._depth[v]:
                u, v = v, u
            u = self._kth(u, self._depth[u] - self._depth[v])
            if u == v:
                return u
            for k in range(self._log - 1, -1, -1):
                if self._up[k][u] != self._up[k][v]:
                    u = self._up[k][u]
                    v = self._up[k][v]
            return self._up[0][u]

    def is_ancestor(self, u: int, v: int) -> bool:
        """True iff ``u`` lies on the root→``v`` path (reflexive: ``u == v`` → True)."""
        with self._lock:
            self._check_node(u)
            self._check_node(v)
            if self._depth[u] > self._depth[v]:
                return False
            return self._kth(v, self._depth[v] - self._depth[u]) == u

    def reset(self) -> None:
        """Discard the tree."""
        with self._lock:
            self._clear()

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return self._n == 0

    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def levels(self) -> int:
        return self._log

    def stats(self) -> dict:
        """Summary: ``size`` / ``levels`` / ``max_depth`` / ``num_roots``."""
        with self._lock:
            max_depth = max(self._depth) if self._depth else 0
            num_roots = sum(1 for v in range(self._n) if self._up[0][v] == _NIL) if self._n else 0
            return {"size": self._n, "levels": self._log,
                    "max_depth": max_depth, "num_roots": num_roots}
