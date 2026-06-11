"""Phase 165 — Sovereign Heavy-Light Decomposition (Sleator & Tarjan, 1983).

The platform's first **tree path-aggregate** structure. It decomposes a rooted tree into *heavy
chains* — each node links to its largest-subtree child — assigns every node a contiguous ``pos`` so
each chain (and each subtree) is a contiguous range, and lays a point-update **segment tree** over
those positions.

* `path_sum(u, v)` / `path_max(u, v)` — aggregate over the `u`–`v` path in `O(log²n)`: repeatedly
  query the segment for the deeper chain head→node span and jump to that head's parent until both
  nodes share a chain.
* `update(node, value)` — `O(log n)` point update.
* `subtree_sum(v)` — `O(log n)` over the contiguous range `[pos[v], pos[v] + size[v] − 1]`.

This is distinct from Binary Lifting/P161 (ancestor queries, no aggregates) and from every array
segment tree (no tree structure). The decomposition uses **iterative** DFS (chain trees can be
`O(n)` deep, so no recursion) and an iterative bottom-up segment tree carrying both sum and max.
Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

_NEG_INF = float("-inf")


class HeavyLightError(Exception):
    """Raised for an invalid heavy-light operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class HeavyLight:
    """Heavy-light decomposition + segment tree: O(log^2 n) path-sum/path-max, O(log n) update."""

    def __init__(self, parents: Any = None, values: Any = None) -> None:
        self._lock = threading.Lock()
        self._clear()
        if parents is not None:
            self.build(parents, values)

    def _clear(self) -> None:
        self._n = 0
        self._parent: list[int] = []
        self._depth: list[int] = []
        self._size: list[int] = []
        self._head: list[int] = []
        self._pos: list[int] = []
        self._sum: list = []  # segment tree (sum), 2*n
        self._max: list = []  # segment tree (max), 2*n

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, parents: Any, values: Any = None) -> None:
        """(Re)build from ``parents`` (single rooted tree; ``parents[v]`` = parent or ``-1``)."""
        try:
            par = list(parents)
        except TypeError as exc:
            raise HeavyLightError("parents must be iterable") from exc
        n = len(par)
        if n == 0:
            with self._lock:
                self._clear()
            return
        for p in par:
            if not _is_int(p) or not (-1 <= p < n):
                raise HeavyLightError(f"each parent must be an int in [-1, {n})")
        for v, p in enumerate(par):
            if p == v:
                raise HeavyLightError(f"node {v} cannot be its own parent")
        if values is None:
            vals = [0] * n
        else:
            vals = list(values)
            if len(vals) != n:
                raise HeavyLightError("values length must match parents length")
            for x in vals:
                if not _is_num(x):
                    raise HeavyLightError("every value must be a number")
        with self._lock:
            self._clear()
            self._n = n
            children: list[list[int]] = [[] for _ in range(n)]
            roots = []
            for v, p in enumerate(par):
                if p == -1:
                    roots.append(v)
                else:
                    children[p].append(v)
            if len(roots) != 1:
                raise HeavyLightError(f"expected exactly one root, found {len(roots)}")
            root = roots[0]
            depth = [0] * n
            order = []
            dq = deque([root])
            seen = 0
            while dq:
                u = dq.popleft()
                order.append(u)
                seen += 1
                for c in children[u]:
                    depth[c] = depth[u] + 1
                    dq.append(c)
            if seen != n:
                raise HeavyLightError("parents form a disconnected graph or cycle")
            # subtree sizes + heavy child (reverse BFS order = children before parents)
            size = [1] * n
            heavy = [-1] * n
            for u in reversed(order):
                p = par[u]
                if p != -1:
                    size[p] += size[u]
            for u in order:
                best = -1
                best_sz = 0
                for c in children[u]:
                    if size[c] > best_sz:
                        best_sz = size[c]
                        best = c
                heavy[u] = best
            # iterative decomposition: head + contiguous pos (heavy child contiguous with parent)
            head = [0] * n
            pos = [0] * n
            timer = 0
            stack = [(root, root)]
            while stack:
                v, h = stack.pop()
                head[v] = h
                pos[v] = timer
                timer += 1
                for c in children[v]:
                    if c != heavy[v]:
                        stack.append((c, c))
                if heavy[v] != -1:
                    stack.append((heavy[v], h))
            # base array by position, build segment tree (sum + max), size n
            base = [0] * n
            for v in range(n):
                base[pos[v]] = vals[v]
            seg_sum = [0] * (2 * n)
            seg_max = [_NEG_INF] * (2 * n)
            for i in range(n):
                seg_sum[n + i] = base[i]
                seg_max[n + i] = base[i]
            for i in range(n - 1, 0, -1):
                seg_sum[i] = seg_sum[2 * i] + seg_sum[2 * i + 1]
                seg_max[i] = max(seg_max[2 * i], seg_max[2 * i + 1])
            self._parent = par
            self._depth = depth
            self._size = size
            self._head = head
            self._pos = pos
            self._sum = seg_sum
            self._max = seg_max

    # ── segment-tree helpers (over positions) ────────────────────────────────────────────
    def _seg_update(self, i: int, val: float) -> None:
        n = self._n
        i += n
        self._sum[i] = val
        self._max[i] = val
        i >>= 1
        while i:
            self._sum[i] = self._sum[2 * i] + self._sum[2 * i + 1]
            self._max[i] = max(self._max[2 * i], self._max[2 * i + 1])
            i >>= 1

    def _seg_sum(self, l: int, r: int) -> float:
        n = self._n
        res = 0
        l += n
        r += n + 1
        while l < r:
            if l & 1:
                res += self._sum[l]
                l += 1
            if r & 1:
                r -= 1
                res += self._sum[r]
            l >>= 1
            r >>= 1
        return res

    def _seg_max(self, l: int, r: int) -> float:
        n = self._n
        res = _NEG_INF
        l += n
        r += n + 1
        while l < r:
            if l & 1:
                res = max(res, self._max[l])
                l += 1
            if r & 1:
                r -= 1
                res = max(res, self._max[r])
            l >>= 1
            r >>= 1
        return res

    # ── update ───────────────────────────────────────────────────────────────────────────
    def _check_node(self, v: Any) -> None:
        if not _is_int(v):
            raise HeavyLightError("node must be an int")
        if not (0 <= v < self._n):
            raise HeavyLightError(f"node must be in [0, {self._n})")

    def update(self, node: int, value: float) -> None:
        """Set ``node``'s value (point update)."""
        if not _is_num(value):
            raise HeavyLightError("value must be a number")
        with self._lock:
            self._check_node(node)
            self._seg_update(self._pos[node], value)

    # ── path queries ───────────────────────────────────────────────────────────────────────
    def path_sum(self, u: int, v: int) -> float:
        """Sum of node values on the ``u``–``v`` path (inclusive)."""
        with self._lock:
            self._check_node(u)
            self._check_node(v)
            res = 0
            while self._head[u] != self._head[v]:
                if self._depth[self._head[u]] < self._depth[self._head[v]]:
                    u, v = v, u
                hu = self._head[u]
                res += self._seg_sum(self._pos[hu], self._pos[u])
                u = self._parent[hu]
            lo = min(self._pos[u], self._pos[v])
            hi = max(self._pos[u], self._pos[v])
            res += self._seg_sum(lo, hi)
            return res

    def path_max(self, u: int, v: int) -> float:
        """Maximum node value on the ``u``–``v`` path (inclusive)."""
        with self._lock:
            self._check_node(u)
            self._check_node(v)
            res = _NEG_INF
            while self._head[u] != self._head[v]:
                if self._depth[self._head[u]] < self._depth[self._head[v]]:
                    u, v = v, u
                hu = self._head[u]
                res = max(res, self._seg_max(self._pos[hu], self._pos[u]))
                u = self._parent[hu]
            lo = min(self._pos[u], self._pos[v])
            hi = max(self._pos[u], self._pos[v])
            res = max(res, self._seg_max(lo, hi))
            return res

    def subtree_sum(self, v: int) -> float:
        """Sum of node values in the subtree rooted at ``v``."""
        with self._lock:
            self._check_node(v)
            return self._seg_sum(self._pos[v], self._pos[v] + self._size[v] - 1)

    def depth(self, v: int) -> int:
        """Depth of ``v`` (root = 0)."""
        with self._lock:
            self._check_node(v)
            return self._depth[v]

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

    def stats(self) -> dict:
        """Summary: ``size`` / ``total`` / ``max`` / ``num_chains``."""
        with self._lock:
            if self._n == 0:
                return {"size": 0, "total": 0, "max": None, "num_chains": 0}
            num_chains = sum(1 for v in range(self._n) if self._head[v] == v)
            return {
                "size": self._n,
                "total": self._sum[1] if self._n else 0,
                "max": self._max[1],
                "num_chains": num_chains,
            }
