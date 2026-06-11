"""Phase 17C — SovereignMemoryGraph unit tests (20 tests).

Covers:
 1.  add_node() returns GraphNode with correct kind/label
 2.  add_node() auto-generates node_id as non-empty str
 3.  add_node() with explicit node_id uses that id
 4.  add_node() increments stats()["nodes"]
 5.  add_edge() returns GraphEdge with correct src/dst/relation
 6.  add_edge() auto-generates edge_id
 7.  add_edge() increments stats()["edges"]
 8.  get_node() returns the node after add_node()
 9.  get_node() returns None for unknown id
10.  get_edge() returns the edge after add_edge()
11.  neighbours() returns connected nodes
12.  neighbours(relation=X) filters by relation
13.  query_nodes(kind="campaign") filters by kind
14.  query_nodes(label="x") filters by label
15.  remove_node() returns True for existing node
16.  remove_node() returns False for unknown node
17.  remove_node() also removes incident edges (check stats)
18.  remove_edge() returns True/False correctly
19.  maxnodes eviction — oldest node evicted when limit reached
20.  clear() resets stats to {"nodes": 0, "edges": 0}
"""
from __future__ import annotations

import time

import pytest

from pradyos.core.memorygraph import GraphEdge, GraphNode, SovereignMemoryGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _graph() -> SovereignMemoryGraph:
    return SovereignMemoryGraph()


# ===========================================================================
# Test 1: add_node() returns GraphNode with correct kind/label
# ===========================================================================

def test_add_node_returns_correct_kind_label():
    g = _graph()
    node = g.add_node(kind="campaign", label="alpha")
    assert isinstance(node, GraphNode)
    assert node.kind == "campaign"
    assert node.label == "alpha"


# ===========================================================================
# Test 2: add_node() auto-generates node_id as non-empty str
# ===========================================================================

def test_add_node_autogenerates_node_id():
    g = _graph()
    node = g.add_node(kind="task", label="t1")
    assert isinstance(node.node_id, str)
    assert len(node.node_id) > 0


# ===========================================================================
# Test 3: add_node() with explicit node_id uses that id
# ===========================================================================

def test_add_node_explicit_id():
    g = _graph()
    node = g.add_node(kind="agent", label="scout", node_id="custom-id-001")
    assert node.node_id == "custom-id-001"


# ===========================================================================
# Test 4: add_node() increments stats()["nodes"]
# ===========================================================================

def test_add_node_increments_stats():
    g = _graph()
    assert g.stats()["nodes"] == 0
    g.add_node(kind="fact", label="f1")
    assert g.stats()["nodes"] == 1
    g.add_node(kind="fact", label="f2")
    assert g.stats()["nodes"] == 2


# ===========================================================================
# Test 5: add_edge() returns GraphEdge with correct src/dst/relation
# ===========================================================================

def test_add_edge_returns_correct_fields():
    g = _graph()
    a = g.add_node(kind="task", label="A")
    b = g.add_node(kind="task", label="B")
    edge = g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="depends_on")
    assert isinstance(edge, GraphEdge)
    assert edge.src_id == a.node_id
    assert edge.dst_id == b.node_id
    assert edge.relation == "depends_on"


# ===========================================================================
# Test 6: add_edge() auto-generates edge_id
# ===========================================================================

def test_add_edge_autogenerates_edge_id():
    g = _graph()
    a = g.add_node(kind="agent", label="a")
    b = g.add_node(kind="agent", label="b")
    edge = g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="knows")
    assert isinstance(edge.edge_id, str)
    assert len(edge.edge_id) > 0


# ===========================================================================
# Test 7: add_edge() increments stats()["edges"]
# ===========================================================================

def test_add_edge_increments_stats():
    g = _graph()
    a = g.add_node(kind="campaign", label="c1")
    b = g.add_node(kind="campaign", label="c2")
    assert g.stats()["edges"] == 0
    g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="links_to")
    assert g.stats()["edges"] == 1


# ===========================================================================
# Test 8: get_node() returns the node after add_node()
# ===========================================================================

def test_get_node_returns_added_node():
    g = _graph()
    node = g.add_node(kind="fact", label="gravity")
    fetched = g.get_node(node.node_id)
    assert fetched is not None
    assert fetched.node_id == node.node_id
    assert fetched.label == "gravity"


# ===========================================================================
# Test 9: get_node() returns None for unknown id
# ===========================================================================

def test_get_node_unknown_returns_none():
    g = _graph()
    assert g.get_node("does-not-exist") is None


# ===========================================================================
# Test 10: get_edge() returns the edge after add_edge()
# ===========================================================================

def test_get_edge_returns_added_edge():
    g = _graph()
    a = g.add_node(kind="task", label="a")
    b = g.add_node(kind="task", label="b")
    edge = g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="produced_by")
    fetched = g.get_edge(edge.edge_id)
    assert fetched is not None
    assert fetched.edge_id == edge.edge_id
    assert fetched.relation == "produced_by"


# ===========================================================================
# Test 11: neighbours() returns connected nodes
# ===========================================================================

