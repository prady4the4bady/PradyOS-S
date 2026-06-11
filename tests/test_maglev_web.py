"""Phase 120 — tests for the /api/v1/maglev endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.maglev import MaglevHash
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    mg = MaglevHash(nodes=[f"node{i}" for i in range(6)], table_size=1019, seed=0)
    return TestClient(create_app(maglev=mg))


# ── node management ────────────────────────────────────────────────────────────────

def test_add_node(client):
    resp = client.post("/api/v1/maglev/nodes", json={"node": "a"})
    assert resp.status_code == 200 and resp.json()["added"] is True and resp.json()["num_nodes"] == 1


def test_add_duplicate_false(client):
    client.post("/api/v1/maglev/nodes", json={"node": "a"})
    assert client.post("/api/v1/maglev/nodes", json={"node": "a"}).json()["added"] is False


def test_add_missing_422(client):
    assert client.post("/api/v1/maglev/nodes", json={}).status_code == 422


def test_remove_present(loaded_client):
    body = loaded_client.request("DELETE", "/api/v1/maglev/nodes", json={"node": "node0"}).json()
    assert body["removed"] is True and body["num_nodes"] == 5


def test_remove_absent(client):
    assert client.request("DELETE", "/api/v1/maglev/nodes", json={"node": "ghost"}).json()["removed"] is False


def test_remove_missing_422(client):
    assert client.request("DELETE", "/api/v1/maglev/nodes", json={}).status_code == 422


# ── lookup ─────────────────────────────────────────────────────────────────────────

def test_lookup_member(loaded_client):
    node = loaded_client.get("/api/v1/maglev/lookup", params={"key": "mykey"}).json()["node"]
    assert node in [f"node{i}" for i in range(6)]


def test_lookup_stable(loaded_client):
    a = loaded_client.get("/api/v1/maglev/lookup", params={"key": "k"}).json()["node"]
    b = loaded_client.get("/api/v1/maglev/lookup", params={"key": "k"}).json()["node"]
    assert a == b


def test_lookup_no_nodes_400(client):
    resp = client.get("/api/v1/maglev/lookup", params={"key": "k"})
    assert resp.status_code == 400 and "no nodes" in resp.json()["error"]


def test_lookup_missing_key_422(loaded_client):
    assert loaded_client.get("/api/v1/maglev/lookup").status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/maglev/stats").json()) == {
        "num_nodes", "table_size", "nodes", "min_load", "max_load", "load_ratio", "seed"}


def test_stats_default_table_size(client):
    assert client.get("/api/v1/maglev/stats").json()["table_size"] == 65537


def test_stats_even_load(loaded_client):
    s = loaded_client.get("/api/v1/maglev/stats").json()
    assert s["num_nodes"] == 6 and s["load_ratio"] < 1.10


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/maglev/reset", json={})
    assert resp.status_code == 200 and resp.json()["num_nodes"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/maglev/reset",
                          json={"table_size": 2000, "seed": 9}).json()
    assert body["table_size"] == 2003 and body["seed"] == 9       # bumped to next prime


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/maglev/reset", json={"table_size": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/maglev/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────

def test_add_lookup_roundtrip(client):
    client.request("DELETE", "/api/v1/maglev/reset", json={"table_size": 1019})
    for i in range(5):
        client.post("/api/v1/maglev/nodes", json={"node": f"s{i}"})
    node = client.get("/api/v1/maglev/lookup", params={"key": "abc"}).json()["node"]
    assert node in [f"s{i}" for i in range(5)]


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
                  "rendezvous"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
