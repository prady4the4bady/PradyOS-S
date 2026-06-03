"""Phase 132 — tests for the /api/v1/cuckoohash endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.cuckoo_hashtable import CuckooHashTable
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    t = CuckooHashTable(capacity=16, seed=0)
    for i in range(100):
        t.put(f"k{i}", i * 10)
    return TestClient(create_app(cuckoo_hashtable=t))


# ── put ──────────────────────────────────────────────────────────────────────────────

def test_put_returns_size(client):
    resp = client.post("/api/v1/cuckoohash/put", json={"key": "a", "value": 1})
    assert resp.status_code == 200 and resp.json()["size"] == 1


def test_put_missing_key_422(client):
    assert client.post("/api/v1/cuckoohash/put", json={"value": 1}).status_code == 422


def test_put_missing_value_422(client):
    assert client.post("/api/v1/cuckoohash/put", json={"key": "a"}).status_code == 422


def test_put_bool_key_422(client):
    resp = client.post("/api/v1/cuckoohash/put", json={"key": True, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_put_float_key_422(client):
    resp = client.post("/api/v1/cuckoohash/put", json={"key": 3.14, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_put_int_key(client):
    client.post("/api/v1/cuckoohash/put", json={"key": 42, "value": "x"})
    assert client.post("/api/v1/cuckoohash/get", json={"key": 42}).json()["value"] == "x"


# ── get ──────────────────────────────────────────────────────────────────────────────

def test_get_found(filled_client):
    body = filled_client.post("/api/v1/cuckoohash/get", json={"key": "k5"}).json()
    assert body["found"] is True and body["value"] == 50


def test_get_not_found(client):
    body = client.post("/api/v1/cuckoohash/get", json={"key": "absent"}).json()
    assert body["found"] is False and body["value"] is None


def test_get_missing_key_422(client):
    assert client.post("/api/v1/cuckoohash/get", json={}).status_code == 422


def test_put_then_get_roundtrip(client):
    client.post("/api/v1/cuckoohash/put", json={"key": "x", "value": [1, 2, 3]})
    assert client.post("/api/v1/cuckoohash/get", json={"key": "x"}).json()["value"] == [1, 2, 3]


def test_update_value(client):
    client.post("/api/v1/cuckoohash/put", json={"key": "x", "value": 1})
    client.post("/api/v1/cuckoohash/put", json={"key": "x", "value": 2})
    assert client.post("/api/v1/cuckoohash/get", json={"key": "x"}).json()["value"] == 2


# ── remove ───────────────────────────────────────────────────────────────────────────

def test_remove_present(filled_client):
    body = filled_client.request("DELETE", "/api/v1/cuckoohash/remove", json={"key": "k1"}).json()
    assert body["removed"] is True


def test_remove_absent(client):
    body = client.request("DELETE", "/api/v1/cuckoohash/remove", json={"key": "nope"}).json()
    assert body["removed"] is False


def test_remove_missing_key_422(client):
    assert client.request("DELETE", "/api/v1/cuckoohash/remove", json={}).status_code == 422


def test_remove_then_get_not_found(client):
    client.post("/api/v1/cuckoohash/put", json={"key": "x", "value": 1})
    client.request("DELETE", "/api/v1/cuckoohash/remove", json={"key": "x"})
    assert client.post("/api/v1/cuckoohash/get", json={"key": "x"}).json()["found"] is False


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/cuckoohash/stats").json()) == {
        "size", "capacity", "total_slots", "load_factor", "num_rehashes", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/cuckoohash/stats").json()
    assert s["size"] == 0 and s["capacity"] == 16 and s["total_slots"] == 32


def test_stats_reflects_size(filled_client):
    assert filled_client.get("/api/v1/cuckoohash/stats").json()["size"] == 100


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/cuckoohash/reset", json={}).json()
    assert body["size"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/cuckoohash/reset",
                          json={"capacity": 64, "seed": 5}).json()
    assert body["capacity"] == 64 and body["seed"] == 5


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/cuckoohash/reset", json={"capacity": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/cuckoohash/reset").status_code == 200


# ── round-trip under growth ───────────────────────────────────────────────────────────

def test_many_puts_then_gets(client):
    client.request("DELETE", "/api/v1/cuckoohash/reset", json={"capacity": 4})
    for i in range(300):
        client.post("/api/v1/cuckoohash/put", json={"key": f"k{i}", "value": i})
    assert client.post("/api/v1/cuckoohash/get", json={"key": "k299"}).json()["value"] == 299
    assert client.get("/api/v1/cuckoohash/stats").json()["size"] == 300


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
                  "frugal", "simhashlsh", "randomprojection", "gcs", "fmsketch", "ams",
                  "prioritysample"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
