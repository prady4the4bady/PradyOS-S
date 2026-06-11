"""Phase 76 — tests for the /api/v1/frequency endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.countminsketch import CountMinSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_sketch():
    return TestClient(create_app())


@pytest.fixture()
def client_with_sketch():
    return TestClient(create_app(countminsketch=CountMinSketch()))


# ── no sketch configured ──────────────────────────────────────────────────────

def test_stats_no_sketch_returns_error(client_no_sketch):
    assert "error" in client_no_sketch.get("/api/v1/frequency").json()


def test_add_no_sketch_returns_error(client_no_sketch):
    assert "error" in client_no_sketch.post("/api/v1/frequency/add", json={"item": "x"}).json()


def test_estimate_no_sketch_returns_error(client_no_sketch):
    assert "error" in client_no_sketch.post("/api/v1/frequency/estimate", json={"item": "x"}).json()


def test_merge_no_sketch_returns_error(client_no_sketch):
    assert "error" in client_no_sketch.post("/api/v1/frequency/merge", json={"items": []}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_sketch):
    data = client_with_sketch.get("/api/v1/frequency").json()
    for key in ("width", "depth", "cells", "total"):
        assert key in data


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_single(client_with_sketch):
    resp = client_with_sketch.post("/api/v1/frequency/add", json={"item": "apple"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["estimate"] == 1


def test_add_with_count(client_with_sketch):
    resp = client_with_sketch.post("/api/v1/frequency/add", json={"item": "apple", "count": 5})
    assert resp.status_code == 200
    assert resp.json()["estimate"] == 5


def test_add_missing_item_returns_422(client_with_sketch):
    resp = client_with_sketch.post("/api/v1/frequency/add", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_add_invalid_count_returns_422(client_with_sketch):
    resp = client_with_sketch.post("/api/v1/frequency/add", json={"item": "x", "count": 0})
    assert resp.status_code == 422


# ── estimate ──────────────────────────────────────────────────────────────────

def test_estimate_round_trip(client_with_sketch):
    client_with_sketch.post("/api/v1/frequency/add", json={"item": "apple", "count": 3})
    resp = client_with_sketch.post("/api/v1/frequency/estimate", json={"item": "apple"})
    assert resp.json()["item"] == "apple"
    assert resp.json()["estimate"] == 3


def test_estimate_accumulates_across_adds(client_with_sketch):
    for _ in range(3):
        client_with_sketch.post("/api/v1/frequency/add", json={"item": "banana"})
    assert client_with_sketch.post("/api/v1/frequency/estimate", json={"item": "banana"}).json()["estimate"] == 3


def test_estimate_missing_item_returns_422(client_with_sketch):
    resp = client_with_sketch.post("/api/v1/frequency/estimate", json={})
    assert resp.status_code == 422


def test_estimate_absent_item_is_zero(client_with_sketch):
    client_with_sketch.post("/api/v1/frequency/add", json={"item": "apple"})
    assert client_with_sketch.post("/api/v1/frequency/estimate", json={"item": "ghost-zzz"}).json()["estimate"] == 0


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_increases_estimate(client_with_sketch):
    client_with_sketch.post("/api/v1/frequency/add", json={"item": "apple", "count": 3})
    resp = client_with_sketch.post(
        "/api/v1/frequency/merge", json={"items": ["apple", "apple"], "item": "apple"}
    )
    assert resp.status_code == 200
    assert resp.json()["merged"] is True
    # merged estimate (3 + 2) is never less than the primary's 3
    assert resp.json()["estimate"] >= 3


def test_merge_invalid_items_returns_422(client_with_sketch):
    resp = client_with_sketch.post("/api/v1/frequency/merge", json={"items": "notalist"})
    assert resp.status_code == 422
