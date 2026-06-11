"""Phase 32D — 10 tests for snapshot store endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.snapshot_store import SnapshotStore
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_with_store():
    ss = SnapshotStore()
    app = create_app(snapshot_store=ss)
    return TestClient(app), ss


@pytest.fixture()
def client_no_store():
    app = create_app()
    return TestClient(app)


# ── GET /api/v1/snapshots/{namespace} ─────────────────────────────────────────

def test_get_namespace_returns_200(client_with_store):
    client, _ = client_with_store
    assert client.get("/api/v1/snapshots/myns").status_code == 200


def test_get_namespace_has_required_keys(client_with_store):
    client, _ = client_with_store
    data = client.get("/api/v1/snapshots/myns").json()
    assert "namespace" in data
    assert "keys" in data


def test_get_namespace_no_store_returns_empty_keys(client_no_store):
    data = client_no_store.get("/api/v1/snapshots/myns").json()
    assert data["keys"] == []


# ── POST /api/v1/snapshots/{namespace}/{key} ──────────────────────────────────

def test_post_snapshot_returns_200(client_with_store):
    client, _ = client_with_store
    resp = client.post("/api/v1/snapshots/myns/cfg", json={"data": {"x": 1}})
    assert resp.status_code == 200


def test_post_snapshot_first_version_is_1(client_with_store):
    client, _ = client_with_store
    data = client.post("/api/v1/snapshots/myns/cfg", json={"data": {"x": 1}}).json()
    assert data["version"] == 1
    assert data["namespace"] == "myns"
    assert data["key"] == "cfg"
    assert data["data"] == {"x": 1}
    assert "saved_at" in data


def test_post_snapshot_no_store_returns_error(client_no_store):
    data = client_no_store.post("/api/v1/snapshots/ns/k", json={"data": {}}).json()
    assert "error" in data


# ── GET /api/v1/snapshots/{namespace}/{key} ───────────────────────────────────

def test_get_snapshot_returns_200_after_save(client_with_store):
    client, _ = client_with_store
    client.post("/api/v1/snapshots/myns/cfg", json={"data": {"z": 9}})
    resp = client.get("/api/v1/snapshots/myns/cfg")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"z": 9}


def test_get_snapshot_unknown_returns_404(client_with_store):
    client, _ = client_with_store
    resp = client.get("/api/v1/snapshots/myns/does_not_exist")
    assert resp.status_code == 404


# ── DELETE /api/v1/snapshots/{namespace}/{key} ────────────────────────────────

def test_delete_snapshot_returns_deleted_true(client_with_store):
    client, _ = client_with_store
    client.post("/api/v1/snapshots/myns/cfg", json={"data": {}})
    resp = client.delete("/api/v1/snapshots/myns/cfg")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


# ── version increment ─────────────────────────────────────────────────────────

def test_second_save_version_2_and_get_returns_it(client_with_store):
    client, _ = client_with_store
    client.post("/api/v1/snapshots/myns/cfg", json={"data": {"v": 1}})
    r2 = client.post("/api/v1/snapshots/myns/cfg", json={"data": {"v": 2}})
    assert r2.json()["version"] == 2
    # GET without version= should return latest (v=2)
    got = client.get("/api/v1/snapshots/myns/cfg").json()
    assert got["version"] == 2
    assert got["data"] == {"v": 2}
