"""Phase 144 — tests for the /api/v1/minmaxheap endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.min_max_heap import MinMaxHeap
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    h = MinMaxHeap()
    for v in (5, 2, 8, 1, 9):
        h.push(v)
    return TestClient(create_app(min_max_heap=h))


# ── push ───────────────────────────────────────────────────────────────────────────────

def test_push_returns_min_max(client):
    body = client.post("/api/v1/minmaxheap/push", json={"value": 5}).json()
    assert body["size"] == 1 and body["min"] == 5 and body["max"] == 5


def test_push_updates_min_max(client):
    client.post("/api/v1/minmaxheap/push", json={"value": 5})
    body = client.post("/api/v1/minmaxheap/push", json={"value": 1}).json()
    assert body["min"] == 1 and body["max"] == 5 and body["size"] == 2


def test_push_missing_value_422(client):
    assert client.post("/api/v1/minmaxheap/push", json={}).status_code == 422


def test_push_bool_422(client):
    resp = client.post("/api/v1/minmaxheap/push", json={"value": True})
    assert resp.status_code == 422 and "error" in resp.json()


def test_push_mixed_kind_422(client):
    client.post("/api/v1/minmaxheap/push", json={"value": 1})
    resp = client.post("/api/v1/minmaxheap/push", json={"value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── extract ────────────────────────────────────────────────────────────────────────────────

def test_extract_min(filled_client):
    body = filled_client.post("/api/v1/minmaxheap/extract_min").json()
    assert body["min"] == 1 and body["size"] == 4


def test_extract_max(filled_client):
    body = filled_client.post("/api/v1/minmaxheap/extract_max").json()
    assert body["max"] == 9 and body["size"] == 4


def test_extract_min_order(client):
    for v in (5, 2, 8, 1):
        client.post("/api/v1/minmaxheap/push", json={"value": v})
    got = [client.post("/api/v1/minmaxheap/extract_min").json()["min"] for _ in range(4)]
    assert got == [1, 2, 5, 8]


def test_extract_max_order(client):
    for v in (5, 2, 8, 1):
        client.post("/api/v1/minmaxheap/push", json={"value": v})
    got = [client.post("/api/v1/minmaxheap/extract_max").json()["max"] for _ in range(4)]
    assert got == [8, 5, 2, 1]


def test_extract_empty_422(client):
    assert client.post("/api/v1/minmaxheap/extract_min").status_code == 422
    assert client.post("/api/v1/minmaxheap/extract_max").status_code == 422


# ── peek ─────────────────────────────────────────────────────────────────────────────────

def test_peek(filled_client):
    assert filled_client.get("/api/v1/minmaxheap/peek").json() == {"min": 1, "max": 9, "size": 5}


def test_peek_empty(client):
    assert client.get("/api/v1/minmaxheap/peek").json() == {"min": None, "max": None, "size": 0}


def test_peek_does_not_remove(filled_client):
    filled_client.get("/api/v1/minmaxheap/peek")
    assert filled_client.get("/api/v1/minmaxheap/stats").json()["size"] == 5


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/minmaxheap/stats").json()) == {"size", "min", "max", "kind"}


def test_stats_defaults(client):
    s = client.get("/api/v1/minmaxheap/stats").json()
    assert s["size"] == 0 and s["min"] is None and s["max"] is None


def test_stats_after_push(filled_client):
    s = filled_client.get("/api/v1/minmaxheap/stats").json()
    assert s["size"] == 5 and s["min"] == 1 and s["max"] == 9 and s["kind"] == "num"


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/minmaxheap/reset").json()
    assert body["size"] == 0 and body["min"] is None


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/minmaxheap/reset").status_code == 200


# ── string heap ───────────────────────────────────────────────────────────────────────────

def test_string_heap(client):
    for w in ("banana", "apple", "cherry"):
        client.post("/api/v1/minmaxheap/push", json={"value": w})
    assert client.post("/api/v1/minmaxheap/extract_min").json()["min"] == "apple"
    assert client.post("/api/v1/minmaxheap/extract_max").json()["max"] == "cherry"


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
                  "skewheap", "intervaltree", "sparsetable", "kdtree", "radixtree",
                  "suffixarray", "ahocorasick", "xortrie"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
