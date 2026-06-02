"""Phase 113 — tests for the /api/v1/treap endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.treap import Treap
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    t = Treap(seed=1)
    for k in (50, 30, 70, 10, 40, 60, 90, 20, 80):
        t.insert(k, value=f"v{k}")
    return TestClient(create_app(treap=t))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_returns_size(client):
    resp = client.post("/api/v1/treap/insert", json={"key": 5})
    assert resp.status_code == 200
    assert resp.json()["key"] == 5 and resp.json()["size"] == 1


def test_insert_with_value(client):
    client.post("/api/v1/treap/insert", json={"key": 5, "value": "hello"})
    assert client.get("/api/v1/treap/search", params={"key": 5}).json()["value"] == "hello"


def test_insert_missing_key_422(client):
    assert client.post("/api/v1/treap/insert", json={}).status_code == 422


def test_insert_non_numeric_key_422(client):
    resp = client.post("/api/v1/treap/insert", json={"key": "abc"})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_non_dict_422(client):
    assert client.post("/api/v1/treap/insert", json=["nope"]).status_code == 422


def test_insert_duplicate_updates_no_dup(client):
    client.post("/api/v1/treap/insert", json={"key": 7, "value": "a"})
    resp = client.post("/api/v1/treap/insert", json={"key": 7, "value": "b"})
    assert resp.json()["size"] == 1
    assert client.get("/api/v1/treap/search", params={"key": 7}).json()["value"] == "b"


# ── delete ──────────────────────────────────────────────────────────────────────

def test_delete_present(loaded_client):
    body = loaded_client.request("DELETE", "/api/v1/treap/delete", json={"key": 50}).json()
    assert body["deleted"] is True and body["size"] == 8


def test_delete_absent(client):
    body = client.request("DELETE", "/api/v1/treap/delete", json={"key": 999}).json()
    assert body["deleted"] is False and body["size"] == 0


def test_delete_missing_key_422(client):
    assert client.request("DELETE", "/api/v1/treap/delete", json={}).status_code == 422


# ── search ──────────────────────────────────────────────────────────────────────

def test_search_found(loaded_client):
    body = loaded_client.get("/api/v1/treap/search", params={"key": 40}).json()
    assert body["found"] is True and body["value"] == "v40"


def test_search_not_found(loaded_client):
    body = loaded_client.get("/api/v1/treap/search", params={"key": 999}).json()
    assert body["found"] is False and body["value"] is None


def test_search_missing_param_422(client):
    assert client.get("/api/v1/treap/search").status_code == 422


# ── rank / select (order statistics) ──────────────────────────────────────────────

def test_rank(loaded_client):
    # keys: 10,20,30,40,50,60,70,80,90 → rank(50) = 4
    assert loaded_client.get("/api/v1/treap/rank", params={"key": 50}).json()["rank"] == 4


def test_rank_of_gap(loaded_client):
    assert loaded_client.get("/api/v1/treap/rank", params={"key": 55}).json()["rank"] == 5


def test_select(loaded_client):
    assert loaded_client.get("/api/v1/treap/select", params={"index": 0}).json()["key"] == 10
    assert loaded_client.get("/api/v1/treap/select", params={"index": 8}).json()["key"] == 90


def test_select_out_of_range_400(loaded_client):
    resp = loaded_client.get("/api/v1/treap/select", params={"index": 9})
    assert resp.status_code == 400 and "error" in resp.json()


def test_select_negative_422(client):
    assert client.get("/api/v1/treap/select", params={"index": -1}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/treap/stats").json()) == {"size", "height", "min", "max", "seed"}


def test_stats_empty(client):
    s = client.get("/api/v1/treap/stats").json()
    assert s["size"] == 0 and s["min"] is None and s["max"] is None


def test_stats_reflects_contents(loaded_client):
    s = loaded_client.get("/api/v1/treap/stats").json()
    assert s["size"] == 9 and s["min"] == 10 and s["max"] == 90


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/treap/reset", json={})
    assert resp.status_code == 200 and resp.json()["size"] == 0


def test_reset_reconfigures_seed(client):
    assert client.request("DELETE", "/api/v1/treap/reset", json={"seed": 9}).json()["seed"] == 9


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/treap/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────

def test_insert_then_order_statistics(client):
    for k in (5, 1, 9, 3, 7):
        client.post("/api/v1/treap/insert", json={"key": k})
    assert [client.get("/api/v1/treap/select", params={"index": i}).json()["key"]
            for i in range(5)] == [1, 3, 5, 7, 9]


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
