"""Phase 159 — tests for the /api/v1/scapegoat endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.scapegoat_tree import ScapegoatTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    t = ScapegoatTree()
    for k in (50, 30, 70, 20, 40, 60, 80, 10, 90):
        t.insert(k)
    return TestClient(create_app(scapegoat_tree=t))


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_added(client):
    body = client.post("/api/v1/scapegoat/insert", json={"key": 5}).json()
    assert body["added"] is True and body["size"] == 1


def test_insert_duplicate_not_added(client):
    client.post("/api/v1/scapegoat/insert", json={"key": 5})
    body = client.post("/api/v1/scapegoat/insert", json={"key": 5}).json()
    assert body["added"] is False and body["size"] == 1


def test_insert_missing_422(client):
    assert client.post("/api/v1/scapegoat/insert", json={}).status_code == 422


def test_insert_unorderable_422(client):
    resp = client.post("/api/v1/scapegoat/insert", json={"key": [1, 2]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete_present(filled_client):
    body = filled_client.post("/api/v1/scapegoat/delete", json={"key": 30}).json()
    assert body["deleted"] is True and body["size"] == 8


def test_delete_absent(filled_client):
    body = filled_client.post("/api/v1/scapegoat/delete", json={"key": 999}).json()
    assert body["deleted"] is False and body["size"] == 9


def test_delete_missing_422(client):
    assert client.post("/api/v1/scapegoat/delete", json={}).status_code == 422


# ── contains ─────────────────────────────────────────────────────────────────────────────

def test_contains_true(filled_client):
    assert filled_client.get("/api/v1/scapegoat/contains", params={"key": 40}).json()["contains"] is True


def test_contains_false(filled_client):
    assert filled_client.get("/api/v1/scapegoat/contains", params={"key": 45}).json()["contains"] is False


# ── keys ─────────────────────────────────────────────────────────────────────────────────

def test_keys_sorted(filled_client):
    body = filled_client.get("/api/v1/scapegoat/keys").json()
    assert body["keys"] == [10, 20, 30, 40, 50, 60, 70, 80, 90] and body["size"] == 9


def test_keys_empty(client):
    body = client.get("/api/v1/scapegoat/keys").json()
    assert body["keys"] == [] and body["size"] == 0


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/scapegoat/stats").json()) == {"size", "height", "alpha", "min", "max"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/scapegoat/stats").json()
    assert s["size"] == 9 and s["min"] == 10 and s["max"] == 90


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/scapegoat/reset").json()
    assert body["size"] == 0 and body["min"] is None and body["height"] == 0


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    for k in (10, 20, 30):
        client.post("/api/v1/scapegoat/insert", json={"key": k})
    assert client.get("/api/v1/scapegoat/contains", params={"key": 20}).json()["contains"] is True
    assert client.get("/api/v1/scapegoat/keys").json()["keys"] == [10, 20, 30]
    client.post("/api/v1/scapegoat/delete", json={"key": 20})
    assert client.get("/api/v1/scapegoat/contains", params={"key": 20}).json()["contains"] is False
    assert client.get("/api/v1/scapegoat/keys").json()["keys"] == [10, 30]


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
                  "rangetree", "leftist"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
