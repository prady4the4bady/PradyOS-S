"""Phase 72 — tests for the /api/v1/bloom endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bloom_filter import BloomFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_filter():
    return TestClient(create_app())


@pytest.fixture()
def client_with_filter():
    return TestClient(create_app(bloom_filter=BloomFilter(capacity=1000, error_rate=0.01)))


# ── no filter configured ──────────────────────────────────────────────────────

def test_stats_no_filter_returns_error(client_no_filter):
    assert "error" in client_no_filter.get("/api/v1/bloom").json()


def test_add_no_filter_returns_error(client_no_filter):
    assert "error" in client_no_filter.post("/api/v1/bloom/add", json={"item": "x"}).json()


def test_contains_no_filter_returns_error(client_no_filter):
    assert "error" in client_no_filter.get("/api/v1/bloom/contains/x").json()


def test_clear_no_filter_returns_error(client_no_filter):
    assert "error" in client_no_filter.delete("/api/v1/bloom").json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_filter):
    data = client_with_filter.get("/api/v1/bloom").json()
    for key in ("capacity", "error_rate", "bits", "hashes", "count",
                "fill_ratio", "est_false_positive_rate"):
        assert key in data, f"missing key: {key}"


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_single_item(client_with_filter):
    resp = client_with_filter.post("/api/v1/bloom/add", json={"item": "alpha"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["count"] == 1


def test_add_items_list(client_with_filter):
    resp = client_with_filter.post("/api/v1/bloom/add", json={"items": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["added"] == 3


def test_add_missing_item_returns_422(client_with_filter):
    resp = client_with_filter.post("/api/v1/bloom/add", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_add_non_string_item_returns_422(client_with_filter):
    resp = client_with_filter.post("/api/v1/bloom/add", json={"item": 5})
    assert resp.status_code == 422


def test_add_non_string_items_returns_422(client_with_filter):
    resp = client_with_filter.post("/api/v1/bloom/add", json={"items": [1, 2, 3]})
    assert resp.status_code == 422


# ── contains ──────────────────────────────────────────────────────────────────

def test_contains_true_after_add(client_with_filter):
    client_with_filter.post("/api/v1/bloom/add", json={"item": "alpha"})
    data = client_with_filter.get("/api/v1/bloom/contains/alpha").json()
    assert data["item"] == "alpha"
    assert data["contains"] is True


def test_contains_false_for_absent(client_with_filter):
    client_with_filter.post("/api/v1/bloom/add", json={"item": "alpha"})
    data = client_with_filter.get("/api/v1/bloom/contains/zzz-absent").json()
    assert data["contains"] is False


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_resets_filter(client_with_filter):
    client_with_filter.post("/api/v1/bloom/add", json={"items": ["a", "b"]})
    resp = client_with_filter.delete("/api/v1/bloom")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
    assert client_with_filter.get("/api/v1/bloom").json()["count"] == 0
    assert client_with_filter.get("/api/v1/bloom/contains/a").json()["contains"] is False


# ── core guarantee over HTTP ──────────────────────────────────────────────────

def test_no_false_negatives_over_http(client_with_filter):
    items = [f"item-{i}" for i in range(50)]
    client_with_filter.post("/api/v1/bloom/add", json={"items": items})
    assert all(
        client_with_filter.get(f"/api/v1/bloom/contains/{it}").json()["contains"]
        for it in items
    )
