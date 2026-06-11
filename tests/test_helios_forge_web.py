"""Agent 2 — tests for the /api/v1/helios endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _drive_to_validated(client, bid="b"):
    client.post("/api/v1/helios/build", json={"id": bid, "project": "P"})
    for _ in range(3):  # planned -> tested
        client.post("/api/v1/helios/advance", json={"build_id": bid})
    client.post("/api/v1/helios/tests", json={"build_id": bid, "passed": 3, "failed": 0})
    return client.post("/api/v1/helios/advance", json={"build_id": bid}).json()  # validated


def test_create_and_manifest(client):
    m = client.post("/api/v1/helios/build", json={"id": "b1", "project": "Aurora"}).json()
    assert m["stage"] == "planned"
    got = client.get("/api/v1/helios/build", params={"build_id": "b1"}).json()
    assert got["project"] == "Aurora"


def test_create_missing_422(client):
    assert client.post("/api/v1/helios/build", json={"id": "b"}).status_code == 422


def test_advance_test_gate(client):
    client.post("/api/v1/helios/build", json={"id": "b", "project": "P"})
    for _ in range(3):
        client.post("/api/v1/helios/advance", json={"build_id": "b"})
    # no green tests -> 422 at validate gate
    assert client.post("/api/v1/helios/advance", json={"build_id": "b"}).status_code == 422


def test_full_flow_to_staged(client):
    client.post("/api/v1/helios/build", json={"id": "b", "project": "P"})
    client.post("/api/v1/helios/milestone", json={"build_id": "b", "name": "m1"})
    for _ in range(3):
        client.post("/api/v1/helios/advance", json={"build_id": "b"})
    client.post("/api/v1/helios/tests", json={"build_id": "b", "passed": 5, "failed": 0})
    client.post("/api/v1/helios/advance", json={"build_id": "b"})  # validated
    # milestone incomplete -> blocked
    assert client.post("/api/v1/helios/advance", json={"build_id": "b"}).status_code == 422
    client.post("/api/v1/helios/milestone", json={"build_id": "b", "name": "m1", "complete": True})
    m = client.post("/api/v1/helios/advance", json={"build_id": "b"}).json()
    assert m["stage"] == "staged" and m["is_terminal"] is True


def test_unknown_build_404(client):
    assert client.get("/api/v1/helios/build", params={"build_id": "nope"}).status_code == 404
    assert client.post("/api/v1/helios/advance", json={"build_id": "nope"}).status_code == 404


def test_artifact_and_bad_kind(client):
    client.post("/api/v1/helios/build", json={"id": "b", "project": "P"})
    ok = client.post(
        "/api/v1/helios/artifact", json={"build_id": "b", "name": "x.py", "kind": "code"}
    )
    assert ok.status_code == 200
    bad = client.post("/api/v1/helios/artifact", json={"build_id": "b", "name": "x", "kind": "exe"})
    assert bad.status_code == 422


def test_milestone_bad_complete_flag_422(client):
    client.post("/api/v1/helios/build", json={"id": "b", "project": "P"})
    resp = client.post(
        "/api/v1/helios/milestone", json={"build_id": "b", "name": "m", "complete": "yes"}
    )
    assert resp.status_code == 422


def test_stats_and_reset(client):
    _drive_to_validated(client, "b1")
    stats = client.get("/api/v1/helios/stats").json()
    assert stats["builds"] == 1 and stats["by_stage"]["validated"] == 1
    after = client.delete("/api/v1/helios/reset").json()
    assert after["builds"] == 0
