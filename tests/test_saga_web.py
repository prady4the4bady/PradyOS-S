"""Phase 66D — 10 tests for SagaOrchestrator endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.saga_orchestrator import SagaOrchestrator
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_orch():
    return TestClient(create_app())


@pytest.fixture()
def client_with_orch():
    so = SagaOrchestrator()
    so.register("double", lambda p: {"n": p.get("n", 0) * 2})
    so.register("add_one", lambda p: {"n": p.get("n", 0) + 1})
    app = create_app(saga_orchestrator=so)
    return TestClient(app), so


# ── POST /api/v1/sagas/run ───────────────────────────────────────────────────

def test_post_run_returns_200_completed(client_with_orch):
    client, _ = client_with_orch
    data = client.post("/api/v1/sagas/run", json={
        "name": "math_chain",
        "steps": ["double", "add_one"],
        "payload": {"n": 5},
    }).json()
    assert data["status"] == "completed"


def test_post_run_response_has_required_keys(client_with_orch):
    client, _ = client_with_orch
    data = client.post("/api/v1/sagas/run", json={
        "name": "math_chain",
        "steps": ["double"],
        "payload": {"n": 5},
    }).json()
    for k in ("saga_id", "saga_name", "status", "payload_trace"):
        assert k in data


def test_post_run_no_orchestrator_returns_error(client_no_orch):
    data = client_no_orch.post("/api/v1/sagas/run", json={
        "name": "x", "steps": ["a"],
    }).json()
    assert "error" in data


def test_post_run_missing_name_400(client_with_orch):
    client, _ = client_with_orch
    resp = client.post("/api/v1/sagas/run", json={"steps": ["double"]})
    assert resp.status_code == 400


def test_post_run_missing_steps_400(client_with_orch):
    client, _ = client_with_orch
    resp = client.post("/api/v1/sagas/run", json={"name": "x"})
    assert resp.status_code == 400


def test_post_run_empty_steps_completes(client_with_orch):
    client, _ = client_with_orch
    data = client.post("/api/v1/sagas/run", json={
        "name": "noop", "steps": [],
    }).json()
    assert data["status"] == "completed"
    assert data["payload_trace"] == []


# ── GET /api/v1/sagas ────────────────────────────────────────────────────────

def test_get_sagas_returns_runs_after_post(client_with_orch):
    client, _ = client_with_orch
    sub = client.post("/api/v1/sagas/run", json={
        "name": "s", "steps": ["double"], "payload": {"n": 1},
    }).json()
    data = client.get("/api/v1/sagas").json()
    saga_ids = [r["saga_id"] for r in data["runs"]]
    assert sub["saga_id"] in saga_ids


def test_get_sagas_no_orchestrator_empty(client_no_orch):
    data = client_no_orch.get("/api/v1/sagas").json()
    assert data["runs"] == []


# ── GET /api/v1/sagas/{saga_id} ──────────────────────────────────────────────

def test_get_saga_by_id_returns_correct_run(client_with_orch):
    client, _ = client_with_orch
    sub = client.post("/api/v1/sagas/run", json={
        "name": "s", "steps": ["double"], "payload": {"n": 7},
    }).json()
    saga_id = sub["saga_id"]
    data = client.get(f"/api/v1/sagas/{saga_id}").json()
    assert data["saga_id"] == saga_id
    assert data["status"] == "completed"


def test_get_saga_unknown_id_404(client_with_orch):
    client, _ = client_with_orch
    resp = client.get("/api/v1/sagas/phantom-id-doesnt-exist")
    assert resp.status_code == 404
