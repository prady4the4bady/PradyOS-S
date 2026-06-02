"""Phase 116 — tests for the /api/v1/tinylfu endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.tiny_lfu import TinyLFU
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    t = TinyLFU(sample_size=1_000_000, width=4096, depth=4, seed=0)
    for _ in range(100):
        t.add("popular")
    for _ in range(3):
        t.add("rare")
    return TestClient(create_app(tiny_lfu=t))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_total(client):
    resp = client.post("/api/v1/tinylfu/add", json={"key": "a"})
    assert resp.status_code == 200 and resp.json()["total"] == 1


def test_add_accumulates_total(client):
    for i in range(5):
        client.post("/api/v1/tinylfu/add", json={"key": f"k{i}"})
    assert client.get("/api/v1/tinylfu/stats").json()["total"] == 5


def test_add_missing_key_422(client):
    assert client.post("/api/v1/tinylfu/add", json={}).status_code == 422


def test_add_non_dict_422(client):
    assert client.post("/api/v1/tinylfu/add", json=["x"]).status_code == 422


# ── estimate ─────────────────────────────────────────────────────────────────────

def test_estimate_popular(loaded_client):
    body = loaded_client.get("/api/v1/tinylfu/estimate", params={"key": "popular"}).json()
    assert body["key"] == "popular" and body["estimate"] == 100


def test_estimate_rare(loaded_client):
    assert loaded_client.get("/api/v1/tinylfu/estimate", params={"key": "rare"}).json()["estimate"] == 3


def test_estimate_never_added_zero(client):
    assert client.get("/api/v1/tinylfu/estimate", params={"key": "ghost"}).json()["estimate"] == 0


def test_estimate_missing_param_422(client):
    assert client.get("/api/v1/tinylfu/estimate").status_code == 422


# ── admit ──────────────────────────────────────────────────────────────────────────

def test_admit_hot_over_cold(loaded_client):
    body = loaded_client.post("/api/v1/tinylfu/admit",
                              json={"candidate": "popular", "victim": "rare"}).json()
    assert body["admit"] is True


def test_admit_cold_over_hot(loaded_client):
    body = loaded_client.post("/api/v1/tinylfu/admit",
                              json={"candidate": "rare", "victim": "popular"}).json()
    assert body["admit"] is False


def test_admit_missing_fields_422(client):
    assert client.post("/api/v1/tinylfu/admit", json={"candidate": "a"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/tinylfu/stats").json()) == {
        "sample_size", "width", "depth", "doorkeeper_bits", "total",
        "accesses_since_reset", "resets", "seed"}


def test_stats_default_sample_size(client):
    assert client.get("/api/v1/tinylfu/stats").json()["sample_size"] == 1000


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/tinylfu/reset", json={})
    assert resp.status_code == 200 and resp.json()["total"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/tinylfu/reset",
                          json={"sample_size": 500, "width": 2048, "depth": 5, "seed": 9}).json()
    assert body["sample_size"] == 500 and body["width"] == 2048 and body["depth"] == 5 and body["seed"] == 9


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/tinylfu/reset").status_code == 200


# ── round-trip / aging over HTTP ─────────────────────────────────────────────────

def test_add_estimate_roundtrip(client):
    for _ in range(20):
        client.post("/api/v1/tinylfu/add", json={"key": "rt"})
    assert client.get("/api/v1/tinylfu/estimate", params={"key": "rt"}).json()["estimate"] == 20


def test_aging_over_http(client):
    # small sample_size so a modest flood triggers aging.
    client.request("DELETE", "/api/v1/tinylfu/reset", json={"sample_size": 100, "width": 256})
    for _ in range(40):
        client.post("/api/v1/tinylfu/add", json={"key": "x"})
    before = client.get("/api/v1/tinylfu/estimate", params={"key": "x"}).json()["estimate"]
    for i in range(200):
        client.post("/api/v1/tinylfu/add", json={"key": f"f{i}"})
    after = client.get("/api/v1/tinylfu/estimate", params={"key": "x"}).json()["estimate"]
    assert after < before


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
