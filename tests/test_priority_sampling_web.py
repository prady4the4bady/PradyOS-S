"""Phase 131 — tests for the /api/v1/prioritysample endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.priority_sampling import PrioritySample
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def trained_client():
    ps = PrioritySample(capacity=256, seed=0)
    cats = ("x", "y", "z", "w")
    items = [(f"k{i}", (i % 50) + 1, cats[i % 4]) for i in range(2000)]
    for key, w, c in items:
        ps.add(key, w, c)
    true_total = sum(w for _, w, _ in items)
    true_x = sum(w for _, w, c in items if c == "x")
    return TestClient(create_app(priority_sample=ps)), true_total, true_x


# ── add ──────────────────────────────────────────────────────────────────────────────

def test_add_returns_sampled(client):
    resp = client.post("/api/v1/prioritysample/add", json={"key": "a", "weight": 10})
    assert resp.status_code == 200 and resp.json()["sampled"] is True


def test_add_missing_key_422(client):
    assert client.post("/api/v1/prioritysample/add", json={"weight": 5}).status_code == 422


def test_add_missing_weight_422(client):
    assert client.post("/api/v1/prioritysample/add", json={"key": "a"}).status_code == 422


def test_add_negative_weight_422(client):
    resp = client.post("/api/v1/prioritysample/add", json={"key": "a", "weight": -3})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_zero_weight_422(client):
    assert client.post("/api/v1/prioritysample/add",
                       json={"key": "a", "weight": 0}).status_code == 422


def test_add_with_category(client):
    resp = client.post("/api/v1/prioritysample/add",
                       json={"key": "a", "weight": 7, "category": "vip"})
    assert resp.status_code == 200


def test_add_float_key_422(client):
    resp = client.post("/api/v1/prioritysample/add", json={"key": 3.14, "weight": 5})
    assert resp.status_code == 422 and "error" in resp.json()


# ── add_many ─────────────────────────────────────────────────────────────────────────

def test_add_many(client):
    body = client.post("/api/v1/prioritysample/add_many",
                       json={"items": [["a", 1], ["b", 2], ["c", 3]]}).json()
    assert body["added"] == 3 and body["total_estimate"] > 0.0


def test_add_many_missing_422(client):
    assert client.post("/api/v1/prioritysample/add_many", json={}).status_code == 422


def test_add_many_bad_shape_422(client):
    resp = client.post("/api/v1/prioritysample/add_many", json={"items": [["a"]]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── estimate ─────────────────────────────────────────────────────────────────────────

def test_estimate_empty(client):
    body = client.get("/api/v1/prioritysample/estimate").json()
    assert body["estimate"] == 0.0 and body["category"] is None


def test_estimate_keys(client):
    assert set(client.get("/api/v1/prioritysample/estimate").json()) == {"category", "estimate"}


def test_estimate_total(trained_client):
    tc, true_total, _ = trained_client
    est = tc.get("/api/v1/prioritysample/estimate").json()["estimate"]
    assert abs(est / true_total - 1.0) < 0.20


def test_estimate_by_category(trained_client):
    tc, _, true_x = trained_client
    body = tc.get("/api/v1/prioritysample/estimate", params={"category": "x"}).json()
    assert body["category"] == "x" and abs(body["estimate"] / true_x - 1.0) < 0.35


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/prioritysample/stats").json()) == {
        "capacity", "sampled", "num_seen", "threshold", "total_estimate", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/prioritysample/stats").json()
    assert s["capacity"] == 256 and s["sampled"] == 0 and s["num_seen"] == 0


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(trained_client):
    tc, _, _ = trained_client
    body = tc.request("DELETE", "/api/v1/prioritysample/reset", json={}).json()
    assert body["sampled"] == 0 and body["total_estimate"] == 0.0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/prioritysample/reset",
                          json={"capacity": 64, "seed": 7}).json()
    assert body["capacity"] == 64 and body["seed"] == 7


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/prioritysample/reset", json={"capacity": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/prioritysample/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_add_then_estimate_grows(client):
    client.request("DELETE", "/api/v1/prioritysample/reset", json={"capacity": 32})
    client.post("/api/v1/prioritysample/add_many",
                json={"items": [[f"k-{i}", 10] for i in range(200)]})
    assert client.get("/api/v1/prioritysample/estimate").json()["estimate"] > 0.0


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
                  "frugal", "simhashlsh", "randomprojection", "gcs", "fmsketch", "ams"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
