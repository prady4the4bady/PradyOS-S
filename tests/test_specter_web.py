"""SPECTER — tests for the /api/v1/specter endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _steps():
    return [{"kind": "navigate", "arg": "https://x"}, {"kind": "extract", "arg": "v"}]


def test_plan_api_first(client):
    p = client.get("/api/v1/specter/plan", params={"target": "gh", "has_api": True}).json()
    assert p["mode"] == "api"


def test_plan_browser_fallback(client):
    p = client.get("/api/v1/specter/plan", params={"target": "old", "has_api": False}).json()
    assert p["mode"] == "browser"


def test_create_and_step(client):
    client.post("/api/v1/specter/flow", json={"id": "f", "target": "t", "steps": _steps()})
    m = client.post("/api/v1/specter/step", json={"flow_id": "f"}).json()
    assert m["status"] == "running" and m["checkpoint"] == 0
    m = client.post("/api/v1/specter/step", json={"flow_id": "f"}).json()
    assert m["status"] == "done"


def test_create_bad_step_422(client):
    resp = client.post(
        "/api/v1/specter/flow", json={"id": "f", "target": "t", "steps": [{"kind": "fly"}]}
    )
    assert resp.status_code == 422


def test_extract(client):
    client.post("/api/v1/specter/flow", json={"id": "f", "target": "t", "steps": _steps()})
    m = client.post("/api/v1/specter/extract", json={"flow_id": "f", "key": "v", "value": 7}).json()
    assert m["state"]["v"] == 7


def test_fail_until_failed(client):
    client.post("/api/v1/specter/flow", json={"id": "f", "target": "t", "steps": _steps()})
    client.post("/api/v1/specter/step", json={"flow_id": "f"})
    statuses = []
    for _ in range(3):
        statuses.append(client.post("/api/v1/specter/fail", json={"flow_id": "f"}).json()["status"])
    assert statuses[-1] == "failed"


def test_unknown_flow_404(client):
    assert client.get("/api/v1/specter/flow", params={"flow_id": "nope"}).status_code == 404


def test_stats_and_reset(client):
    client.post("/api/v1/specter/flow", json={"id": "f", "target": "t", "steps": _steps()})
    assert client.get("/api/v1/specter/stats").json()["flows"] == 1
    after = client.delete("/api/v1/specter/reset").json()
    assert after["flows"] == 0
