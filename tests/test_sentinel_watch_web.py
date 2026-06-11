"""Agent 5 — tests for the /api/v1/sentinel endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_register_and_secure(client):
    client.post("/api/v1/sentinel/scenario", json={"name": "x", "boundary": "kernel"})
    p = client.get("/api/v1/sentinel/posture").json()
    assert p["scenarios"] == 1 and p["threat_level"] == "secure"


def test_breach_elevates_then_patch(client):
    client.post("/api/v1/sentinel/scenario", json={"name": "x", "boundary": "kernel"})
    client.post("/api/v1/sentinel/run", json={"name": "x", "breached": True})
    assert client.get("/api/v1/sentinel/posture").json()["threat_level"] == "elevated"
    client.post("/api/v1/sentinel/patch", json={"name": "x"})
    assert client.get("/api/v1/sentinel/posture").json()["threat_level"] == "secure"


def test_critical_posture(client):
    for i in range(3):
        client.post("/api/v1/sentinel/scenario", json={"name": f"s{i}", "boundary": "b"})
        client.post("/api/v1/sentinel/run", json={"name": f"s{i}", "breached": True})
    p = client.get("/api/v1/sentinel/posture").json()
    assert p["threat_level"] == "critical" and p["response"] == "safe_stop_escalate"


def test_register_missing_422(client):
    assert client.post("/api/v1/sentinel/scenario", json={"name": "x"}).status_code == 422


def test_run_bad_breached_422(client):
    client.post("/api/v1/sentinel/scenario", json={"name": "x", "boundary": "b"})
    resp = client.post("/api/v1/sentinel/run", json={"name": "x", "breached": "yes"})
    assert resp.status_code == 422


def test_run_unknown_404(client):
    assert (
        client.post("/api/v1/sentinel/run", json={"name": "nope", "breached": True}).status_code
        == 404
    )


def test_patch_no_breach_422(client):
    client.post("/api/v1/sentinel/scenario", json={"name": "x", "boundary": "b"})
    assert client.post("/api/v1/sentinel/patch", json={"name": "x"}).status_code == 422


def test_scenarios_history_reset(client):
    client.post("/api/v1/sentinel/scenario", json={"name": "x", "boundary": "b"})
    client.post("/api/v1/sentinel/run", json={"name": "x", "breached": False})
    assert len(client.get("/api/v1/sentinel/scenarios").json()["scenarios"]) == 1
    assert len(client.get("/api/v1/sentinel/history").json()["history"]) == 1
    after = client.delete("/api/v1/sentinel/reset").json()
    assert after["scenarios"] == 0
