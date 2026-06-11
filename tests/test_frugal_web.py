"""Phase 125 — tests for the /api/v1/frugal endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.frugal import FrugalQuantile
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def trained_client():
    fq = FrugalQuantile(quantile=0.5, seed=0)
    rng = random.Random(7)
    fq.add_many(rng.uniform(0, 1000) for _ in range(100000))   # median ~500
    return TestClient(create_app(frugal=fq))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_estimate(client):
    resp = client.post("/api/v1/frugal/add", json={"value": 42})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1 and body["estimate"] == 42      # first sample seeds


def test_add_accumulates(client):
    for i in range(10):
        client.post("/api/v1/frugal/add", json={"value": i})
    assert client.get("/api/v1/frugal/estimate").json()["count"] == 10


def test_add_missing_value_422(client):
    assert client.post("/api/v1/frugal/add", json={}).status_code == 422


def test_add_non_number_422(client):
    resp = client.post("/api/v1/frugal/add", json={"value": "lots"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── estimate ─────────────────────────────────────────────────────────────────────

def test_estimate_empty(client):
    body = client.get("/api/v1/frugal/estimate").json()
    assert body["estimate"] == 0.0 and body["quantile"] == 0.5 and body["count"] == 0


def test_estimate_converged(trained_client):
    body = trained_client.get("/api/v1/frugal/estimate").json()
    assert abs(body["estimate"] - 500) < 80                   # median of uniform[0,1000)


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/frugal/stats").json()) == {
        "quantile", "estimate", "step", "count", "seed"}


def test_stats_default_quantile(client):
    assert client.get("/api/v1/frugal/stats").json()["quantile"] == 0.5


def test_stats_count(trained_client):
    assert trained_client.get("/api/v1/frugal/stats").json()["count"] == 100000


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(trained_client):
    resp = trained_client.request("DELETE", "/api/v1/frugal/reset", json={})
    assert resp.status_code == 200 and resp.json()["count"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/frugal/reset",
                          json={"quantile": 0.9, "seed": 9}).json()
    assert body["quantile"] == 0.9 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/frugal/reset", json={"quantile": 1.5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/frugal/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────

def test_add_estimate_roundtrip(client):
    client.request("DELETE", "/api/v1/frugal/reset", json={"quantile": 0.5})
    for v in (10, 20, 30, 40, 50):
        client.post("/api/v1/frugal/add", json={"value": v})
    body = client.get("/api/v1/frugal/estimate").json()
    assert body["count"] == 5 and 10 <= body["estimate"] <= 50


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash", "scalablebloom",
                  "rendezvous", "maglev", "iblt", "bbitminhash", "cusketch", "jump"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
