"""Phase 17D — Memory Graph web endpoint tests (10 tests).

FastAPI TestClient for:
  GET  /api/v1/graph/stats
  POST /api/v1/graph/nodes
  GET  /api/v1/graph/nodes
  GET  /api/v1/graph/nodes/{node_id}/neighbours

Covers:
  1.  GET /api/v1/graph/stats returns HTTP 200
  2.  stats has "nodes" and "edges" keys
  3.  POST /api/v1/graph/nodes returns 200
  4.  POST response has required keys (node_id, kind, label)
  5.  GET /api/v1/graph/nodes returns 200 with "nodes" and "count"
  6.  count equals len(nodes) after POST
  7.  ?kind=campaign filters by kind
  8.  GET /api/v1/graph/nodes/{node_id}/neighbours returns 200
  9.  neighbours response has "neighbours" and "count" keys
 10.  No graph injected -> safe empty responses (nodes=[], count=0)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.memorygraph import SovereignMemoryGraph
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(graph: SovereignMemoryGraph | None = None) -> TestClient:
    app = create_app(graph=graph)
    return TestClient(app)


def _populated_graph() -> SovereignMemoryGraph:
    g = SovereignMemoryGraph()
    g.add_node(kind="campaign", label="alpha")
    g.add_node(kind="task", label="beta")
    return g


# ===========================================================================
# Test 1: GET /api/v1/graph/stats returns HTTP 200
# ===========================================================================

def test_get_stats_returns_200():
    client = _client(_populated_graph())
    resp = client.get("/api/v1/graph/stats")
    assert resp.status_code == 200


# ===========================================================================
# Test 2: stats has "nodes" and "edges" keys
# ===========================================================================

def test_stats_has_required_keys():
    client = _client(_populated_graph())
    data = client.get("/api/v1/graph/stats").json()
    assert "nodes" in data
    assert "edges" in data


# ===========================================================================
# Test 3: POST /api/v1/graph/nodes returns 200
# ===========================================================================

def test_post_node_returns_200():
    client = _client(SovereignMemoryGraph())
    resp = client.post(
        "/api/v1/graph/nodes",
        json={"kind": "campaign", "label": "my-campaign"},
    )
    assert resp.status_code == 200


# ===========================================================================
# Test 4: POST response has required keys (node_id, kind, label)
# ===========================================================================

def test_post_node_response_has_required_keys():
    client = _client(SovereignMemoryGraph())
    data = client.post(
        "/api/v1/graph/nodes",
        json={"kind": "task", "label": "my-task"},
    ).json()
    assert "node_id" in data
    assert "kind" in data
    assert "label" in data


# ===========================================================================
# Test 5: GET /api/v1/graph/nodes returns 200 with "nodes" and "count"
# ===========================================================================

def test_get_nodes_returns_200_with_shape():
    client = _client(_populated_graph())
    resp = client.get("/api/v1/graph/nodes")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "count" in data


# ===========================================================================
# Test 6: count equals len(nodes) after POST
# ===========================================================================

def test_count_equals_len_nodes_after_post():
    g = SovereignMemoryGraph()
    client = _client(g)
    client.post("/api/v1/graph/nodes", json={"kind": "fact", "label": "x"})
    client.post("/api/v1/graph/nodes", json={"kind": "fact", "label": "y"})
    data = client.get("/api/v1/graph/nodes").json()
    assert data["count"] == len(data["nodes"])
    assert data["count"] >= 2


# ===========================================================================
# Test 7: ?kind=campaign filters by kind
# ===========================================================================

def test_kind_query_param_filters():
    g = SovereignMemoryGraph()
    client = _client(g)
    client.post("/api/v1/graph/nodes", json={"kind": "campaign", "label": "c1"})
    client.post("/api/v1/graph/nodes", json={"kind": "task", "label": "t1"})
    data = client.get("/api/v1/graph/nodes?kind=campaign").json()
    assert data["count"] == 1
    assert data["nodes"][0]["kind"] == "campaign"


# ===========================================================================
# Test 8: GET /api/v1/graph/nodes/{node_id}/neighbours returns 200
# ===========================================================================

def test_get_neighbours_returns_200():
    g = SovereignMemoryGraph()
    a = g.add_node(kind="campaign", label="parent")
    b = g.add_node(kind="task", label="child")
    g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="spawned")
    client = _client(g)
    resp = client.get(f"/api/v1/graph/nodes/{a.node_id}/neighbours")
    assert resp.status_code == 200


# ===========================================================================
# Test 9: neighbours response has "neighbours" and "count" keys
# ===========================================================================

def test_neighbours_response_shape():
    g = SovereignMemoryGraph()
    a = g.add_node(kind="agent", label="master")
    b = g.add_node(kind="agent", label="worker")
    g.add_edge(src_id=a.node_id, dst_id=b.node_id, relation="manages")
    client = _client(g)
    data = client.get(f"/api/v1/graph/nodes/{a.node_id}/neighbours").json()
    assert "neighbours" in data
    assert "count" in data
    assert data["count"] == 1
    assert data["neighbours"][0]["node_id"] == b.node_id


# ===========================================================================
# Test 10: No graph injected -> safe empty responses (nodes=[], count=0)
# ===========================================================================

def test_no_graph_returns_safe_empty_responses():
    client = _client(graph=None)

    stats = client.get("/api/v1/graph/stats").json()
    assert stats["nodes"] == 0
    assert stats["edges"] == 0

    nodes = client.get("/api/v1/graph/nodes").json()
    assert nodes["nodes"] == []
    assert nodes["count"] == 0

    nbrs = client.get("/api/v1/graph/nodes/any-id/neighbours").json()
    assert nbrs["neighbours"] == []
    assert nbrs["count"] == 0
