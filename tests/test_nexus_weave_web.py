"""Agent 4 — tests for the /api/v1/nexus endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed(client):
    client.post(
        "/api/v1/nexus/agent",
        json={"name": "helios", "location": "internal", "capabilities": ["build"]},
    )
    client.post(
        "/api/v1/nexus/agent",
        json={"name": "cloud", "location": "external", "capabilities": ["build", "research"]},
    )


def test_route_prefers_internal(client):
    _seed(client)
    client.post("/api/v1/nexus/submit", json={"task_id": "t1", "kind": "build"})
    t = client.post("/api/v1/nexus/route", json={"task_id": "t1"}).json()
    assert t["agent"] == "helios" and t["delegated"] is False


def test_route_delegates_external(client):
    _seed(client)
    client.post("/api/v1/nexus/submit", json={"task_id": "t1", "kind": "research"})
    t = client.post("/api/v1/nexus/route", json={"task_id": "t1"}).json()
    assert t["agent"] == "cloud" and t["delegated"] is True


def test_no_route_409(client):
    _seed(client)
    client.post("/api/v1/nexus/submit", json={"task_id": "t1", "kind": "speech"})
    resp = client.post("/api/v1/nexus/route", json={"task_id": "t1"})
    assert resp.status_code == 409 and resp.json()["routed"] is False


def test_fail_reroutes(client):
    _seed(client)
    client.post("/api/v1/nexus/submit", json={"task_id": "t1", "kind": "build"})
    client.post("/api/v1/nexus/route", json={"task_id": "t1"})  # helios
    client.post("/api/v1/nexus/fail", json={"task_id": "t1", "reason": "crash"})
    t = client.post("/api/v1/nexus/route", json={"task_id": "t1"}).json()
    assert t["agent"] == "cloud" and t["delegated"] is True


def test_register_bad_location_422(client):
    resp = client.post(
        "/api/v1/nexus/agent", json={"name": "x", "location": "edge", "capabilities": ["a"]}
    )
    assert resp.status_code == 422


def test_submit_missing_422(client):
    assert client.post("/api/v1/nexus/submit", json={"task_id": "t"}).status_code == 422


def test_unknown_task_404(client):
    assert client.get("/api/v1/nexus/task", params={"task_id": "nope"}).status_code == 404


def test_complete_flow_and_stats(client):
    _seed(client)
    client.post("/api/v1/nexus/submit", json={"task_id": "t1", "kind": "build"})
    client.post("/api/v1/nexus/route", json={"task_id": "t1"})
    done = client.post("/api/v1/nexus/complete", json={"task_id": "t1"}).json()
    assert done["status"] == "done"
    stats = client.get("/api/v1/nexus/stats").json()
    assert stats["agents"] == 2 and stats["by_status"]["done"] == 1
    after = client.delete("/api/v1/nexus/reset").json()
    assert after["agents"] == 0
