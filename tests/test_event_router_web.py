"""Phase 62D — 10 tests for EventRouter endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.event_router import RouterRegistry
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_reg():
    return TestClient(create_app())


@pytest.fixture()
def client_with_reg():
    reg = RouterRegistry()
    app = create_app(router_registry=reg)
    return TestClient(app), reg


# ── GET /api/v1/routers ──────────────────────────────────────────────────────

def test_get_routers_returns_200(client_with_reg):
    client, _ = client_with_reg
    data = client.get("/api/v1/routers").json()
    assert "routers" in data
    assert "total" in data


def test_get_no_registry_empty(client_no_reg):
    data = client_no_reg.get("/api/v1/routers").json()
    assert data["routers"] == []
    assert data["total"] == 0


# ── POST /api/v1/routers ─────────────────────────────────────────────────────

def test_post_create_returns_created_true(client_with_reg):
    client, _ = client_with_reg
    data = client.post("/api/v1/routers", json={
        "name": "primary",
        "default_destination": "fallback",
        "routes": [
            {"name": "err", "predicates": [
                {"field": "level", "op": "eq", "value": "error"}
            ], "destination": "errors"},
        ],
    }).json()
    assert data["created"] is True
    assert data["route_count"] == 1


def test_post_missing_name_400(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/routers", json={"routes": []})
    assert resp.status_code == 400


def test_post_duplicate_name_409(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/routers", json={"name": "primary", "routes": []})
    resp = client.post("/api/v1/routers", json={"name": "primary", "routes": []})
    assert resp.status_code == 409


def test_post_no_registry_error(client_no_reg):
    data = client_no_reg.post("/api/v1/routers", json={
        "name": "x", "routes": [],
    }).json()
    assert "error" in data


# ── POST /api/v1/routers/{name}/route ────────────────────────────────────────

def test_post_route_dispatches_matching_routes(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/routers", json={
        "name": "primary",
        "routes": [
            {"name": "err", "predicates": [
                {"field": "level", "op": "eq", "value": "error"}
            ], "destination": "errors"},
        ],
    })
    data = client.post("/api/v1/routers/primary/route", json={
        "event": {"level": "error"},
    }).json()
    assert data["destinations"] == ["errors"]
    assert data["matched"] == 1


def test_post_route_unknown_router_404(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/routers/phantom/route",
                       json={"event": {}})
    assert resp.status_code == 404


def test_post_route_default_destination_when_no_match(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/routers", json={
        "name": "primary",
        "default_destination": "fallback",
        "routes": [
            {"name": "err", "predicates": [
                {"field": "level", "op": "eq", "value": "fatal"}
            ], "destination": "fatals"},
        ],
    })
    data = client.post("/api/v1/routers/primary/route", json={
        "event": {"level": "info"},
    }).json()
    assert data["destinations"] == ["fallback"]


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_returns_deleted_true(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/routers", json={"name": "primary", "routes": []})
    resp = client.delete("/api/v1/routers/primary")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_second_delete_returns_404(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/routers", json={"name": "primary", "routes": []})
    client.delete("/api/v1/routers/primary")
    resp = client.delete("/api/v1/routers/primary")
    assert resp.status_code == 404
