"""Phase 60D — 10 tests for PipelineRegistry endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.pipeline_chain import PipelineRegistry
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_reg():
    return TestClient(create_app())


@pytest.fixture()
def client_with_reg():
    reg = PipelineRegistry()
    app = create_app(pipeline_registry=reg)
    return TestClient(app), reg


# ── GET /api/v1/pipelines ────────────────────────────────────────────────────

def test_get_pipelines_returns_200_with_keys(client_with_reg):
    client, _ = client_with_reg
    data = client.get("/api/v1/pipelines").json()
    assert "pipelines" in data
    assert "count" in data


def test_get_no_registry_empty(client_no_reg):
    data = client_no_reg.get("/api/v1/pipelines").json()
    assert data["pipelines"] == []
    assert data["count"] == 0


# ── POST /api/v1/pipelines ───────────────────────────────────────────────────

def test_post_register_returns_registered_true(client_with_reg):
    client, _ = client_with_reg
    data = client.post("/api/v1/pipelines", json={
        "name": "p1",
        "steps": [
            {"name": "s1", "transform_type": "set_field",
             "params": {"key": "x", "value": 1}},
        ],
    }).json()
    assert data["registered"] is True
    assert data["name"] == "p1"
    assert data["step_count"] == 1


def test_post_missing_keys_400(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/pipelines", json={"name": "p1"})
    assert resp.status_code == 400


def test_post_no_registry_returns_error(client_no_reg):
    data = client_no_reg.post("/api/v1/pipelines", json={
        "name": "p1", "steps": [],
    }).json()
    assert "error" in data


# ── POST /api/v1/pipelines/{name}/run ────────────────────────────────────────

def test_run_returns_result_dict(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/pipelines", json={
        "name": "p1",
        "steps": [
            {"name": "set", "transform_type": "set_field",
             "params": {"key": "x", "value": 42}},
        ],
    })
    data = client.post("/api/v1/pipelines/p1/run", json={"event": {}}).json()
    assert data["name"] == "p1"
    assert data["result"] == {"x": 42}


def test_run_unknown_chain_404(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/pipelines/phantom/run", json={"event": {}})
    assert resp.status_code == 404


def test_run_bad_step_422_with_step_key(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/pipelines", json={
        "name": "p1",
        "steps": [
            {"name": "bad", "transform_type": "uppercase_field",
             "params": {"key": "missing"}},
        ],
    })
    resp = client.post("/api/v1/pipelines/p1/run", json={"event": {}})
    assert resp.status_code == 422
    body = resp.json()
    assert "step" in body
    assert body["step"] == "bad"


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_returns_deleted_true(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/pipelines", json={"name": "p1", "steps": []})
    resp = client.delete("/api/v1/pipelines/p1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_second_delete_returns_404(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/pipelines", json={"name": "p1", "steps": []})
    client.delete("/api/v1/pipelines/p1")
    resp = client.delete("/api/v1/pipelines/p1")
    assert resp.status_code == 404