def test_neighbours_returns_connected_nodes():
    g = _graph()
    src = g.add_node(kind="campaign", label="root")
    dst1 = g.add_node(kind="task", label="child1")
    dst2 = g.add_node(kind="task", label="child2")
    g.add_edge(src_id=src.node_id, dst_id=dst1.node_id, relation="spawned")
    g.add_edge(src_id=src.node_id, dst_id=dst2.node_id, relation="spawned")
    nbrs = g.neighbours(src.node_id)
    ids = {n.node_id for n in nbrs}
    assert dst1.node_id in ids
    assert dst2.node_id in ids


# ===========================================================================
# Test 12: neighbours(relation=X) filters by relation
# ===========================================================================

def test_neighbours_filters_by_relation():
    g = _graph()
    src = g.add_node(kind="agent", label="alpha")
    a = g.add_node(kind="agent", label="beta")
    b = g.add_node(kind="agent", label="gamma")
    g.add_edge(src_id=src.node_id, dst_id=a.node_id, relation="manages")
    g.add_edge(src_id=src.node_id, dst_id=b.node_id, relation="monitors")

    manages = g.neighbours(src.node_id, relation="manages")
    assert len(manages) == 1
    assert manages[0].node_id == a.node_id

    monitors = g.neighbours(src.node_id, relation="monitors")
    assert len(monitors) == 1
    assert monitors[0].node_id == b.node_id


# ===========================================================================
# Test 13: query_nodes(kind="campaign") filters by kind
# ===========================================================================

def test_query_nodes_filters_by_kind():
    g = _graph()
    g.add_node(kind="campaign", label="c1")
    g.add_node(kind="campaign", label="c2")
    g.add_node(kind="task", label="t1")

    results = g.query_nodes(kind="campaign")
    assert len(results) == 2
    assert all(n.kind == "campaign" for n in results)


# ===========================================================================
# Test 14: query_nodes(label="x") filters by label
# ===========================================================================

def test_query_nodes_filters_by_label():
    g = _graph()
    g.add_node(kind="fact", label="gravity")
    g.add_node(kind="fact", label="entropy")
    g.add_node(kind="task", label="gravity")  # same label, different kind

    results = g.query_nodes(label="gravity")
    assert len(results) == 2
    assert all(n.label == "gravity" for n in results)


# ===========================================================================
# Test 15: remove_node() returns True for existing node
# ===========================================================================

def test_remove_node_returns_true_for_existing():
    g = _graph()
    node = g.add_node(kind="task", label="removable")
    assert g.remove_node(node.node_id) is True


# ===========================================================================
# Test 16: remove_node() returns False for unknown node
# ===========================================================================

def test_remove_node_returns_false_for_unknown():
    g = _graph()
    assert g.remove_node("ghost-id") is False


# ===========================================================================
# Test 17: remove_node() also removes incident edges (check stats)
# ===========================================================================

def test_remove_node_removes_incident_edges():
    g = _graph()
    a = g.add_node(kind="campaign", label="A")
    b = g.add_node(kind="campaign", label="B")
    c = g.add_node(kind="campaign", label="C")
    # Two edges incident to B (one incoming, one outgoing)
    g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="links_to")
    g.add_edge(src_id=b.node_id, dst_id=c.node_id, relation="links_to")
    assert g.stats()["edges"] == 2

    g.remove_node(b.node_id)
    assert g.stats()["edges"] == 0


# ===========================================================================
# Test 18: remove_edge() returns True/False correctly
# ===========================================================================

def test_remove_edge_returns_correct_bool():
    g = _graph()
    a = g.add_node(kind="task", label="a")
    b = g.add_node(kind="task", label="b")
    edge = g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="uses")

    assert g.remove_edge(edge.edge_id) is True
    assert g.remove_edge(edge.edge_id) is False   # already gone
    assert g.remove_edge("no-such-edge") is False


# ===========================================================================
# Test 19: maxnodes eviction — oldest node evicted when limit reached
# ===========================================================================

def test_maxnodes_eviction():
    g = SovereignMemoryGraph(maxnodes=3)
    n1 = g.add_node(kind="fact", label="first")
    time.sleep(0.001)  # ensure distinct timestamps
    g.add_node(kind="fact", label="second")
    time.sleep(0.001)
    g.add_node(kind="fact", label="third")

    assert g.stats()["nodes"] == 3

    # Adding a 4th should evict the oldest (n1)
    g.add_node(kind="fact", label="fourth")
    assert g.stats()["nodes"] == 3
    assert g.get_node(n1.node_id) is None


# ===========================================================================
# Test 20: clear() resets stats to {"nodes": 0, "edges": 0}
# ===========================================================================

def test_clear_resets_stats():
    g = _graph()
    a = g.add_node(kind="campaign", label="a")
    b = g.add_node(kind="campaign", label="b")
    g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="links_to")
    assert g.stats()["nodes"] == 2
    assert g.stats()["edges"] == 1

    g.clear()
    assert g.stats() == {"nodes": 0, "edges": 0}
