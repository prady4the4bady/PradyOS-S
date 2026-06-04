"""Phase 164 — tests for the /api/v1/tst endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.ternary_search_tree import TernarySearchTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    t = TernarySearchTree()
    for w in ("cat", "car", "card", "dog", "do", "cats"):
        t.insert(w)
    return TestClient(create_app(ternary_search_tree=t))


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_added(client):
    body = client.post("/api/v1/tst/insert", json={"key": "cat"}).json()
    assert body["added"] is True and body["size"] == 1


def test_insert_duplicate(client):
    client.post("/api/v1/tst/insert", json={"key": "cat"})
    body = client.post("/api/v1/tst/insert", json={"key": "cat"}).json()
    assert body["added"] is False and body["size"] == 1


def test_insert_missing_422(client):
    assert client.post("/api/v1/tst/insert", json={}).status_code == 422


def test_insert_empty_422(client):
    resp = client.post("/api/v1/tst/insert", json={"key": ""})
    assert resp.status_code == 422 and "error" in resp.json()


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete(filled_client):
    body = filled_client.post("/api/v1/tst/delete", json={"key": "car"}).json()
    assert body["deleted"] is True and body["size"] == 5


def test_delete_absent(filled_client):
    body = filled_client.post("/api/v1/tst/delete", json={"key": "zzz"}).json()
    assert body["deleted"] is False and body["size"] == 6


# ── contains ─────────────────────────────────────────────────────────────────────────────

def test_contains_true(filled_client):
    assert filled_client.get("/api/v1/tst/contains", params={"key": "card"}).json()["contains"] is True


def test_contains_false(filled_client):
    assert filled_client.get("/api/v1/tst/contains", params={"key": "ca"}).json()["contains"] is False


# ── prefix / longest ─────────────────────────────────────────────────────────────────────

def test_keys_with_prefix(filled_client):
    body = filled_client.get("/api/v1/tst/keys_with_prefix", params={"prefix": "ca"}).json()
    assert body["keys"] == ["car", "card", "cat", "cats"] and body["count"] == 4


def test_keys_with_prefix_empty_all(filled_client):
    body = filled_client.get("/api/v1/tst/keys_with_prefix", params={"prefix": ""}).json()
    assert body["keys"] == ["car", "card", "cat", "cats", "do", "dog"]


def test_longest_prefix_of(filled_client):
    assert filled_client.get("/api/v1/tst/longest_prefix_of", params={"query": "cards"}).json()["longest_prefix"] == "card"


def test_longest_prefix_none(filled_client):
    assert filled_client.get("/api/v1/tst/longest_prefix_of", params={"query": "xyz"}).json()["longest_prefix"] is None


# ── keys / stats / reset ──────────────────────────────────────────────────────────────────

def test_keys(filled_client):
    body = filled_client.get("/api/v1/tst/keys").json()
    assert body["keys"] == ["car", "card", "cat", "cats", "do", "dog"] and body["size"] == 6


def test_stats_keys(client):
    assert set(client.get("/api/v1/tst/stats").json()) == {"size", "nodes"}


def test_stats_after_insert(filled_client):
    assert filled_client.get("/api/v1/tst/stats").json()["size"] == 6


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/tst/reset").json()
    assert body["size"] == 0


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    for w in ("apple", "app", "application", "banana"):
        client.post("/api/v1/tst/insert", json={"key": w})
    assert client.get("/api/v1/tst/keys_with_prefix", params={"prefix": "app"}).json()["keys"] == ["app", "apple", "application"]
    assert client.get("/api/v1/tst/longest_prefix_of", params={"query": "applepie"}).json()["longest_prefix"] == "apple"
    client.post("/api/v1/tst/delete", json={"key": "app"})
    assert client.get("/api/v1/tst/contains", params={"key": "app"}).json()["contains"] is False
    assert client.get("/api/v1/tst/contains", params={"key": "apple"}).json()["contains"] is True


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
                  "rangetree", "leftist", "scapegoat", "binomial", "binarylifting",
                  "implicittreap", "lazysegtree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
