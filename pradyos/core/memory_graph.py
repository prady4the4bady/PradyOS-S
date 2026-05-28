from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.snapshot_store import SnapshotStore


@dataclass
class GraphNode:
    name: str
    metadata: dict
    created_at: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


@dataclass
class GraphEdge:
    src: str
    dst: str
    relation: str
    weight: float
    created_at: float

    def to_dict(self) -> dict:
        return {
            "src": self.src,
            "dst": self.dst,
            "relation": self.relation,
            "weight": self.weight,
            "created_at": self.created_at,
        }


class MemoryGraph:
    _NS = "memory_graph"
    _KEY = "graph_state"

    def __init__(self, snapshot_store: "SnapshotStore | None" = None) -> None:
        self._store = snapshot_store
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._lock = threading.Lock()
        if self._store is not None:
            self._load()

    # ── public API ───────────────────────────────────────────────────────────

    def add_node(self, name: str, metadata: dict | None = None) -> GraphNode:
        meta = dict(metadata) if metadata else {}
        with self._lock:
            existing = self._nodes.get(name)
            if existing is not None:
                existing.metadata = meta
                node = existing
            else:
                node = GraphNode(name=name, metadata=meta, created_at=time.time())
                self._nodes[name] = node
        self._save()
        return node

    def add_edge(
        self,
        src: str,
        dst: str,
        relation: str,
        weight: float = 1.0,
    ) -> GraphEdge:
        with self._lock:
            if src not in self._nodes:
                self._nodes[src] = GraphNode(name=src, metadata={}, created_at=time.time())
            if dst not in self._nodes:
                self._nodes[dst] = GraphNode(name=dst, metadata={}, created_at=time.time())

            for edge in self._edges:
                if edge.src == src and edge.dst == dst and edge.relation == relation:
                    edge.weight = weight
                    self._save_locked()
                    return edge

            edge = GraphEdge(
                src=src, dst=dst, relation=relation,
                weight=weight, created_at=time.time(),
            )
            self._edges.append(edge)
            self._save_locked()
            return edge

    def get_node(self, name: str) -> GraphNode | None:
        with self._lock:
            return self._nodes.get(name)

    def get_neighbors(
        self,
        name: str,
        relation: str | None = None,
    ) -> list[GraphNode]:
        with self._lock:
            if name not in self._nodes:
                return []
            out: list[GraphNode] = []
            seen: set[str] = set()
            for edge in self._edges:
                if edge.src != name:
                    continue
                if relation is not None and edge.relation != relation:
                    continue
                if edge.dst in seen:
                    continue
                target = self._nodes.get(edge.dst)
                if target is not None:
                    out.append(target)
                    seen.add(edge.dst)
            return out

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        with self._lock:
            if src == dst and src in self._nodes:
                return [src]
            if src not in self._nodes or dst not in self._nodes:
                return None

            # Build adjacency on the fly
            adj: dict[str, list[str]] = {}
            for edge in self._edges:
                adj.setdefault(edge.src, []).append(edge.dst)

            queue: deque[tuple[str, list[str]]] = deque()
            queue.append((src, [src]))
            visited: set[str] = {src}

            while queue:
                node, path = queue.popleft()
                for nxt in adj.get(node, []):
                    if nxt == dst:
                        return path + [nxt]
                    if nxt in visited:
                        continue
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))

            return None

    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    def edge_count(self) -> int:
        with self._lock:
            return len(self._edges)

    # ── persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._store is None:
            return
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        """Caller already holds self._lock."""
        if self._store is None:
            return
        try:
            data = {
                "nodes": [n.to_dict() for n in self._nodes.values()],
                "edges": [e.to_dict() for e in self._edges],
            }
            self._store.save(self._NS, self._KEY, data)
        except Exception:
            pass

    def _load(self) -> None:
        if self._store is None:
            return
        try:
            snap = self._store.get(self._NS, self._KEY)
        except Exception:
            return
        if snap is None:
            return
        data = snap.data if hasattr(snap, "data") else snap
        nodes_raw = data.get("nodes", []) if isinstance(data, dict) else []
        edges_raw = data.get("edges", []) if isinstance(data, dict) else []
        for n in nodes_raw:
            try:
                self._nodes[n["name"]] = GraphNode(
                    name=n["name"],
                    metadata=dict(n.get("metadata") or {}),
                    created_at=float(n.get("created_at") or time.time()),
                )
            except (KeyError, TypeError):
                continue
        for e in edges_raw:
            try:
                self._edges.append(GraphEdge(
                    src=e["src"],
                    dst=e["dst"],
                    relation=e["relation"],
                    weight=float(e.get("weight", 1.0)),
                    created_at=float(e.get("created_at") or time.time()),
                ))
            except (KeyError, TypeError):
                continue
