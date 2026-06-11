"""Phase 155 — tests for the /api/v1/avl endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.avl_tree import AVLTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    t = AVLTree()
    for k in (50, 30, 70, 20, 40, 60, 80):
        t.insert(k)
    return TestClient(create_app(avl_tree=t))


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_added(client):
    body = client.post("/api/v1/avl/insert", json={"key": 5}).json()
    assert body["added"] is True and body["size"] == 1


def test_insert_duplicate_not_added(client):
    client.post("/api/v1/avl/insert", json={"key": 5})
    body = client.post("/api/v1/avl/insert", json={"key": 5}).json()
    assert body["added"] is False and body["size"] == 1


def test_insert_missing_422(client):
    assert client.post("/api/v1/avl/insert", json={}).status_code == 422


def test_insert_unorderable_422(client):
    resp = client.post("/api/v1/avl/insert", json={"key": [1, 2]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete_present(filled_client):
    body = filled_client.post("/api/v1/avl/delete", json={"key": 30}).json()
    assert body["deleted"] is True and body["size"] == 6


def test_delete_absent(filled_client):
    body = filled_client.post("/api/v1/avl/delete", json={"key": 999}).json()
    assert body["deleted"] is False and body["size"] == 7


def test_delete_missing_422(client):
    assert client.post("/api/v1/avl/delete", json={}).status_code == 422


# ── contains ─────────────────────────────────────────────────────────────────────────────

def test_contains_true(filled_client):
    assert filled_client.get("/api/v1/avl/contains", params={"key": 40}).json()["contains"] is True


def test_contains_false(filled_client):
    assert filled_client.get("/api/v1/avl/contains", params={"key": 45}).json()["contains"] is False


# ── successor / predecessor ──────────────────────────────────────────────────────────────

def test_successor(filled_client):
    assert filled_client.get("/api/v1/avl/successor", params={"key": 50}).json()["successor"] == 60


def test_successor_none(filled_client):
    assert filled_client.get("/api/v1/avl/successor", params={"key": 80}).json()["successor"] is None


def test_predecessor(filled_client):
    assert filled_client.get("/api/v1/avl/predecessor", params={"key": 50}).json()["predecessor"] == 40


def test_predecessor_none(filled_client):
    assert filled_client.get("/api/v1/avl/predecessor", params={"key": 20}).json()["predecessor"] is None


def test_successor_absent_key(filled_client):
    assert filled_client.get("/api/v1/avl/successor", params={"key": 35}).json()["successor"] == 40


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/avl/stats").json()) == {"size", "height", "min", "max"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/avl/stats").json()
    assert s["size"] == 7 and s["min"] == 20 and s["max"] == 80


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/avl/reset").json()
    assert body["size"] == 0 and body["min"] is None and body["height"] == 0


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    for k in (10, 20, 30):
        client.post("/api/v1/avl/insert", json={"key": k})
    assert client.get("/api/v1/avl/contains", params={"key": 20}).json()["contains"] is True
    assert client.get("/api/v1/avl/successor", params={"key": 10}).json()["successor"] == 20
    client.post("/api/v1/avl/delete", json={"key": 20})
    assert client.get("/api/v1/avl/contains", params={"key": 20}).json()["contains"] is False
    assert client.get("/api/v1/avl/successor", params={"key": 10}).json()["successor"] == 30


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
                  "suffixautomaton", "veb", "prquadtree", "fibonacci"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
