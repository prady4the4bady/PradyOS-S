"""Phase 17A — Sovereign Memory Graph.

A thread-safe, bounded knowledge graph for PRADY OS.  Stores facts,
relationships, and inferences about campaigns, tasks, agents, and system
state.  Queryable via Python API and exposed over HTTP in Phase 17B.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """A single vertex in the sovereign knowledge graph."""

    kind: str        # e.g. "campaign", "task", "agent", "fact"
    label: str       # human-readable name
    attributes: dict = field(default_factory=dict)
    node_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "attributes": dict(self.attributes),
            "created_ts": self.created_ts,
        }


@dataclass
class GraphEdge:
    """A directed edge connecting two nodes in the knowledge graph."""

    src_id: str      # source node_id
    dst_id: str      # destination node_id
    relation: str    # e.g. "depends_on", "produced_by", "inferred_from"
    weight: float = 1.0
    attributes: dict = field(default_factory=dict)
    edge_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "src_id": self.src_id,
            "dst_id": self.dst_id,
            "relation": self.relation,
            "weight": self.weight,
            "attributes": dict(self.attributes),
            "created_ts": self.created_ts,
        }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class SovereignMemoryGraph:
    """Bounded, thread-safe in-memory knowledge graph.

    Parameters
    ----------
    maxnodes:
        Maximum number of nodes to retain.  When the limit is reached the
        oldest node (by ``created_ts``) is evicted before the new one is
        inserted.  Eviction also removes all edges incident to the evicted
        node.
    maxedges:
        Maximum number of edges to retain.  When the limit is reached the
        oldest edge (by ``created_ts``) is evicted before the new one is
        inserted.
    """

    def __init__(self, maxnodes: int = 1000, maxedges: int = 5000) -> None:
        self._maxnodes = maxnodes
        self._maxedges = maxedges
        self._nodes: dict[str, GraphNode] = {}          # node_id → GraphNode
        self._edges: dict[str, GraphEdge] = {}          # edge_id → GraphEdge
        # Reverse index: src_id → list of edges leaving that node
        self._out_edges: dict[str, list[GraphEdge]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_node(
        self,
        kind: str,
        label: str,
        node_id: Optional[str] = None,
        attributes: Optional[dict] = None,
    ) -> GraphNode:
        """Add a node to the graph and return it.

        Auto-generates ``node_id`` when not provided.  If ``maxnodes`` is
        reached the oldest node is evicted first.
        """
        with self._lock:
            effective_id = node_id if node_id else uuid.uuid4().hex
            node = GraphNode(
                kind=kind,
                label=label,
                node_id=effective_id,
                attributes=attributes if attributes is not None else {},
            )
            if len(self._nodes) >= self._maxnodes:
                self._evict_oldest_node()
            self._nodes[node.node_id] = node
            return node

    def add_edge(
        self,
        src_id: str,
        dst_id: str,
        relation: str,
        edge_id: Optional[str] = None,
        weight: float = 1.0,
        attributes: Optional[dict] = None,
    ) -> GraphEdge:
        """Add a directed edge and return it.

        Auto-generates ``edge_id`` when not provided.  If ``maxedges`` is
        reached the oldest edge is evicted first.
        """
        with self._lock:
            effective_id = edge_id if edge_id else uuid.uuid4().hex
            edge = GraphEdge(
                src_id=src_id,
                dst_id=dst_id,
                relation=relation,
                edge_id=effective_id,
                weight=weight,
                attributes=attributes if attributes is not None else {},
            )
            if len(self._edges) >= self._maxedges:
                self._evict_oldest_edge()
            self._edges[edge.edge_id] = edge
            self._out_edges.setdefault(src_id, []).append(edge)
            return edge

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all incident edges.

        Returns ``True`` if the node existed, ``False`` otherwise.
        """
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            self._remove_incident_edges_locked(node_id)
            return True

    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge by id.

        Returns ``True`` if the edge existed, ``False`` otherwise.
        """
        with self._lock:
            if edge_id not in self._edges:
                return False
            edge = self._edges.pop(edge_id)
            # Remove from out_edges reverse index
            out = self._out_edges.get(edge.src_id, [])
            self._out_edges[edge.src_id] = [e for e in out if e.edge_id != edge_id]
            return True

    def clear(self) -> None:
        """Remove all nodes and edges."""
        with self._lock:
            self._nodes.clear()
            self._edges.clear()
            self._out_edges.clear()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Return the node with the given id, or ``None``."""
        with self._lock:
            return self._nodes.get(node_id)

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        """Return the edge with the given id, or ``None``."""
        with self._lock:
            return self._edges.get(edge_id)

    def neighbours(
        self,
        node_id: str,
        relation: Optional[str] = None,
    ) -> list[GraphNode]:
        """Return destination nodes reachable from *node_id*.

        Optionally filter by *relation*.  Only returns nodes that still
        exist in the graph (dangling edges are silently skipped).
        """
        with self._lock:
            out = self._out_edges.get(node_id, [])
            result: list[GraphNode] = []
            for edge in out:
                if relation is not None and edge.relation != relation:
                    continue
                dst = self._nodes.get(edge.dst_id)
                if dst is not None:
                    result.append(dst)
            return result

    def query_nodes(
        self,
        kind: Optional[str] = None,
        label: Optional[str] = None,
    ) -> list[GraphNode]:
        """Return nodes matching all provided filters (``None`` = wildcard).

        Results are sorted most-recently-created first.
        """
        with self._lock:
            nodes = list(self._nodes.values())
        # Filter
        if kind is not None:
            nodes = [n for n in nodes if n.kind == kind]
        if label is not None:
            nodes = [n for n in nodes if n.label == label]
        # Sort newest first
        nodes.sort(key=lambda n: n.created_ts, reverse=True)
        return nodes

    def stats(self) -> dict:
        """Return ``{"nodes": int, "edges": int}``."""
        with self._lock:
            return {"nodes": len(self._nodes), "edges": len(self._edges)}

    # ------------------------------------------------------------------
    # Internal helpers (must be called while lock is held)
    # ------------------------------------------------------------------

    def _evict_oldest_node(self) -> None:
        """Evict the node with the smallest ``created_ts`` (lock must be held)."""
        if not self._nodes:
            return
        oldest_id = min(self._nodes, key=lambda nid: self._nodes[nid].created_ts)
        del self._nodes[oldest_id]
        self._remove_incident_edges_locked(oldest_id)

    def _evict_oldest_edge(self) -> None:
        """Evict the edge with the smallest ``created_ts`` (lock must be held)."""
        if not self._edges:
            return
        oldest_id = min(self._edges, key=lambda eid: self._edges[eid].created_ts)
        edge = self._edges.pop(oldest_id)
        out = self._out_edges.get(edge.src_id, [])
        self._out_edges[edge.src_id] = [e for e in out if e.edge_id != oldest_id]

    def _remove_incident_edges_locked(self, node_id: str) -> None:
        """Remove every edge where src or dst is *node_id* (lock must be held)."""
        # Collect edge_ids to remove
        to_remove = [
            eid for eid, e in self._edges.items()
            if e.src_id == node_id or e.dst_id == node_id
        ]
        for eid in to_remove:
            edge = self._edges.pop(eid)
            out = self._out_edges.get(edge.src_id, [])
            self._out_edges[edge.src_id] = [e for e in out if e.edge_id != eid]
        # Clean up any now-empty out_edges entry for this node
        self._out_edges.pop(node_id, None)
