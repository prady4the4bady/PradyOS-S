"""Phase 39D — 10 tests for memory store endpoints in sovereign_web."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.memory_store import MemoryStore
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_mem():
    return TestClient(create_app())


@pytest.fixture()
def client_with_mem():
    m = MemoryStore()
    app = create_app(memory_store=m)
    return TestClient(app), m


# ── POST /api/v1/memory/{key} ─────────────────────────────────────────────────

def test_post_memory_returns_200(client_with_mem):
    client, _ = client_with_mem
    resp = client.post("/api/v1/memory/k1", json={"value": "hello"})
    assert resp.status_code == 200


def test_post_memory_no_store_error(client_no_mem):
    data = client_no_mem.post("/api/v1/memory/k1", json={"value": "x"}).json()
    assert "error" in data


def test_post_memory_response_has_all_fields(client_with_mem):
    client, _ = client_with_mem
    data = client.post("/api/v1/memory/k1",
                       json={"value": "hello", "tags": ["greet"], "ttl": 60.0}).json()
    for key in ("key", "value", "tags", "created_at", "updated_at", "ttl"):
        assert key in data, f"Missing key: {key}"
    assert data["value"] == "hello"


# ── GET /api/v1/memory/{key} ──────────────────────────────────────────────────

def test_get_memory_after_store_returns_200(client_with_mem):
    client, _ = client_with_mem
    client.post("/api/v1/memory/k1", json={"value": "hello"})
    assert client.get("/api/v1/memory/k1").status_code == 200


def test_get_unknown_returns_404(client_with_mem):
    client, _ = client_with_mem
    assert client.get("/api/v1/memory/phantom").status_code == 404


# ── DELETE /api/v1/memory/{key} ───────────────────────────────────────────────

def test_delete_memory_returns_deleted_true(client_with_mem):
    client, _ = client_with_mem
    client.post("/api/v1/memory/k1", json={"value": "x"})
    resp = client.delete("/api/v1/memory/k1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_delete_unknown_returns_404(client_with_mem):
    client, _ = client_with_mem
    assert client.delete("/api/v1/memory/phantom").status_code == 404


# ── GET /api/v1/memory/search ─────────────────────────────────────────────────

def test_search_returns_matching_entries(client_with_mem):
    client, _ = client_with_mem
    client.post("/api/v1/memory/k1", json={"value": "a", "tags": ["x"]})
    client.post("/api/v1/memory/k2", json={"value": "b", "tags": ["x", "y"]})
    client.post("/api/v1/memory/k3", json={"value": "c", "tags": ["y"]})
    data = client.get("/api/v1/memory/search?tag=x").json()
    keys = [e["key"] for e in data["entries"]]
    assert sorted(keys) == ["k1", "k2"]


# ── POST /api/v1/memory/expire ────────────────────────────────────────────────

def test_post_expire_returns_count(client_with_mem):
    client, _ = client_with_mem
    client.post("/api/v1/memory/k1", json={"value": "x", "ttl": 0.001})
    client.post("/api/v1/memory/k2", json={"value": "y", "ttl": 0.001})
    time.sleep(0.01)
    data = client.post("/api/v1/memory/expire").json()
    assert data["expired"] == 2


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_store_ttl_expire_recall_404(client_with_mem):
    client, _ = client_with_mem
    client.post("/api/v1/memory/k1", json={"value": "x", "ttl": 0.001})
    time.sleep(0.01)
    client.post("/api/v1/memory/expire")
    resp = client.get("/api/v1/memory/k1")
    assert resp.status_code == 404
