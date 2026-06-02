"""Phase 119 — tests for the /api/v1/rendezvous endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.rendezvous_hash import RendezvousHash
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    rdv = RendezvousHash(nodes=[f"node{i}" for i in range(5)], seed=0)
    return TestClient(create_app(rendezvous=rdv))


# ── node management ────────────────────────────────────────────────────────────────

def test_add_node(client):
    resp = client.post("/api/v1/rendezvous/nodes", json={"node": "a"})
    assert resp.status_code == 200 and resp.json()["num_nodes"] == 1


def test_add_node_with_weight(client):
    resp = client.post("/api/v1/rendezvous/nodes", json={"node": "a", "weight": 2.5})
    assert resp.status_code == 200 and resp.json()["weight"] == 2.5


def test_add_node_missing_422(client):
    assert client.post("/api/v1/rendezvous/nodes", json={}).status_code == 422


def test_add_node_bad_weight_422(client):
    resp = client.post("/api/v1/rendezvous/nodes", json={"node": "a", "weight": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_remove_node_present(loaded_client):
    body = loaded_client.request("DELETE", "/api/v1/rendezvous/nodes", json={"node": "node0"}).json()
    assert body["removed"] is True and body["num_nodes"] == 4


def test_remove_node_absent(client):
    body = client.request("DELETE", "/api/v1/rendezvous/nodes", json={"node": "ghost"}).json()
    assert body["removed"] is False


def test_remove_node_missing_422(client):
    assert client.request("DELETE", "/api/v1/rendezvous/nodes", json={}).status_code == 422


# ── assign ─────────────────────────────────────────────────────────────────────────

def test_assign_returns_member(loaded_client):
    body = loaded_client.get("/api/v1/rendezvous/assign", params={"key": "mykey"}).json()
    assert body["node"] in [f"node{i}" for i in range(5)]


def test_assign_stable(loaded_client):
    a = loaded_client.get("/api/v1/rendezvous/assign", params={"key": "k"}).json()["node"]
    b = loaded_client.get("/api/v1/rendezvous/assign", params={"key": "k"}).json()["node"]
    assert a == b


def test_assign_no_nodes_400(client):
    resp = client.get("/api/v1/rendezvous/assign", params={"key": "k"})
    assert resp.status_code == 400 and "no nodes" in resp.json()["error"]


def test_assign_missing_key_422(loaded_client):
    assert loaded_client.get("/api/v1/rendezvous/assign").status_code == 422


# ── replicas ─────────────────────────────────────────────────────────────────────

def test_replicas_returns_k(loaded_client):
    body = loaded_client.get("/api/v1/rendezvous/replicas", params={"key": "k", "k": 3}).json()
    assert len(body["replicas"]) == 3 and len(set(body["replicas"])) == 3


def test_first_replica_is_assign(loaded_client):
    key = "somekey"
    assigned = loaded_client.get("/api/v1/rendezvous/assign", params={"key": key}).json()["node"]
    reps = loaded_client.get("/api/v1/rendezvous/replicas", params={"key": key, "k": 3}).json()["replicas"]
    assert reps[0] == assigned


def test_replicas_no_nodes_400(client):
    assert client.get("/api/v1/rendezvous/replicas", params={"key": "k", "k": 2}).status_code == 400


def test_replicas_invalid_k_422(loaded_client):
    assert loaded_client.get("/api/v1/rendezvous/replicas", params={"key": "k", "k": 0}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/rendezvous/stats").json()) == {
        "num_nodes", "nodes", "total_weight", "seed"}


def test_stats_values(loaded_client):
    s = loaded_client.get("/api/v1/rendezvous/stats").json()
    assert s["num_nodes"] == 5 and s["total_weight"] == 5.0


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/rendezvous/reset", json={})
    assert resp.status_code == 200 and resp.json()["num_nodes"] == 0


def test_reset_reconfigures_seed(client):
    assert client.request("DELETE", "/api/v1/rendezvous/reset", json={"seed": 9}).json()["seed"] == 9


# ── round-trip / disruption over HTTP ────────────────────────────────────────────

def test_remove_disruption_over_http(loaded_client):
    keys = [f"k{i}" for i in range(200)]
    before = {k: loaded_client.get("/api/v1/rendezvous/assign", params={"key": k}).json()["node"]
              for k in keys}
    loaded_client.request("DELETE", "/api/v1/rendezvous/nodes", json={"node": "node2"})
    after = {k: loaded_client.get("/api/v1/rendezvous/assign", params={"key": k}).json()["node"]
             for k in keys}
    # keys not on node2 are unchanged
    assert all(after[k] == before[k] for k in keys if before[k] != "node2")


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash", "scalablebloom"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
