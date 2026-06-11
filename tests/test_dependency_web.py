"""Phase 70 — tests for the /api/v1/deps endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.dependency_graph import DependencyGraph
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_engine():
    return TestClient(create_app())


@pytest.fixture()
def client_with_engine():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    g.add_dependency("api", "db")
    g.add_dependency("web", "cache")
    app = create_app(dependency_graph=g)
    return TestClient(app), g


# ── no engine ─────────────────────────────────────────────────────────────────

def test_get_deps_no_engine_returns_error(client_no_engine):
    assert "error" in client_no_engine.get("/api/v1/deps/db").json()


def test_post_deps_no_engine_returns_error(client_no_engine):
    body = {"from": "web", "to": "db"}
    assert "error" in client_no_engine.post("/api/v1/deps", json=body).json()


# ── GET node info ─────────────────────────────────────────────────────────────

def test_get_deps_returns_node_info(client_with_engine):
    client, _ = client_with_engine
    data = client.get("/api/v1/deps/db").json()
    for key in ("node", "exists", "dependencies", "dependents", "impact_score"):
        assert key in data, f"missing key: {key}"
    assert data["node"] == "db"
    assert data["dependents"] == ["api", "web"]
    assert data["impact_score"] == 2


# ── POST add edge ─────────────────────────────────────────────────────────────

def test_post_deps_adds_edge(client_with_engine):
    client, _ = client_with_engine
    resp = client.post("/api/v1/deps", json={"from": "worker", "to": "queue"})
    assert resp.status_code == 200
    assert resp.json()["added"] is True
    # the new dependency is now visible
    assert client.get("/api/v1/deps/worker").json()["dependencies"] == ["queue"]


def test_post_deps_missing_field_returns_422(client_with_engine):
    client, _ = client_with_engine
    resp = client.post("/api/v1/deps", json={"from": "worker"})
    assert resp.status_code == 422
    assert "error" in resp.json()


# ── DELETE edge ───────────────────────────────────────────────────────────────

def test_delete_deps_removes_edge(client_with_engine):
    client, _ = client_with_engine
    resp = client.delete("/api/v1/deps/web/db")
    assert resp.status_code == 200
    assert resp.json()["removed"] is True
    assert "db" not in client.get("/api/v1/deps/web").json()["dependencies"]


def test_delete_deps_nonexistent_returns_false(client_with_engine):
    client, _ = client_with_engine
    assert client.delete("/api/v1/deps/web/ghost").json()["removed"] is False


# ── topological sort ──────────────────────────────────────────────────────────

def test_get_sort_returns_order(client_with_engine):
    client, _ = client_with_engine
    data = client.get("/api/v1/deps/web/sort").json()
    assert data["node"] == "web"
    order = data["order"]
    # web depends on db and cache → both precede web
    assert order.index("db") < order.index("web")
    assert order.index("cache") < order.index("web")


def test_get_sort_cycle_returns_409(client_with_engine):
    client, g = client_with_engine
    g.add_dependency("db", "web")  # introduce a web <-> db cycle
    resp = client.get("/api/v1/deps/web/sort")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "cycle detected"
    assert body["cycle"][0] == body["cycle"][-1]


# ── impact ────────────────────────────────────────────────────────────────────

def test_get_impact_returns_score(client_with_engine):
    client, _ = client_with_engine
    data = client.get("/api/v1/deps/db/impact").json()
    assert data["node"] == "db"
    assert data["impact_score"] == 2
