"""Phase 158 — tests for the /api/v1/leftist endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _insert(client, value):
    return client.post("/api/v1/leftist/insert", json={"value": value}).json()


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_min(client):
    body = client.post("/api/v1/leftist/insert", json={"value": 5}).json()
    assert body["size"] == 1 and body["min"] == 5


def test_insert_missing_422(client):
    assert client.post("/api/v1/leftist/insert", json={}).status_code == 422


def test_insert_non_num_422(client):
    resp = client.post("/api/v1/leftist/insert", json={"value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── find_min ─────────────────────────────────────────────────────────────────────────────

def test_find_min(client):
    for v in (8, 3, 9, 1):
        _insert(client, v)
    assert client.get("/api/v1/leftist/find_min").json()["min"] == 1


def test_find_min_empty_null(client):
    body = client.get("/api/v1/leftist/find_min").json()
    assert body["min"] is None and body["size"] == 0


# ── extract_min ──────────────────────────────────────────────────────────────────────────

def test_extract_min(client):
    _insert(client, 5); _insert(client, 2)
    body = client.post("/api/v1/leftist/extract_min").json()
    assert body["min"] == 2 and body["size"] == 1


def test_extract_min_empty_422(client):
    resp = client.post("/api/v1/leftist/extract_min")
    assert resp.status_code == 422 and "error" in resp.json()


def test_drain_sorted_over_http(client):
    for v in (5, 3, 8, 1, 9, 2):
        _insert(client, v)
    drained = [client.post("/api/v1/leftist/extract_min").json()["min"] for _ in range(6)]
    assert drained == [1, 2, 3, 5, 8, 9]


# ── merge ────────────────────────────────────────────────────────────────────────────────

def test_merge(client):
    _insert(client, 5)
    body = client.post("/api/v1/leftist/merge", json={"values": [1, 9, 3]}).json()
    assert body["size"] == 4 and body["min"] == 1


def test_merge_bad_422(client):
    assert client.post("/api/v1/leftist/merge", json={"values": "nope"}).status_code == 422


def test_merge_non_num_422(client):
    resp = client.post("/api/v1/leftist/merge", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_merge_into_empty(client):
    body = client.post("/api/v1/leftist/merge", json={"values": [7, 2, 5]}).json()
    assert body["size"] == 3 and body["min"] == 2


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/leftist/stats").json()) == {"size", "rank", "min"}


def test_stats_after_insert(client):
    _insert(client, 7); _insert(client, 3)
    s = client.get("/api/v1/leftist/stats").json()
    assert s["size"] == 2 and s["min"] == 3


def test_reset_clears(client):
    _insert(client, 1); _insert(client, 2)
    body = client.request("DELETE", "/api/v1/leftist/reset").json()
    assert body["size"] == 0 and body["min"] is None


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    _insert(client, 10)
    client.post("/api/v1/leftist/merge", json={"values": [5, 20]})
    assert client.get("/api/v1/leftist/find_min").json()["min"] == 5
    assert client.post("/api/v1/leftist/extract_min").json()["min"] == 5
    assert client.get("/api/v1/leftist/find_min").json()["min"] == 10


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
                  "rangetree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
