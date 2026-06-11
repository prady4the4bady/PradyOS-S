"""Phase 55D — 10 tests for BulkheadManager endpoints in sovereign_web."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bulkhead_pool import BulkheadManager
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_mgr():
    return TestClient(create_app())


@pytest.fixture()
def client_with_mgr():
    mgr = BulkheadManager()
    app = create_app(bulkhead_manager=mgr)
    client = TestClient(app)
    try:
        yield client, mgr
    finally:
        # Drain any registered pools
        for stats in list(mgr.list_pools()):
            mgr.delete(stats["name"])


# ── GET /api/v1/bulkheads ────────────────────────────────────────────────────

def test_get_bulkheads_returns_200(client_no_mgr):
    assert client_no_mgr.get("/api/v1/bulkheads").status_code == 200


def test_get_bulkheads_no_manager_empty(client_no_mgr):
    data = client_no_mgr.get("/api/v1/bulkheads").json()
    assert data["pools"] == []


# ── POST /api/v1/bulkheads ───────────────────────────────────────────────────

def test_post_creates_pool_returns_stats(client_with_mgr):
    client, _ = client_with_mgr
    data = client.post("/api/v1/bulkheads",
                       json={"name": "svc", "max_workers": 2, "queue_depth": 4}).json()
    assert data["name"] == "svc"
    assert data["max_workers"] == 2


def test_post_duplicate_returns_error(client_with_mgr):
    client, _ = client_with_mgr
    client.post("/api/v1/bulkheads", json={"name": "svc"})
    data = client.post("/api/v1/bulkheads", json={"name": "svc"}).json()
    assert "error" in data


# ── GET /api/v1/bulkheads/{name} ─────────────────────────────────────────────

def test_get_by_name_returns_stats(client_with_mgr):
    client, _ = client_with_mgr
    client.post("/api/v1/bulkheads", json={"name": "svc"})
    data = client.get("/api/v1/bulkheads/svc").json()
    assert data["name"] == "svc"


def test_get_unknown_404(client_with_mgr):
    client, _ = client_with_mgr
    resp = client.get("/api/v1/bulkheads/phantom")
    assert resp.status_code == 404


# ── POST /api/v1/bulkheads/{name}/submit ─────────────────────────────────────

def test_submit_returns_submitted_true(client_with_mgr):
    client, _ = client_with_mgr
    client.post("/api/v1/bulkheads", json={"name": "svc"})
    data = client.post("/api/v1/bulkheads/svc/submit", json={"sleep": 0.0}).json()
    assert data["submitted"] is True
    assert "stats" in data


def test_submit_unknown_pool_404(client_with_mgr):
    client, _ = client_with_mgr
    resp = client.post("/api/v1/bulkheads/phantom/submit", json={"sleep": 0.0})
    assert resp.status_code == 404


def test_submit_full_pool_429():
    mgr = BulkheadManager()
    try:
        client = TestClient(create_app(bulkhead_manager=mgr))
        client.post("/api/v1/bulkheads",
                    json={"name": "tight", "max_workers": 1, "queue_depth": 0})
        # First submit fills capacity (sleep long enough that we can race)
        first = client.post("/api/v1/bulkheads/tight/submit",
                            json={"sleep": 1.0})
        assert first.status_code == 200
        # Second submit must be rejected
        second = client.post("/api/v1/bulkheads/tight/submit",
                             json={"sleep": 0.0})
        assert second.status_code == 429
        assert second.json()["submitted"] is False
    finally:
        mgr.delete("tight")


def test_stats_after_submit_has_submitted_geq_1(client_with_mgr):
    client, _ = client_with_mgr
    client.post("/api/v1/bulkheads", json={"name": "svc"})
    client.post("/api/v1/bulkheads/svc/submit", json={"sleep": 0.0})
    data = client.get("/api/v1/bulkheads/svc").json()
    assert data["submitted"] >= 1
