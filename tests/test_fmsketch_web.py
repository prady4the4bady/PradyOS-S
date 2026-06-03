"""Phase 129 — tests for the /api/v1/fmsketch endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.fm_sketch import FMSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def trained_client():
    fm = FMSketch(num_bitmaps=64, num_bits=32, seed=0)
    fm.add_many(f"e-{i}" for i in range(10000))
    return TestClient(create_app(fm_sketch=fm))


# ── add ──────────────────────────────────────────────────────────────────────────────

def test_add_returns_estimate(client):
    resp = client.post("/api/v1/fmsketch/add", json={"item": "hello"})
    assert resp.status_code == 200 and resp.json()["estimate"] > 0.0


def test_add_missing_item_422(client):
    assert client.post("/api/v1/fmsketch/add", json={}).status_code == 422


def test_add_null_item_422(client):
    resp = client.post("/api/v1/fmsketch/add", json={"item": None})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_float_item_422(client):
    resp = client.post("/api/v1/fmsketch/add", json={"item": 3.14})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_int_item(client):
    assert client.post("/api/v1/fmsketch/add", json={"item": 99}).status_code == 200


# ── add_many ─────────────────────────────────────────────────────────────────────────

def test_add_many(client):
    body = client.post("/api/v1/fmsketch/add_many", json={"items": ["a", "b", "c"]}).json()
    assert body["added"] == 3 and body["estimate"] > 0.0


def test_add_many_missing_422(client):
    assert client.post("/api/v1/fmsketch/add_many", json={}).status_code == 422


def test_add_many_invalid_item_422(client):
    resp = client.post("/api/v1/fmsketch/add_many", json={"items": ["ok", 1.5]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── estimate ─────────────────────────────────────────────────────────────────────────

def test_estimate_empty(client):
    body = client.get("/api/v1/fmsketch/estimate").json()
    assert body["estimate"] == 0.0 and body["count"] == 0


def test_estimate_after_training(trained_client):
    body = trained_client.get("/api/v1/fmsketch/estimate").json()
    assert abs(body["estimate"] / 10000 - 1.0) < 0.30      # ~3×SE single-run bound


def test_estimate_keys(client):
    assert set(client.get("/api/v1/fmsketch/estimate").json()) == {"estimate", "count"}


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/fmsketch/stats").json()) == {
        "num_bitmaps", "num_bits", "estimate", "standard_error", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/fmsketch/stats").json()
    assert s["num_bitmaps"] == 64 and s["num_bits"] == 32


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(trained_client):
    body = trained_client.request("DELETE", "/api/v1/fmsketch/reset", json={}).json()
    assert body["estimate"] == 0.0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/fmsketch/reset",
                          json={"num_bitmaps": 256, "num_bits": 24, "seed": 5}).json()
    assert body["num_bitmaps"] == 256 and body["num_bits"] == 24 and body["seed"] == 5


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/fmsketch/reset", json={"num_bitmaps": 100})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/fmsketch/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_add_then_estimate_grows(client):
    client.request("DELETE", "/api/v1/fmsketch/reset", json={})
    client.post("/api/v1/fmsketch/add_many", json={"items": [f"k-{i}" for i in range(500)]})
    assert client.get("/api/v1/fmsketch/estimate").json()["estimate"] > 0.0


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
                  "frugal", "simhashlsh", "randomprojection", "gcs"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
