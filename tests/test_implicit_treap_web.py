"""Phase 162 — tests for the /api/v1/implicittreap endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.implicit_treap import ImplicitTreap
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    it = ImplicitTreap()
    for v in (10, 20, 30, 40, 50):
        it.insert(it.size, v)
    return TestClient(create_app(implicit_treap=it))


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_size(client):
    body = client.post("/api/v1/implicittreap/insert", json={"index": 0, "value": 5}).json()
    assert body["size"] == 1


def test_insert_missing_422(client):
    assert client.post("/api/v1/implicittreap/insert", json={"index": 0}).status_code == 422


def test_insert_out_of_range_422(client):
    resp = client.post("/api/v1/implicittreap/insert", json={"index": 5, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_non_num_422(client):
    resp = client.post("/api/v1/implicittreap/insert", json={"index": 0, "value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete(filled_client):
    body = filled_client.post("/api/v1/implicittreap/delete", json={"index": 0}).json()
    assert body["value"] == 10 and body["size"] == 4


def test_delete_empty_422(client):
    resp = client.post("/api/v1/implicittreap/delete", json={"index": 0})
    assert resp.status_code == 422 and "error" in resp.json()


# ── get / set ────────────────────────────────────────────────────────────────────────────

def test_get(filled_client):
    assert filled_client.get("/api/v1/implicittreap/get", params={"index": 2}).json()["value"] == 30


def test_get_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/implicittreap/get", params={"index": 99})
    assert resp.status_code == 422 and "error" in resp.json()


def test_set(filled_client):
    filled_client.post("/api/v1/implicittreap/set", json={"index": 2, "value": 99})
    assert filled_client.get("/api/v1/implicittreap/get", params={"index": 2}).json()["value"] == 99


# ── range_sum ────────────────────────────────────────────────────────────────────────────

def test_range_sum(filled_client):
    assert filled_client.get("/api/v1/implicittreap/range_sum", params={"lo": 0, "hi": 4}).json()["sum"] == 150


def test_range_sum_partial(filled_client):
    assert filled_client.get("/api/v1/implicittreap/range_sum", params={"lo": 1, "hi": 3}).json()["sum"] == 90


def test_range_sum_inverted_422(filled_client):
    resp = filled_client.get("/api/v1/implicittreap/range_sum", params={"lo": 3, "hi": 1})
    assert resp.status_code == 422 and "error" in resp.json()


# ── list / stats / reset ──────────────────────────────────────────────────────────────────

def test_list(filled_client):
    body = filled_client.get("/api/v1/implicittreap/list").json()
    assert body["values"] == [10, 20, 30, 40, 50] and body["size"] == 5


def test_stats_keys(client):
    assert set(client.get("/api/v1/implicittreap/stats").json()) == {"size", "total"}


def test_stats_total(filled_client):
    s = filled_client.get("/api/v1/implicittreap/stats").json()
    assert s["size"] == 5 and s["total"] == 150


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/implicittreap/reset").json()
    assert body["size"] == 0 and body["total"] == 0


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    for v in (1, 2, 3):
        client.post("/api/v1/implicittreap/insert", json={"index": client.get("/api/v1/implicittreap/stats").json()["size"], "value": v})
    client.post("/api/v1/implicittreap/insert", json={"index": 1, "value": 99})    # [1,99,2,3]
    assert client.get("/api/v1/implicittreap/list").json()["values"] == [1, 99, 2, 3]
    client.post("/api/v1/implicittreap/delete", json={"index": 1})                 # [1,2,3]
    assert client.get("/api/v1/implicittreap/list").json()["values"] == [1, 2, 3]


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
                  "rangetree", "leftist", "scapegoat", "binomial", "binarylifting"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
