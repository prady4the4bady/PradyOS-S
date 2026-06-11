"""Plane 9 — tests for the /api/v1/citadel endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed(client, cid="c", gdi=0.1, ok=True, regression=0.0):
    client.post("/api/v1/citadel/cycle", json={"id": cid})
    client.post("/api/v1/citadel/audit", json={"cycle_id": cid, "failures": ["slow"]})
    client.post("/api/v1/citadel/candidate", json={"cycle_id": cid, "name": "tune"})
    client.post(
        "/api/v1/citadel/gate",
        json={"cycle_id": cid, "gdi": gdi, "constraints_ok": ok, "regression": regression},
    )


def test_clean_cycle_promotes(client):
    _seed(client, gdi=0.1, ok=True, regression=0.01)
    last = None
    for _ in range(6):
        last = client.post("/api/v1/citadel/advance", json={"cycle_id": "c"}).json()
    assert last["promoted"] is True


def test_drift_gate_halts(client):
    _seed(client, gdi=0.5)
    client.post("/api/v1/citadel/advance", json={"cycle_id": "c"})  # generating
    client.post("/api/v1/citadel/advance", json={"cycle_id": "c"})  # drift_check
    m = client.post("/api/v1/citadel/advance", json={"cycle_id": "c"}).json()
    assert m["halted"] is True and "GDI" in m["halt_reason"]


def test_constraint_gate_halts(client):
    _seed(client, gdi=0.1, ok=False)
    for _ in range(3):
        client.post("/api/v1/citadel/advance", json={"cycle_id": "c"})
    m = client.post("/api/v1/citadel/advance", json={"cycle_id": "c"}).json()
    assert m["halted"] is True


def test_start_missing_id_422(client):
    assert client.post("/api/v1/citadel/cycle", json={}).status_code == 422


def test_gate_bad_constraints_422(client):
    client.post("/api/v1/citadel/cycle", json={"id": "c"})
    resp = client.post("/api/v1/citadel/gate", json={"cycle_id": "c", "constraints_ok": "yes"})
    assert resp.status_code == 422


def test_unknown_cycle_404(client):
    assert client.get("/api/v1/citadel/cycle", params={"cycle_id": "nope"}).status_code == 404
    assert client.post("/api/v1/citadel/advance", json={"cycle_id": "nope"}).status_code == 404


def test_manual_halt(client):
    client.post("/api/v1/citadel/cycle", json={"id": "c"})
    m = client.post("/api/v1/citadel/halt", json={"cycle_id": "c", "reason": "stop"}).json()
    assert m["halted"] is True and m["halt_reason"] == "stop"


def test_stats_and_reset(client):
    _seed(client, "c1")
    stats = client.get("/api/v1/citadel/stats").json()
    assert stats["cycles"] == 1
    after = client.delete("/api/v1/citadel/reset").json()
    assert after["cycles"] == 0
