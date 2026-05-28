"""Phase 58D — 10 tests for EventFilter endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.event_filter import EventFilterRegistry
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_reg():
    return TestClient(create_app())


@pytest.fixture()
def client_with_reg():
    reg = EventFilterRegistry()
    app = create_app(event_filter_registry=reg)
    return TestClient(app), reg


# ── GET /api/v1/filters ──────────────────────────────────────────────────────

def test_get_filters_returns_200_names_count(client_with_reg):
    client, _ = client_with_reg
    data = client.get("/api/v1/filters").json()
    assert "names" in data
    assert "count" in data


def test_get_no_registry_empty(client_no_reg):
    data = client_no_reg.get("/api/v1/filters").json()
    assert data["names"] == []
    assert data["count"] == 0


# ── POST /api/v1/filters ─────────────────────────────────────────────────────

def test_post_creates_returns_rules_mode(client_with_reg):
    client, _ = client_with_reg
    data = client.post("/api/v1/filters", json={
        "name": "errors",
        "rules": [{"field": "level", "op": "eq", "value": "error"}],
        "mode": "AND",
    }).json()
    assert data["name"] == "errors"
    assert data["mode"] == "AND"
    assert len(data["rules"]) == 1


def test_post_invalid_mode_400(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/filters", json={
        "name": "x", "rules": [], "mode": "XOR",
    })
    assert resp.status_code == 400


def test_post_no_registry_returns_error(client_no_reg):
    data = client_no_reg.post("/api/v1/filters", json={
        "name": "x", "rules": [],
    }).json()
    assert "error" in data


# ── apply ────────────────────────────────────────────────────────────────────

def test_apply_returns_matched_events(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/filters", json={
        "name": "errors",
        "rules": [{"field": "level", "op": "eq", "value": "error"}],
    })
    data = client.post("/api/v1/filters/errors/apply", json={"events": [
        {"level": "info"},
        {"level": "error", "msg": "boom"},
        {"level": "error", "msg": "kaput"},
    ]}).json()
    assert data["matched"] == 2
    assert all(e["level"] == "error" for e in data["events"])


def test_apply_zero_matches_empty(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/filters", json={
        "name": "errors",
        "rules": [{"field": "level", "op": "eq", "value": "error"}],
    })
    data = client.post("/api/v1/filters/errors/apply", json={"events": [
        {"level": "info"}, {"level": "warn"},
    ]}).json()
    assert data["matched"] == 0
    assert data["events"] == []


def test_apply_unknown_filter_404(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/filters/phantom/apply", json={"events": []})
    assert resp.status_code == 404


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_returns_deleted_true(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/filters", json={"name": "x", "rules": []})
    resp = client.delete("/api/v1/filters/x")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_second_delete_returns_404(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/filters", json={"name": "x", "rules": []})
    client.delete("/api/v1/filters/x")
    resp = client.delete("/api/v1/filters/x")
    assert resp.status_code == 404
