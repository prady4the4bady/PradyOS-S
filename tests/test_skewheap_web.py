"""Phase 136 — tests for the /api/v1/skewheap endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.skew_heap import SkewHeap
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    h = SkewHeap()
    for v in (5, 2, 8, 1, 9):
        h.insert(v)
    return TestClient(create_app(skew_heap=h))


# ── insert ─────────────────────────────────────────────────────────────────────────────

def test_insert_returns_min(client):
    body = client.post("/api/v1/skewheap/insert", json={"value": 5}).json()
    assert body["size"] == 1 and body["min"] == 5


def test_insert_lowers_min(client):
    client.post("/api/v1/skewheap/insert", json={"value": 5})
    body = client.post("/api/v1/skewheap/insert", json={"value": 2}).json()
    assert body["min"] == 2 and body["size"] == 2


def test_insert_missing_value_422(client):
    assert client.post("/api/v1/skewheap/insert", json={}).status_code == 422


def test_insert_bool_422(client):
    resp = client.post("/api/v1/skewheap/insert", json={"value": True})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_non_orderable_422(client):
    resp = client.post("/api/v1/skewheap/insert", json={"value": [1, 2]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_mixed_kind_422(client):
    client.post("/api/v1/skewheap/insert", json={"value": 1})
    resp = client.post("/api/v1/skewheap/insert", json={"value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── extract_min ──────────────────────────────────────────────────────────────────────────

def test_extract_min(filled_client):
    body = filled_client.post("/api/v1/skewheap/extract_min").json()
    assert body["min"] == 1 and body["size"] == 4


def test_extract_order(client):
    for v in (5, 2, 8, 1):
        client.post("/api/v1/skewheap/insert", json={"value": v})
    got = [client.post("/api/v1/skewheap/extract_min").json()["min"] for _ in range(4)]
    assert got == [1, 2, 5, 8]


def test_extract_empty_422(client):
    resp = client.post("/api/v1/skewheap/extract_min")
    assert resp.status_code == 422 and "error" in resp.json()


# ── peek ─────────────────────────────────────────────────────────────────────────────────

def test_peek(filled_client):
    assert filled_client.get("/api/v1/skewheap/peek").json() == {"min": 1, "size": 5}


def test_peek_empty(client):
    assert client.get("/api/v1/skewheap/peek").json() == {"min": None, "size": 0}


def test_peek_does_not_remove(filled_client):
    filled_client.get("/api/v1/skewheap/peek")
    assert filled_client.get("/api/v1/skewheap/stats").json()["size"] == 5


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/skewheap/stats").json()) == {"size", "min", "kind"}


def test_stats_defaults(client):
    s = client.get("/api/v1/skewheap/stats").json()
    assert s["size"] == 0 and s["min"] is None and s["kind"] is None


def test_stats_after_insert(filled_client):
    s = filled_client.get("/api/v1/skewheap/stats").json()
    assert s["size"] == 5 and s["min"] == 1 and s["kind"] == "num"


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/skewheap/reset").json()
    assert body["size"] == 0 and body["min"] is None


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/skewheap/reset").status_code == 200


# ── string heap ───────────────────────────────────────────────────────────────────────────

def test_string_heap(client):
    for w in ("banana", "apple", "cherry"):
        client.post("/api/v1/skewheap/insert", json={"value": w})
    assert client.post("/api/v1/skewheap/extract_min").json()["min"] == "apple"


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
                  "prioritysample", "cuckoohash", "splaytree", "rankselect", "wavelet"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
