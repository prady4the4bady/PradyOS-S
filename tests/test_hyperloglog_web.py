"""Phase 74 — tests for the /api/v1/cardinality endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.hyperloglog import HyperLogLog
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_hll():
    return TestClient(create_app())


@pytest.fixture()
def client_with_hll():
    return TestClient(create_app(hyperloglog=HyperLogLog()))


# ── no estimator configured ───────────────────────────────────────────────────

def test_stats_no_hll_returns_error(client_no_hll):
    assert "error" in client_no_hll.get("/api/v1/cardinality").json()


def test_add_no_hll_returns_error(client_no_hll):
    assert "error" in client_no_hll.post("/api/v1/cardinality/add", json={"item": "x"}).json()


def test_estimate_no_hll_returns_error(client_no_hll):
    assert "error" in client_no_hll.get("/api/v1/cardinality/estimate").json()


def test_clear_no_hll_returns_error(client_no_hll):
    assert "error" in client_no_hll.delete("/api/v1/cardinality").json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_hll):
    data = client_with_hll.get("/api/v1/cardinality").json()
    for key in ("precision", "registers", "estimate", "fill_ratio"):
        assert key in data


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_single_item(client_with_hll):
    resp = client_with_hll.post("/api/v1/cardinality/add", json={"item": "alpha"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["estimate"] == 1


def test_add_items_list(client_with_hll):
    resp = client_with_hll.post("/api/v1/cardinality/add", json={"items": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["added"] == 3
    assert resp.json()["estimate"] == 3


def test_add_missing_returns_422(client_with_hll):
    resp = client_with_hll.post("/api/v1/cardinality/add", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_add_non_string_item_returns_422(client_with_hll):
    assert client_with_hll.post("/api/v1/cardinality/add", json={"item": 5}).status_code == 422


def test_add_non_string_items_returns_422(client_with_hll):
    assert client_with_hll.post("/api/v1/cardinality/add", json={"items": [1, 2]}).status_code == 422


# ── estimate ──────────────────────────────────────────────────────────────────

def test_estimate_endpoint_reflects_adds(client_with_hll):
    client_with_hll.post("/api/v1/cardinality/add", json={"items": ["a", "b", "c", "a"]})
    assert client_with_hll.get("/api/v1/cardinality/estimate").json()["estimate"] == 3


def test_estimate_accuracy_over_http(client_with_hll):
    items = [f"item-{i}" for i in range(1000)]
    client_with_hll.post("/api/v1/cardinality/add", json={"items": items})
    estimate = client_with_hll.get("/api/v1/cardinality/estimate").json()["estimate"]
    assert abs(estimate - 1000) / 1000 <= 0.05


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_resets_estimator(client_with_hll):
    client_with_hll.post("/api/v1/cardinality/add", json={"items": ["a", "b"]})
    resp = client_with_hll.delete("/api/v1/cardinality")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
    assert client_with_hll.get("/api/v1/cardinality/estimate").json()["estimate"] == 0
