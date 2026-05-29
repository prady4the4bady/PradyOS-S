"""Phase 70 — Sovereign Dependency Graph.

Tracks directed dependencies between named components. An edge ``a -> b`` means
"a depends on b". The graph is stored as a forward adjacency map (``_deps``:
node -> set of its direct dependencies) plus a mirror reverse map
(``_dependents``: node -> set of nodes that directly depend on it), so both
"what does X need?" and "who needs X?" are O(1) lookups.

Capabilities: add/remove edges, direct + transitive queries, DFS cycle
detection (raising :class:`CycleError` with the offending node path), a Kahn's
algorithm topological sort (whole-graph or restricted to a node's transitive
closure), and an ``impact_score`` = the count of transitive dependents.

Pure stdlib — no third-party dependencies. Thread-safe via a single
``threading.Lock``; the public surface acquires it, and internal helpers that
run under the lock never re-acquire it (the lock is non-reentrant).
"""

from __future__ import annotations

import heapq
import threading


class CycleError(Exception):
    """Raised when a cyclic dependency prevents a topological ordering.

    The ``cycle`` attribute holds the offending path as a list of node names,
    closed on itself (e.g. ``["a", "b", "c", "a"]``).
    """

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = list(cycle)
        joined = " -> ".join(self.cycle) if self.cycle else "<unknown>"
        super().__init__(f"dependency cycle detected: {joined}")


class DependencyGraph:
    """Directed dependency graph between named components (stdlib only)."""

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}        # node -> nodes it depends on
        self._dependents: dict[str, set[str]] = {}  # node -> nodes that depend on it
        self._lock = threading.Lock()

    # ── internal (callers already hold the lock) ─────────────────────────────
    def _ensure_node(self, node: str) -> None:
        if node not in self._deps:
            self._deps[node] = set()
        if node not in self._dependents:
            self._dependents[node] = set()

    def _transitive(self, start: str, adjacency: dict[str, set[str]]) -> set[str]:
        """Return every node reachable from ``start`` over ``adjacency``,
        excluding ``start`` itself. Cycle-safe via the ``seen`` guard."""
        seen: set[str] = set()
        stack = list(adjacency.get(start, set()))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adjacency.get(cur, set()))
        seen.discard(start)
        return seen

    def _find_cycle_locked(self, nodes: set[str] | None = None) -> list[str] | None:
        """DFS for a back-edge; returns a closed cycle path or None.

        When ``nodes`` is given the search is confined to that node subset
        (used to report the specific cycle that blocked a scoped topo sort).
        """
        scope = set(self._deps) if nodes is None else set(nodes)
        order = sorted(scope)
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in order}
        stack: list[str] = []

        def visit(u: str) -> list[str] | None:
            color[u] = GRAY
            stack.append(u)
            for v in sorted(self._deps.get(u, set())):
                if v not in scope:
                    continue
                if color.get(v, WHITE) == GRAY:
                    idx = stack.index(v)
                    return stack[idx:] + [v]
                if color.get(v, WHITE) == WHITE:
                    found = visit(v)
                    if found is not None:
                        return found
            stack.pop()
            color[u] = BLACK
            return None

        for n in order:
            if color[n] == WHITE:
                found = visit(n)
                if found is not None:
                    return found
        return None

    # ── mutation ──────────────────────────────────────────────────────────────
    def add_dependency(self, frm: str, to: str) -> None:
        """Record that ``frm`` depends on ``to`` (edge ``frm -> to``). Idempotent."""
        with self._lock:
            self._ensure_node(frm)
            self._ensure_node(to)
            self._deps[frm].add(to)
            self._dependents[to].add(frm)

    def remove_dependency(self, frm: str, to: str) -> bool:
        """Remove the edge ``frm -> to``. Returns True if it existed, else False.

        Nodes themselves are retained (only the edge is dropped)."""
        with self._lock:
            if frm in self._deps and to in self._deps[frm]:
                self._deps[frm].discard(to)
                self._dependents.get(to, set()).discard(frm)
                return True
            return False

    # ── queries ─────────────────────────────────────────────────────────────
    def nodes(self) -> list[str]:
        """All known node names, sorted."""
        with self._lock:
            return sorted(self._deps.keys())

    def has_node(self, node: str) -> bool:
        with self._lock:
            return node in self._deps

    def get_dependencies(self, node: str) -> list[str]:
        """Direct dependencies of ``node`` (the nodes it depends on), sorted."""
        with self._lock:
            return sorted(self._deps.get(node, set()))

    def get_dependents(self, node: str) -> list[str]:
        """Direct dependents of ``node`` (the nodes that depend on it), sorted."""
        with self._lock:
            return sorted(self._dependents.get(node, set()))

    def impact_score(self, node: str) -> int:
        """Number of distinct transitive dependents of ``node``.

        A higher score means breaking ``node`` ripples to more components."""
        with self._lock:
            return len(self._transitive(node, self._dependents))

    def topological_sort(self, start: str | None = None) -> list[str]:
        """Return nodes in dependency-first order via Kahn's algorithm.

        Each node appears only after every node it depends on. With ``start``,
        the sort is restricted to ``start`` plus its transitive dependencies.
        Ties are broken alphabetically for deterministic output. Raises
        :class:`CycleError` (carrying the offending path) if a cycle exists.
        """
        with self._lock:
            if start is None:
                node_set = set(self._deps.keys())
            else:
                node_set = self._transitive(start, self._deps)
                node_set.add(start)

            indeg: dict[str, int] = {
                n: sum(1 for d in self._deps.get(n, set()) if d in node_set)
                for n in node_set
            }
            ready = [n for n in node_set if indeg[n] == 0]
            heapq.heapify(ready)

            order: list[str] = []
            while ready:
                u = heapq.heappop(ready)
                order.append(u)
                for w in sorted(self._dependents.get(u, set())):
                    if w in node_set:
                        indeg[w] -= 1
                        if indeg[w] == 0:
                            heapq.heappush(ready, w)

            if len(order) != len(node_set):
                raise CycleError(self._find_cycle_locked(node_set) or [])
            return order

    def find_cycle(self) -> list[str] | None:
        """Return a cycle path (closed on itself) if the graph has one, else None."""
        with self._lock:
            return self._find_cycle_locked()

    def describe(self, node: str) -> dict:
        """A JSON-serialisable snapshot of ``node``'s position in the graph."""
        return {
            "node": node,
            "exists": self.has_node(node),
            "dependencies": self.get_dependencies(node),
            "dependents": self.get_dependents(node),
            "impact_score": self.impact_score(node),
        }
