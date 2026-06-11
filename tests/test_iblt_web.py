"""Phase 121 — tests for the /api/v1/iblt endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.iblt import InvertibleBloomLookupTable
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def overloaded_client():
    t = InvertibleBloomLookupTable(num_cells=200, num_hashes=4, seed=0)
    for i in range(2000):
        t.insert(f"x{i}", i)
    return TestClient(create_app(iblt=t))


# ── insert / delete ────────────────────────────────────────────────────────────────

def test_insert_returns_size(client):
    resp = client.post("/api/v1/iblt/insert", json={"key": "a", "value": 1})
    assert resp.status_code == 200 and resp.json()["size"] == 1


def test_insert_missing_key_422(client):
    assert client.post("/api/v1/iblt/insert", json={"value": 1}).status_code == 422


def test_insert_missing_value_422(client):
    assert client.post("/api/v1/iblt/insert", json={"key": "a"}).status_code == 422


def test_delete_returns_size(client):
    client.post("/api/v1/iblt/insert", json={"key": "a", "value": 1})
    body = client.request("DELETE", "/api/v1/iblt/delete", json={"key": "a", "value": 1}).json()
    assert body["size"] == 0


def test_delete_missing_422(client):
    assert client.request("DELETE", "/api/v1/iblt/delete", json={"key": "a"}).status_code == 422


# ── get ──────────────────────────────────────────────────────────────────────────

def test_get_found(client):
    client.post("/api/v1/iblt/insert", json={"key": "hello", "value": "world"})
    body = client.get("/api/v1/iblt/get", params={"key": "hello"}).json()
    assert body["found"] is True and body["value"] == "world"


def test_get_absent(client):
    body = client.get("/api/v1/iblt/get", params={"key": "ghost"}).json()
    assert body["found"] is False and body["value"] is None


def test_get_missing_param_422(client):
    assert client.get("/api/v1/iblt/get").status_code == 422


# ── list ───────────────────────────────────────────────────────────────────────

def test_list_decodes_inserts(client):
    for i in range(30):
        client.post("/api/v1/iblt/insert", json={"key": f"k{i}", "value": i})
    body = client.get("/api/v1/iblt/list").json()
    assert body["count"] == 30
    decoded = {e["key"]: e["value"] for e in body["entries"]}
    assert decoded == {f"k{i}": i for i in range(30)}


def test_list_empty(client):
    body = client.get("/api/v1/iblt/list").json()
    assert body["count"] == 0 and body["entries"] == []


def test_list_overloaded_400(overloaded_client):
    resp = overloaded_client.get("/api/v1/iblt/list")
    assert resp.status_code == 400 and "decode" in resp.json()["error"]


# ── reconcile (set difference) ────────────────────────────────────────────────────

def test_reconcile_set_difference(client):
    for i in range(10):                               # here = k0..k9
        client.post("/api/v1/iblt/insert", json={"key": f"k{i}", "value": i})
    pairs = [[f"k{i}", i] for i in range(5, 15)]      # other = k5..k14
    body = client.post("/api/v1/iblt/reconcile", json={"pairs": pairs}).json()
    only_here = sorted(int(e["key"][1:]) for e in body["only_here"])
    only_other = sorted(int(e["key"][1:]) for e in body["only_other"])
    assert only_here == [0, 1, 2, 3, 4]
    assert only_other == [10, 11, 12, 13, 14]


def test_reconcile_identical_empty(client):
    for i in range(10):
        client.post("/api/v1/iblt/insert", json={"key": f"k{i}", "value": i})
    pairs = [[f"k{i}", i] for i in range(10)]
    body = client.post("/api/v1/iblt/reconcile", json={"pairs": pairs}).json()
    assert body["only_here"] == [] and body["only_other"] == []


def test_reconcile_pairs_not_list_422(client):
    assert client.post("/api/v1/iblt/reconcile", json={"pairs": "x"}).status_code == 422


def test_reconcile_bad_pair_422(client):
    assert client.post("/api/v1/iblt/reconcile", json={"pairs": [["k"]]}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/iblt/stats").json()) == {
        "size", "num_cells", "num_hashes", "listable", "seed"}


def test_stats_values(client):
    for i in range(20):
        client.post("/api/v1/iblt/insert", json={"key": f"k{i}", "value": i})
    s = client.get("/api/v1/iblt/stats").json()
    assert s["size"] == 20 and s["listable"] is True


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(20):
        client.post("/api/v1/iblt/insert", json={"key": f"k{i}", "value": i})
    resp = client.request("DELETE", "/api/v1/iblt/reset")
    assert resp.status_code == 200 and resp.json()["size"] == 0


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
                  "rendezvous", "maglev"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
