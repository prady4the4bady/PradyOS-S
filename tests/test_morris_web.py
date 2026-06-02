"""Phase 111 — tests for the /api/v1/morris endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.morris_counter import MorrisCounter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app MorrisCounter (base 2) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def seeded_client():
    return TestClient(create_app(morris_counter=MorrisCounter(base=2.0, seed=1)))


# ── increment ────────────────────────────────────────────────────────────────────

def test_increment_default_one(client):
    resp = client.post("/api/v1/morris/increment", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["increments"] == 1 and body["register"] >= 0 and "estimate" in body


def test_increment_no_body(client):
    assert client.post("/api/v1/morris/increment").status_code == 200


def test_increment_times(client):
    client.post("/api/v1/morris/increment", json={"times": 500})
    assert client.get("/api/v1/morris/stats").json()["increments"] == 500


def test_increment_accumulates(client):
    client.post("/api/v1/morris/increment", json={"times": 100})
    client.post("/api/v1/morris/increment", json={"times": 50})
    assert client.get("/api/v1/morris/stats").json()["increments"] == 150


def test_increment_zero_returns_422(client):
    assert client.post("/api/v1/morris/increment", json={"times": 0}).status_code == 422


def test_increment_negative_returns_422(client):
    assert client.post("/api/v1/morris/increment", json={"times": -5}).status_code == 422


def test_increment_float_returns_422(client):
    resp = client.post("/api/v1/morris/increment", json={"times": 2.5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_increment_non_numeric_returns_422(client):
    assert client.post("/api/v1/morris/increment", json={"times": "lots"}).status_code == 422


# ── estimate ─────────────────────────────────────────────────────────────────────

def test_estimate_zero_initially(client):
    body = client.get("/api/v1/morris/estimate").json()
    assert body["estimate"] == 0.0 and body["register"] == 0


def test_estimate_positive_after_increments(seeded_client):
    seeded_client.post("/api/v1/morris/increment", json={"times": 5000})
    body = seeded_client.get("/api/v1/morris/estimate").json()
    assert body["estimate"] > 0.0 and body["register"] >= 1


def test_estimate_register_log_log_small(seeded_client):
    seeded_client.post("/api/v1/morris/increment", json={"times": 50000})
    assert seeded_client.get("/api/v1/morris/estimate").json()["register"] < 30


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/morris/stats").json()) == {
        "register", "estimate", "increments", "base", "relative_error", "seed"}


def test_stats_default_base(client):
    assert client.get("/api/v1/morris/stats").json()["base"] == 2.0


def test_stats_tracks_increments(client):
    client.post("/api/v1/morris/increment", json={"times": 321})
    assert client.get("/api/v1/morris/stats").json()["increments"] == 321


# ── reset (DELETE with body) ──────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/morris/increment", json={"times": 1000})
    resp = client.request("DELETE", "/api/v1/morris/reset", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["register"] == 0 and body["increments"] == 0 and body["estimate"] == 0.0


def test_reset_reconfigures(client):
    resp = client.request("DELETE", "/api/v1/morris/reset", json={"base": 1.5, "seed": 9})
    body = resp.json()
    assert body["base"] == 1.5 and body["seed"] == 9


def test_reset_bad_base_returns_422(client):
    resp = client.request("DELETE", "/api/v1/morris/reset", json={"base": 1.0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/morris/reset").status_code == 200


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
