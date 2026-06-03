"""Phase 130 — tests for the /api/v1/ams endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.ams_sketch import AMSSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def trained_client():
    ams = AMSSketch(width=64, depth=7, seed=0)
    freq = {f"k{i}": (i % 9) + 1 for i in range(200)}
    for k, v in freq.items():
        ams.update(k, v)
    exact = sum(v * v for v in freq.values())
    return TestClient(create_app(ams=ams)), exact


# ── update ─────────────────────────────────────────────────────────────────────────────

def test_update_returns_f2(client):
    resp = client.post("/api/v1/ams/update", json={"key": "hello"})
    assert resp.status_code == 200 and resp.json()["f2"] >= 1.0


def test_update_missing_key_422(client):
    assert client.post("/api/v1/ams/update", json={}).status_code == 422


def test_update_null_key_422(client):
    resp = client.post("/api/v1/ams/update", json={"key": None})
    assert resp.status_code == 422 and "error" in resp.json()


def test_update_with_count(client):
    assert client.post("/api/v1/ams/update", json={"key": "a", "count": 5}).status_code == 200


def test_update_float_count_422(client):
    resp = client.post("/api/v1/ams/update", json={"key": "a", "count": 1.5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_update_float_key_422(client):
    resp = client.post("/api/v1/ams/update", json={"key": 3.14})
    assert resp.status_code == 422 and "error" in resp.json()


def test_update_negative_count(client):
    assert client.post("/api/v1/ams/update", json={"key": "a", "count": -3}).status_code == 200


# ── update_many ──────────────────────────────────────────────────────────────────────

def test_update_many(client):
    body = client.post("/api/v1/ams/update_many", json={"keys": ["a", "b", "c"]}).json()
    assert body["added"] == 3 and body["f2"] >= 0.0


def test_update_many_missing_422(client):
    assert client.post("/api/v1/ams/update_many", json={}).status_code == 422


def test_update_many_invalid_key_422(client):
    resp = client.post("/api/v1/ams/update_many", json={"keys": ["ok", 1.5]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── f2 ─────────────────────────────────────────────────────────────────────────────────

def test_f2_empty(client):
    body = client.get("/api/v1/ams/f2").json()
    assert body["f2"] == 0.0 and body["l2_norm"] == 0.0


def test_f2_keys(client):
    assert set(client.get("/api/v1/ams/f2").json()) == {"f2", "l2_norm"}


def test_f2_after_training(trained_client):
    tc, exact = trained_client
    f2 = tc.get("/api/v1/ams/f2").json()["f2"]
    assert abs(f2 / exact - 1.0) < 0.30                  # ~SE single-run bound


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/ams/stats").json()) == {
        "width", "depth", "f2", "l2_norm", "standard_error", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/ams/stats").json()
    assert s["width"] == 64 and s["depth"] == 7


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(trained_client):
    tc, _ = trained_client
    assert tc.request("DELETE", "/api/v1/ams/reset", json={}).json()["f2"] == 0.0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/ams/reset",
                          json={"width": 128, "depth": 5, "seed": 7}).json()
    assert body["width"] == 128 and body["depth"] == 5 and body["seed"] == 7


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/ams/reset", json={"width": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/ams/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_update_then_f2_grows(client):
    client.request("DELETE", "/api/v1/ams/reset", json={})
    client.post("/api/v1/ams/update_many", json={"keys": [f"k-{i}" for i in range(300)]})
    assert client.get("/api/v1/ams/f2").json()["f2"] > 0.0


# ── regression ────────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash", "scalablebloom",
                  "rendezvous", "maglev", "iblt", "bbitminhash", "cusketch", "jump",
                  "frugal", "simhashlsh", "randomprojection", "gcs", "fmsketch"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
