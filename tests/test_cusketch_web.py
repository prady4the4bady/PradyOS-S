"""Phase 123 — tests for the /api/v1/cusketch endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.cu_sketch import CUSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_estimate(client):
    resp = client.post("/api/v1/cusketch/add", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"] == "a" and body["estimate"] == 1 and body["total"] == 1


def test_add_with_amount(client):
    client.post("/api/v1/cusketch/add", json={"item": "a", "amount": 5})
    assert client.get("/api/v1/cusketch/estimate", params={"item": "a"}).json()["estimate"] == 5


def test_add_accumulates(client):
    client.post("/api/v1/cusketch/add", json={"item": "a", "amount": 3})
    client.post("/api/v1/cusketch/add", json={"item": "a", "amount": 4})
    assert client.get("/api/v1/cusketch/estimate", params={"item": "a"}).json()["estimate"] == 7


def test_add_missing_item_422(client):
    assert client.post("/api/v1/cusketch/add", json={}).status_code == 422


def test_add_bad_amount_422(client):
    resp = client.post("/api/v1/cusketch/add", json={"item": "a", "amount": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_negative_amount_422(client):
    assert client.post("/api/v1/cusketch/add", json={"item": "a", "amount": -3}).status_code == 422


# ── estimate ─────────────────────────────────────────────────────────────────────

def test_estimate_never_added_zero(client):
    assert client.get("/api/v1/cusketch/estimate", params={"item": "ghost"}).json()["estimate"] == 0


def test_estimate_missing_param_422(client):
    assert client.get("/api/v1/cusketch/estimate").status_code == 422


def test_never_undercount_over_http(client):
    for i in range(200):
        for _ in range((i % 4) + 1):
            client.post("/api/v1/cusketch/add", json={"item": f"k{i}"})
    # each key added (i%4)+1 times; estimate must be >= that (never undercount)
    assert all(
        client.get("/api/v1/cusketch/estimate", params={"item": f"k{i}"}).json()["estimate"]
        >= (i % 4) + 1 for i in range(0, 200, 10))


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/cusketch/stats").json()) == {
        "width", "depth", "total", "num_counters", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/cusketch/stats").json()
    assert s["width"] == 2048 and s["depth"] == 4 and s["num_counters"] == 8192


def test_stats_tracks_total(client):
    for i in range(10):
        client.post("/api/v1/cusketch/add", json={"item": f"k{i}", "amount": 2})
    assert client.get("/api/v1/cusketch/stats").json()["total"] == 20


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(20):
        client.post("/api/v1/cusketch/add", json={"item": f"k{i}"})
    resp = client.request("DELETE", "/api/v1/cusketch/reset", json={})
    assert resp.status_code == 200 and resp.json()["total"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/cusketch/reset",
                          json={"width": 4096, "depth": 6, "seed": 9}).json()
    assert body["width"] == 4096 and body["depth"] == 6 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/cusketch/reset", json={"width": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/cusketch/reset").status_code == 200


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
                  "rendezvous", "maglev", "iblt", "bbitminhash"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
