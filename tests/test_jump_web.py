"""Phase 124 — tests for the /api/v1/jump endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.jump_hash import JumpHash
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    return TestClient(create_app(jump_hash=JumpHash(num_buckets=10, seed=0)))


# ── assign ─────────────────────────────────────────────────────────────────────────

def test_assign_in_range(loaded_client):
    body = loaded_client.get("/api/v1/jump/assign", params={"key": "mykey"}).json()
    assert 0 <= body["bucket"] < 10 and body["num_buckets"] == 10


def test_assign_stable(loaded_client):
    a = loaded_client.get("/api/v1/jump/assign", params={"key": "k"}).json()["bucket"]
    b = loaded_client.get("/api/v1/jump/assign", params={"key": "k"}).json()["bucket"]
    assert a == b


def test_assign_missing_key_422(loaded_client):
    assert loaded_client.get("/api/v1/jump/assign").status_code == 422


def test_default_single_bucket(client):
    body = client.get("/api/v1/jump/assign", params={"key": "anything"}).json()
    assert body["bucket"] == 0 and body["num_buckets"] == 1


# ── buckets ──────────────────────────────────────────────────────────────────────

def test_set_buckets(client):
    resp = client.post("/api/v1/jump/buckets", json={"num_buckets": 20})
    assert resp.status_code == 200 and resp.json()["num_buckets"] == 20


def test_set_buckets_missing_422(client):
    assert client.post("/api/v1/jump/buckets", json={}).status_code == 422


def test_set_buckets_invalid_422(client):
    resp = client.post("/api/v1/jump/buckets", json={"num_buckets": 0})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/jump/stats").json()) == {"num_buckets", "seed"}


def test_stats_values(loaded_client):
    assert loaded_client.get("/api/v1/jump/stats").json() == {"num_buckets": 10, "seed": 0}


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/jump/reset",
                          json={"num_buckets": 16, "seed": 9}).json()
    assert body["num_buckets"] == 16 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/jump/reset", json={"num_buckets": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/jump/reset").status_code == 200


# ── minimal disruption over HTTP ──────────────────────────────────────────────────

def test_minimal_disruption_over_http(loaded_client):
    keys = [f"k{i}" for i in range(300)]
    before = {k: loaded_client.get("/api/v1/jump/assign", params={"key": k}).json()["bucket"]
              for k in keys}
    loaded_client.post("/api/v1/jump/buckets", json={"num_buckets": 11})
    after = {k: loaded_client.get("/api/v1/jump/assign", params={"key": k}).json()["bucket"]
             for k in keys}
    # keys that move all go to the new bucket 10; others unchanged.
    assert all(after[k] == 10 for k in keys if after[k] != before[k])


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
                  "rendezvous", "maglev", "iblt", "bbitminhash", "cusketch"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
