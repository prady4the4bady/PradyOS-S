"""Phase 160 — tests for the /api/v1/binomial endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _insert(client, value):
    return client.post("/api/v1/binomial/insert", json={"value": value}).json()["handle"]


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_handle(client):
    body = client.post("/api/v1/binomial/insert", json={"value": 5}).json()
    assert "handle" in body and body["size"] == 1 and body["min"] == 5


def test_insert_missing_422(client):
    assert client.post("/api/v1/binomial/insert", json={}).status_code == 422


def test_insert_non_num_422(client):
    resp = client.post("/api/v1/binomial/insert", json={"value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── find_min ─────────────────────────────────────────────────────────────────────────────

def test_find_min(client):
    for v in (8, 3, 9, 1):
        _insert(client, v)
    assert client.get("/api/v1/binomial/find_min").json()["min"] == 1


def test_find_min_empty_null(client):
    body = client.get("/api/v1/binomial/find_min").json()
    assert body["min"] is None and body["size"] == 0


# ── extract_min ──────────────────────────────────────────────────────────────────────────

def test_extract_min(client):
    _insert(client, 5); _insert(client, 2)
    body = client.post("/api/v1/binomial/extract_min").json()
    assert body["min"] == 2 and body["size"] == 1


def test_extract_min_empty_422(client):
    resp = client.post("/api/v1/binomial/extract_min")
    assert resp.status_code == 422 and "error" in resp.json()


def test_drain_sorted_over_http(client):
    for v in (5, 3, 8, 1, 9, 2):
        _insert(client, v)
    drained = [client.post("/api/v1/binomial/extract_min").json()["min"] for _ in range(6)]
    assert drained == [1, 2, 3, 5, 8, 9]


# ── decrease_key ─────────────────────────────────────────────────────────────────────────

def test_decrease_key_to_new_min(client):
    _insert(client, 10); _insert(client, 20); h = _insert(client, 30)
    body = client.post("/api/v1/binomial/decrease_key", json={"handle": h, "value": 1}).json()
    assert body["min"] == 1


def test_decrease_key_missing_422(client):
    assert client.post("/api/v1/binomial/decrease_key", json={"handle": 0}).status_code == 422


def test_decrease_key_increase_422(client):
    h = _insert(client, 5)
    resp = client.post("/api/v1/binomial/decrease_key", json={"handle": h, "value": 9})
    assert resp.status_code == 422 and "error" in resp.json()


def test_decrease_key_bad_handle_422(client):
    resp = client.post("/api/v1/binomial/decrease_key", json={"handle": 999999999, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


# ── merge ────────────────────────────────────────────────────────────────────────────────

def test_merge(client):
    _insert(client, 5)
    body = client.post("/api/v1/binomial/merge", json={"values": [1, 9, 3]}).json()
    assert body["size"] == 4 and body["min"] == 1


def test_merge_bad_422(client):
    assert client.post("/api/v1/binomial/merge", json={"values": "nope"}).status_code == 422


def test_merge_non_num_422(client):
    resp = client.post("/api/v1/binomial/merge", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/binomial/stats").json()) == {"size", "num_trees", "min"}


def test_stats_after_insert(client):
    _insert(client, 7); _insert(client, 3)
    s = client.get("/api/v1/binomial/stats").json()
    assert s["size"] == 2 and s["min"] == 3


def test_reset_clears(client):
    _insert(client, 1); _insert(client, 2)
    body = client.request("DELETE", "/api/v1/binomial/reset").json()
    assert body["size"] == 0 and body["min"] is None


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    h1 = _insert(client, 100)
    _insert(client, 50)
    client.post("/api/v1/binomial/merge", json={"values": [30, 70]})
    client.post("/api/v1/binomial/decrease_key", json={"handle": h1, "value": 1})
    assert client.get("/api/v1/binomial/find_min").json()["min"] == 1
    assert client.post("/api/v1/binomial/extract_min").json()["min"] == 1
    assert client.get("/api/v1/binomial/find_min").json()["min"] == 30


# ── regression ────────────────────────────────────────────────────────────────────────────

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
                  "prioritysample", "cuckoohash", "splaytree", "rankselect", "wavelet",
                  "skewheap", "intervaltree", "sparsetable", "kdtree", "radixtree",
                  "suffixarray", "ahocorasick", "xortrie", "minmaxheap", "cartesiantree",
                  "fenwick2d", "sqrtdecomp", "lichao", "perseg", "pairingheap",
                  "suffixautomaton", "veb", "prquadtree", "fibonacci", "avl", "btree",
                  "rangetree", "leftist", "scapegoat"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
