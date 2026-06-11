"""STARMAP — graph intelligence plane (entities, relations, causal recall).

Plane 6 of PRADY OS (v5.0 blueprint §4.6 / §5.7). STARMAP is the relational
memory of the constellation: a directed, typed knowledge graph over entities
(agents, tools, repos, services, projects, incidents, approvals, preferences)
and the relations between them (``proposed``, ``resulted_in``, ``depends_on``,
…). It answers entity-centric, project-centric and cause-effect queries by
graph traversal rather than nearest-neighbour text recall — the GraphRAG idea
from the blueprint.

It is intentionally dependency-free: an in-memory graph with a clean interface.
A production deployment can back the same interface with Neo4j; the traversal
logic and contracts live here and are fully testable.

Public surface:
    KnowledgeGraph  — the graph: add_node/add_edge, neighbors, path, reachable,
                      causal_chain, subgraph, stats
    Node, Edge      — immutable records returned by queries
    *Error          — typed failures
"""

from __future__ import annotations

from pradyos.starmap.graph import (
    Edge,
    KnowledgeGraph,
    Node,
    StarmapError,
    UnknownNodeError,
)

__all__ = [
    "KnowledgeGraph",
    "Node",
    "Edge",
    "StarmapError",
    "UnknownNodeError",
]
