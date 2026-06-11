"""Phase 133 — tests for the /api/v1/splaytree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.splay_tree import SplayTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    t = SplayTree()
    for k in range(100):
        t.insert(k, k * 10)
    return TestClient(create_app(splay_tree=t))


# ── insert ─────────────────────────────────────────────────────────────────────────────

def test_insert_returns_root(client):
    resp = client.post("/api/v1/splaytree/insert", json={"key": 5, "value": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["size"] == 1 and body["root_key"] == 5


def test_insert_missing_key_422(client):
    assert client.post("/api/v1/splaytree/insert", json={"value": 1}).status_code == 422


def test_insert_bool_key_422(client):
    resp = client.post("/api/v1/splaytree/insert", json={"key": True, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_without_value(client):
    assert client.post("/api/v1/splaytree/insert", json={"key": 7}).status_code == 200


def test_insert_str_keys(client):
    for s in ("banana", "apple", "cherry"):
        client.post("/api/v1/splaytree/insert", json={"key": s, "value": s})
    assert client.get("/api/v1/splaytree/stats").json()["size"] == 3


def test_insert_mixed_kind_422(client):
    client.post("/api/v1/splaytree/insert", json={"key": 1, "value": 1})
    resp = client.post("/api/v1/splaytree/insert", json={"key": "x", "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


# ── find ─────────────────────────────────────────────────────────────────────────────────

def test_find_found(filled_client):
    body = filled_client.post("/api/v1/splaytree/find", json={"key": 42}).json()
    assert body["found"] is True and body["value"] == 420


def test_find_splays_to_root(filled_client):
    body = filled_client.post("/api/v1/splaytree/find", json={"key": 42}).json()
    assert body["root_key"] == 42                       # accessed key migrated to the root


def test_find_not_found(client):
    body = client.post("/api/v1/splaytree/find", json={"key": "absent"}).json()
    assert body["found"] is False and body["value"] is None


def test_find_missing_key_422(client):
    assert client.post("/api/v1/splaytree/find", json={}).status_code == 422


def test_insert_then_find_roundtrip(client):
    client.post("/api/v1/splaytree/insert", json={"key": "x", "value": [1, 2]})
    assert client.post("/api/v1/splaytree/find", json={"key": "x"}).json()["value"] == [1, 2]


def test_update_value(client):
    client.post("/api/v1/splaytree/insert", json={"key": 1, "value": "a"})
    client.post("/api/v1/splaytree/insert", json={"key": 1, "value": "b"})
    assert client.post("/api/v1/splaytree/find", json={"key": 1}).json()["value"] == "b"


# ── delete ───────────────────────────────────────────────────────────────────────────────

def test_delete_present(filled_client):
    body = filled_client.request("DELETE", "/api/v1/splaytree/delete", json={"key": 50}).json()
    assert body["deleted"] is True and body["size"] == 99


def test_delete_absent(client):
    body = client.request("DELETE", "/api/v1/splaytree/delete", json={"key": 999}).json()
    assert body["deleted"] is False


def test_delete_missing_key_422(client):
    assert client.request("DELETE", "/api/v1/splaytree/delete", json={}).status_code == 422


def test_delete_then_find_not_found(client):
    client.post("/api/v1/splaytree/insert", json={"key": 5, "value": 1})
    client.request("DELETE", "/api/v1/splaytree/delete", json={"key": 5})
    assert client.post("/api/v1/splaytree/find", json={"key": 5}).json()["found"] is False


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/splaytree/stats").json()) == {
        "size", "height", "root_key", "key_kind"}


def test_stats_defaults(client):
    s = client.get("/api/v1/splaytree/stats").json()
    assert s["size"] == 0 and s["root_key"] is None and s["key_kind"] is None


def test_stats_reflects_size(filled_client):
    s = filled_client.get("/api/v1/splaytree/stats").json()
    assert s["size"] == 100 and s["key_kind"] == "num"


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/splaytree/reset").json()
    assert body["size"] == 0 and body["root_key"] is None


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/splaytree/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_many_inserts_then_finds(client):
    for i in range(300):
        client.post("/api/v1/splaytree/insert", json={"key": i, "value": i})
    assert client.post("/api/v1/splaytree/find", json={"key": 299}).json()["value"] == 299
    assert client.get("/api/v1/splaytree/stats").json()["size"] == 300


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
                  "prioritysample", "cuckoohash"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
