"""STARMAP in-memory directed typed knowledge graph.

Nodes are typed entities keyed by a unique id; edges are directed, typed
relations between nodes. Traversals (``neighbors``, ``path``, ``reachable``,
``causal_chain``) are breadth-first and depth-bounded, so they stay cheap and
predictable on the sizes a single Sovereign host accumulates.

All mutating and reading operations take a re-entrant lock, so the graph is safe
to share across the agent constellation.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any


class StarmapError(RuntimeError):
    """Base class for STARMAP failures."""


class UnknownNodeError(StarmapError):
    """Referenced a node id that is not in the graph."""


def _is_id(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Node:
    """An entity in the graph."""

    id: str
    type: str
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "attrs": dict(self.attrs)}


@dataclass(frozen=True)
class Edge:
    """A directed, typed relation ``src --rel--> dst``."""

    src: str
    rel: str
    dst: str
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "rel": self.rel, "dst": self.dst, "attrs": dict(self.attrs)}


class KnowledgeGraph:
    """A directed, typed knowledge graph with depth-bounded traversal."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        # adjacency: node id -> list of (rel, dst) and reverse (rel, src)
        self._out: dict[str, list[tuple[str, str]]] = {}
        self._in: dict[str, list[tuple[str, str]]] = {}
        # edge store keyed by (src, rel, dst) for attrs + dedupe
        self._edges: dict[tuple[str, str, str], Edge] = {}
        self._lock = threading.RLock()

    # ── mutation ─────────────────────────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str, **attrs: Any) -> Node:
        """Insert or update (merge attrs) a node; returns the stored node."""
        if not _is_id(node_id):
            raise StarmapError("node id must be a non-empty string")
        if not _is_id(node_type):
            raise StarmapError("node type must be a non-empty string")
        with self._lock:
            existing = self._nodes.get(node_id)
            merged = dict(existing.attrs) if existing else {}
            merged.update(attrs)
            node = Node(id=node_id, type=node_type, attrs=merged)
            self._nodes[node_id] = node
            self._out.setdefault(node_id, [])
            self._in.setdefault(node_id, [])
            return node

    def add_edge(
        self, src: str, rel: str, dst: str, *, create_missing: bool = False, **attrs: Any
    ) -> Edge:
        """Add (or update attrs of) a directed edge ``src --rel--> dst``.

        Both endpoints must already exist unless ``create_missing`` is set, in
        which case absent endpoints are created with type ``"unknown"``.
        """
        if not _is_id(rel):
            raise StarmapError("rel must be a non-empty string")
        with self._lock:
            for end in (src, dst):
                if end not in self._nodes:
                    if create_missing:
                        self.add_node(end, "unknown")
                    else:
                        raise UnknownNodeError(
                            f"unknown node {end!r} (use create_missing=True to auto-add)"
                        )
            key = (src, rel, dst)
            edge = Edge(src=src, rel=rel, dst=dst, attrs=dict(attrs))
            if key not in self._edges:
                self._out[src].append((rel, dst))
                self._in[dst].append((rel, src))
            self._edges[key] = edge
            return edge

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and every edge touching it."""
        with self._lock:
            if node_id not in self._nodes:
                return False
            for rel, dst in list(self._out.get(node_id, [])):
                self._edges.pop((node_id, rel, dst), None)
                self._in[dst] = [(r, s) for (r, s) in self._in.get(dst, []) if s != node_id]
            for rel, src in list(self._in.get(node_id, [])):
                self._edges.pop((src, rel, node_id), None)
                self._out[src] = [(r, d) for (r, d) in self._out.get(src, []) if d != node_id]
            self._out.pop(node_id, None)
            self._in.pop(node_id, None)
            self._nodes.pop(node_id, None)
            return True

    def remove_edge(self, src: str, rel: str, dst: str) -> bool:
        with self._lock:
            key = (src, rel, dst)
            if key not in self._edges:
                return False
            self._edges.pop(key)
            self._out[src] = [
                (r, d) for (r, d) in self._out.get(src, []) if not (r == rel and d == dst)
            ]
            self._in[dst] = [
                (r, s) for (r, s) in self._in.get(dst, []) if not (r == rel and s == src)
            ]
            return True

    # ── lookup ───────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Node:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                raise UnknownNodeError(f"unknown node {node_id!r}")
            return node

    def has_node(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._nodes

    def nodes(self, node_type: str | None = None) -> list[Node]:
        with self._lock:
            vals = list(self._nodes.values())
        return [n for n in vals if node_type is None or n.type == node_type]

    def edges(self, rel: str | None = None) -> list[Edge]:
        with self._lock:
            vals = list(self._edges.values())
        return [e for e in vals if rel is None or e.rel == rel]

    # ── traversal ────────────────────────────────────────────────────────────

    def neighbors(self, node_id: str, rel: str | None = None, direction: str = "out") -> list[str]:
        """Adjacent node ids. ``direction`` is ``out``, ``in`` or ``both``."""
        if direction not in ("out", "in", "both"):
            raise StarmapError("direction must be 'out', 'in' or 'both'")
        with self._lock:
            self._require(node_id)
            result: list[str] = []
            seen: set[str] = set()
            sources = []
            if direction in ("out", "both"):
                sources += [(r, d) for (r, d) in self._out.get(node_id, [])]
            if direction in ("in", "both"):
                sources += [(r, s) for (r, s) in self._in.get(node_id, [])]
            for r, other in sources:
                if (rel is None or r == rel) and other not in seen:
                    seen.add(other)
                    result.append(other)
            return result

    def reachable(self, src: str, rel: str | None = None, max_hops: int = 6) -> set[str]:
        """All node ids reachable from ``src`` within ``max_hops`` (excludes src)."""
        if max_hops < 1:
            raise StarmapError("max_hops must be >= 1")
        with self._lock:
            self._require(src)
            seen = {src}
            out = set()
            queue: deque[tuple[str, int]] = deque([(src, 0)])
            while queue:
                cur, depth = queue.popleft()
                if depth >= max_hops:
                    continue
                for r, dst in self._out.get(cur, []):
                    if rel is not None and r != rel:
                        continue
                    if dst not in seen:
                        seen.add(dst)
                        out.add(dst)
                        queue.append((dst, depth + 1))
            return out

    def path(
        self, src: str, dst: str, rel: str | None = None, max_hops: int = 6
    ) -> list[str] | None:
        """Shortest directed path ``[src, …, dst]`` (BFS), or ``None`` if none
        within ``max_hops``."""
        if max_hops < 1:
            raise StarmapError("max_hops must be >= 1")
        with self._lock:
            self._require(src)
            self._require(dst)
            if src == dst:
                return [src]
            prev: dict[str, str] = {src: src}
            queue: deque[tuple[str, int]] = deque([(src, 0)])
            while queue:
                cur, depth = queue.popleft()
                if depth >= max_hops:
                    continue
                for r, nxt in self._out.get(cur, []):
                    if rel is not None and r != rel:
                        continue
                    if nxt not in prev:
                        prev[nxt] = cur
                        if nxt == dst:
                            chain = [dst]
                            while chain[-1] != src:
                                chain.append(prev[chain[-1]])
                            return list(reversed(chain))
                        queue.append((nxt, depth + 1))
            return None

    def causal_chain(self, src: str, rel: str, max_hops: int = 6) -> list[str]:
        """Follow a single relation type forward from ``src`` as far as it goes
        (deterministically taking the first such edge at each step), e.g. a
        ``resulted_in`` chain. Returns the ordered node ids including ``src``."""
        with self._lock:
            self._require(src)
            chain = [src]
            seen = {src}
            cur = src
            for _ in range(max_hops):
                nxts = [d for (r, d) in self._out.get(cur, []) if r == rel and d not in seen]
                if not nxts:
                    break
                nxt = sorted(nxts)[0]
                chain.append(nxt)
                seen.add(nxt)
                cur = nxt
            return chain

    def subgraph(self, node_ids: Any) -> dict[str, Any]:
        """Induced subgraph over ``node_ids`` — nodes plus edges with both ends
        in the set."""
        with self._lock:
            ids = {i for i in node_ids if i in self._nodes}
            nodes = [self._nodes[i].to_dict() for i in sorted(ids)]
            edges = [e.to_dict() for (s, _r, d), e in self._edges.items() if s in ids and d in ids]
            return {"nodes": nodes, "edges": edges}

    # ── introspection ────────────────────────────────────────────────────────

    def degree(self, node_id: str) -> dict[str, int]:
        with self._lock:
            self._require(node_id)
            return {
                "out": len(self._out.get(node_id, [])),
                "in": len(self._in.get(node_id, [])),
            }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            type_counts: dict[str, int] = {}
            for n in self._nodes.values():
                type_counts[n.type] = type_counts.get(n.type, 0) + 1
            rel_counts: dict[str, int] = {}
            for e in self._edges.values():
                rel_counts[e.rel] = rel_counts.get(e.rel, 0) + 1
            return {
                "nodes": len(self._nodes),
                "edges": len(self._edges),
                "node_types": type_counts,
                "relations": rel_counts,
            }

    def reset(self) -> None:
        with self._lock:
            self._nodes.clear()
            self._out.clear()
            self._in.clear()
            self._edges.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, node_id: str) -> None:
        if node_id not in self._nodes:
            raise UnknownNodeError(f"unknown node {node_id!r}")
