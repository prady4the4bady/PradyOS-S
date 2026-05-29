"""Phase 71 — tests for the /api/v1/anomaly/* watch endpoints in sovereign_web.

These cover the AnomalyWatch routes added in Phase 71 and live alongside the
Phase 69 /api/v1/anomaly z-score detector tests (test_anomaly_web.py), which
remain untouched.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.anomaly_watch import AnomalyWatch
from pradyos.sovereign_web import create_app


NORMAL = [10, 11, 9, 10, 11, 9, 10, 11, 9, 10, 11, 10]   # last value central
ANOMALOUS = [10, 11, 9, 10, 11, 9, 10, 11, 9, 10, 11, 1_000_000.0]  # last extreme


@pytest.fixture()
def client_no_watch():
    return TestClient(create_app())


@pytest.fixture()
def client_with_watch():
    return TestClient(create_app(anomaly_watch=AnomalyWatch()))


# ── no watch configured ───────────────────────────────────────────────────────

def test_sources_no_watch_returns_error(client_no_watch):
    assert "error" in client_no_watch.get("/api/v1/anomaly/sources").json()


def test_status_no_watch_returns_error(client_no_watch):
    assert "error" in client_no_watch.get("/api/v1/anomaly/status").json()


def test_register_no_watch_returns_error(client_no_watch):
    body = {"name": "svc", "baseline": NORMAL}
    assert "error" in client_no_watch.post("/api/v1/anomaly/sources", json=body).json()


def test_delete_no_watch_returns_error(client_no_watch):
    assert "error" in client_no_watch.delete("/api/v1/anomaly/sources/svc").json()


# ── listing & registration ────────────────────────────────────────────────────

def test_sources_initially_empty(client_with_watch):
    assert client_with_watch.get("/api/v1/anomaly/sources").json() == {"sources": []}


def test_register_then_listed(client_with_watch):
    resp = client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": NORMAL}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["registered"] is True
    assert body["samples"] == len(NORMAL)
    assert client_with_watch.get("/api/v1/anomaly/sources").json()["sources"] == ["cpu"]


def test_register_missing_name_returns_422(client_with_watch):
    resp = client_with_watch.post("/api/v1/anomaly/sources", json={"baseline": NORMAL})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_register_bad_baseline_returns_422(client_with_watch):
    resp = client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": ["not", "numbers"]}
    )
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_register_empty_baseline_ok(client_with_watch):
    resp = client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": []}
    )
    assert resp.status_code == 200
    assert resp.json()["samples"] == 0


# ── status (runs a tick) ───────────────────────────────────────────────────────

def test_status_warming_up_for_short_baseline(client_with_watch):
    client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": [10, 11, 9]}
    )
    results = client_with_watch.get("/api/v1/anomaly/status").json()["results"]
    assert results["cpu"]["status"] == "warming_up"


def test_status_scored_normal_not_anomalous(client_with_watch):
    client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": NORMAL}
    )
    results = client_with_watch.get("/api/v1/anomaly/status").json()["results"]
    assert results["cpu"]["status"] == "scored"
    assert results["cpu"]["anomaly"] is False


def test_status_detects_anomaly(client_with_watch):
    client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": ANOMALOUS}
    )
    results = client_with_watch.get("/api/v1/anomaly/status").json()["results"]
    assert results["cpu"]["status"] == "scored"
    assert results["cpu"]["anomaly"] is True


def test_status_empty_with_no_sources(client_with_watch):
    assert client_with_watch.get("/api/v1/anomaly/status").json() == {"results": {}}


# ── deletion ───────────────────────────────────────────────────────────────────

def test_delete_removes_source(client_with_watch):
    client_with_watch.post(
        "/api/v1/anomaly/sources", json={"name": "cpu", "baseline": NORMAL}
    )
    resp = client_with_watch.delete("/api/v1/anomaly/sources/cpu")
    assert resp.status_code == 200
    assert resp.json()["removed"] is True
    assert client_with_watch.get("/api/v1/anomaly/sources").json()["sources"] == []


def test_delete_unknown_returns_404(client_with_watch):
    resp = client_with_watch.delete("/api/v1/anomaly/sources/ghost")
    assert resp.status_code == 404
    assert "error" in resp.json()


# ── coexistence with the Phase 69 /api/v1/anomaly detector route ───────────────

def test_phase69_anomaly_route_still_distinct(client_with_watch):
    # The bare /api/v1/anomaly GET (Phase 69) has no detector wired here and must
    # not be shadowed by the Phase 71 /api/v1/anomaly/sources route.
    resp = client_with_watch.get("/api/v1/anomaly")
    assert resp.status_code == 200
    assert "error" in resp.json()  # "no anomaly detector configured"
