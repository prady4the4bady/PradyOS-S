"""Plane 6 — tests for the /api/v1/starmap endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app
from pradyos.starmap import KnowledgeGraph


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def graph_client():
    g = KnowledgeGraph()
    g.add_node("oracle", "agent")
    g.add_node("projectX", "project")
    g.add_node("outcomeOk", "outcome")
    g.add_edge("oracle", "proposed", "projectX")
    g.add_edge("projectX", "resulted_in", "outcomeOk")
    return TestClient(create_app(starmap=g))


# ── mutation ──────────────────────────────────────────────────────────────────


def test_add_node(client):
    resp = client.post(
        "/api/v1/starmap/node", json={"id": "a", "type": "agent", "attrs": {"role": "scout"}}
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": "a", "type": "agent", "attrs": {"role": "scout"}}


def test_add_node_missing_422(client):
    assert client.post("/api/v1/starmap/node", json={"id": "a"}).status_code == 422


def test_add_edge(client):
    client.post("/api/v1/starmap/node", json={"id": "a", "type": "agent"})
    client.post("/api/v1/starmap/node", json={"id": "b", "type": "project"})
    resp = client.post("/api/v1/starmap/edge", json={"src": "a", "rel": "proposed", "dst": "b"})
    assert resp.status_code == 200 and resp.json()["rel"] == "proposed"


def test_add_edge_unknown_node_404(client):
    client.post("/api/v1/starmap/node", json={"id": "a", "type": "agent"})
    resp = client.post("/api/v1/starmap/edge", json={"src": "a", "rel": "r", "dst": "ghost"})
    assert resp.status_code == 404


def test_add_edge_create_missing(client):
    client.post("/api/v1/starmap/node", json={"id": "a", "type": "agent"})
    resp = client.post(
        "/api/v1/starmap/edge",
        json={"src": "a", "rel": "r", "dst": "ghost", "create_missing": True},
    )
    assert resp.status_code == 200


# ── queries ───────────────────────────────────────────────────────────────────


def test_nodes_filter(graph_client):
    ids = sorted(
        n["id"]
        for n in graph_client.get("/api/v1/starmap/nodes", params={"type": "project"}).json()[
            "nodes"
        ]
    )
    assert ids == ["projectX"]


def test_neighbors(graph_client):
    body = graph_client.get(
        "/api/v1/starmap/neighbors", params={"node_id": "projectX", "direction": "both"}
    ).json()
    assert sorted(body["neighbors"]) == ["oracle", "outcomeOk"]


def test_neighbors_unknown_404(client):
    assert client.get("/api/v1/starmap/neighbors", params={"node_id": "nope"}).status_code == 404


def test_neighbors_bad_direction_422(graph_client):
    resp = graph_client.get(
        "/api/v1/starmap/neighbors", params={"node_id": "oracle", "direction": "sideways"}
    )
    assert resp.status_code == 422


def test_path_multihop(graph_client):
    body = graph_client.get(
        "/api/v1/starmap/path", params={"src": "oracle", "dst": "outcomeOk"}
    ).json()
    assert body["found"] is True and body["path"] == ["oracle", "projectX", "outcomeOk"]


def test_path_not_found(graph_client):
    body = graph_client.get(
        "/api/v1/starmap/path", params={"src": "outcomeOk", "dst": "oracle"}
    ).json()
    assert body["found"] is False and body["path"] is None


def test_reachable(graph_client):
    body = graph_client.get("/api/v1/starmap/reachable", params={"src": "oracle"}).json()
    assert body["reachable"] == ["outcomeOk", "projectX"]


def test_causal_chain(graph_client):
    body = graph_client.get(
        "/api/v1/starmap/causal", params={"src": "projectX", "rel": "resulted_in"}
    ).json()
    assert body["chain"] == ["projectX", "outcomeOk"]


# ── stats & reset ─────────────────────────────────────────────────────────────


def test_stats_and_reset(graph_client):
    stats = graph_client.get("/api/v1/starmap/stats").json()
    assert stats["nodes"] == 3 and stats["edges"] == 2
    after = graph_client.delete("/api/v1/starmap/reset").json()
    assert after["nodes"] == 0 and after["edges"] == 0
