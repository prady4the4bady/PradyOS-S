"""Phase 140 — tests for the /api/v1/radixtree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.radix_tree import RadixTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    rt = RadixTree()
    for k, v in [("apple", 1), ("app", 2), ("application", 3), ("banana", 4)]:
        rt.insert(k, v)
    return TestClient(create_app(radix_tree=rt))


# ── insert ─────────────────────────────────────────────────────────────────────────────

def test_insert_returns_size(client):
    body = client.post("/api/v1/radixtree/insert", json={"key": "hello", "value": 1}).json()
    assert body["size"] == 1


def test_insert_missing_key_422(client):
    assert client.post("/api/v1/radixtree/insert", json={"value": 1}).status_code == 422


def test_insert_non_str_key_422(client):
    resp = client.post("/api/v1/radixtree/insert", json={"key": 5, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_then_search(client):
    client.post("/api/v1/radixtree/insert", json={"key": "x", "value": [1, 2]})
    assert client.post("/api/v1/radixtree/search", json={"key": "x"}).json()["value"] == [1, 2]


def test_update_value(client):
    client.post("/api/v1/radixtree/insert", json={"key": "k", "value": 1})
    client.post("/api/v1/radixtree/insert", json={"key": "k", "value": 2})
    assert client.post("/api/v1/radixtree/search", json={"key": "k"}).json()["value"] == 2


# ── search ─────────────────────────────────────────────────────────────────────────────

def test_search_found(filled_client):
    body = filled_client.post("/api/v1/radixtree/search", json={"key": "app"}).json()
    assert body["found"] is True and body["value"] == 2


def test_search_not_found(filled_client):
    body = filled_client.post("/api/v1/radixtree/search", json={"key": "appl"}).json()
    assert body["found"] is False and body["value"] is None


def test_search_missing_key_422(client):
    assert client.post("/api/v1/radixtree/search", json={}).status_code == 422


# ── prefix_search ─────────────────────────────────────────────────────────────────────────

def test_prefix_search(filled_client):
    body = filled_client.post("/api/v1/radixtree/prefix_search", json={"prefix": "app"}).json()
    assert body["results"] == [["app", 2], ["apple", 1], ["application", 3]] and body["count"] == 3


def test_prefix_search_all(filled_client):
    body = filled_client.post("/api/v1/radixtree/prefix_search", json={"prefix": ""}).json()
    assert body["count"] == 4


def test_prefix_search_no_match(filled_client):
    body = filled_client.post("/api/v1/radixtree/prefix_search", json={"prefix": "zzz"}).json()
    assert body["results"] == [] and body["count"] == 0


def test_prefix_search_missing_422(client):
    assert client.post("/api/v1/radixtree/prefix_search", json={}).status_code == 422


# ── delete ───────────────────────────────────────────────────────────────────────────────

def test_delete_present(filled_client):
    body = filled_client.request("DELETE", "/api/v1/radixtree/delete", json={"key": "app"}).json()
    assert body["deleted"] is True and body["size"] == 3


def test_delete_absent(filled_client):
    body = filled_client.request("DELETE", "/api/v1/radixtree/delete", json={"key": "zzz"}).json()
    assert body["deleted"] is False


def test_delete_missing_key_422(client):
    assert client.request("DELETE", "/api/v1/radixtree/delete", json={}).status_code == 422


def test_delete_then_search_gone(filled_client):
    filled_client.request("DELETE", "/api/v1/radixtree/delete", json={"key": "app"})
    assert filled_client.post("/api/v1/radixtree/search", json={"key": "app"}).json()["found"] is False
    # siblings survive the re-merge
    assert filled_client.post("/api/v1/radixtree/search", json={"key": "apple"}).json()["value"] == 1


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/radixtree/stats").json()) == {
        "num_keys", "num_nodes", "compression_ratio", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/radixtree/stats").json()
    assert s["num_keys"] == 0


def test_stats_after_insert(filled_client):
    s = filled_client.get("/api/v1/radixtree/stats").json()
    assert s["num_keys"] == 4 and s["compression_ratio"] > 1.0


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/radixtree/reset").json()
    assert body["num_keys"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/radixtree/reset").status_code == 200


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
                  "prioritysample", "cuckoohash", "splaytree", "rankselect", "wavelet",
                  "skewheap", "intervaltree", "sparsetable", "kdtree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
