"""Phase 47D — 10 tests for MemoryGraph endpoints in sovereign_web.

Uses /api/v1/memgraph/* (Phase 17 already owns /api/v1/graph/*).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.memory_graph import MemoryGraph
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_graph():
    return TestClient(create_app())


@pytest.fixture()
def client_with_graph():
    g = MemoryGraph()
    app = create_app(memory_graph=g)
    return TestClient(app), g


# ── list nodes ────────────────────────────────────────────────────────────────

def test_get_nodes_returns_200(client_no_graph):
    assert client_no_graph.get("/api/v1/memgraph/nodes").status_code == 200


def test_get_nodes_has_required_keys(client_with_graph):
    client, _ = client_with_graph
    data = client.get("/api/v1/memgraph/nodes").json()
    assert "nodes" in data
    assert "count" in data


def test_get_nodes_no_graph_empty(client_no_graph):
    data = client_no_graph.get("/api/v1/memgraph/nodes").json()
    assert data["nodes"] == []
    assert data["count"] == 0


# ── add node ──────────────────────────────────────────────────────────────────

def test_post_node_returns_200(client_with_graph):
    client, _ = client_with_graph
    resp = client.post("/api/v1/memgraph/nodes",
                       json={"name": "alpha", "metadata": {"k": "v"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "alpha"


def test_post_node_missing_name_400(client_with_graph):
    client, _ = client_with_graph
    resp = client.post("/api/v1/memgraph/nodes", json={"metadata": {}})
    assert resp.status_code == 400


# ── add edge ──────────────────────────────────────────────────────────────────

def test_post_edge_returns_200(client_with_graph):
    client, _ = client_with_graph
    resp = client.post("/api/v1/memgraph/edges",
                       json={"src": "a", "dst": "b", "relation": "knows"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["src"] == "a"
    assert data["dst"] == "b"


def test_post_edge_missing_relation_400(client_with_graph):
    client, _ = client_with_graph
    resp = client.post("/api/v1/memgraph/edges", json={"src": "a", "dst": "b"})
    assert resp.status_code == 400


# ── neighbors ─────────────────────────────────────────────────────────────────

def test_get_neighbors_has_required_keys(client_with_graph):
    client, _ = client_with_graph
    data = client.get("/api/v1/memgraph/neighbors/alpha").json()
    assert "neighbors" in data


# ── path ──────────────────────────────────────────────────────────────────────

def test_get_path_returns_path_key(client_with_graph):
    client, _ = client_with_graph
    data = client.get("/api/v1/memgraph/path?src=a&dst=b").json()
    assert "path" in data


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_nodes_edge_path(client_with_graph):
    client, _ = client_with_graph
    client.post("/api/v1/memgraph/nodes", json={"name": "A"})
    client.post("/api/v1/memgraph/nodes", json={"name": "B"})
    client.post("/api/v1/memgraph/edges",
                json={"src": "A", "dst": "B", "relation": "x"})
    data = client.get("/api/v1/memgraph/path?src=A&dst=B").json()
    assert data["path"] == ["A", "B"]
