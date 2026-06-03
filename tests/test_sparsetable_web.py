"""Phase 138 — tests for the /api/v1/sparsetable endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.sparse_table import SparseTable
from pradyos.sovereign_web import create_app


ARR = [3, 1, 4, 1, 5, 9, 2, 6]


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    return TestClient(create_app(sparse_table=SparseTable(ARR, "min")))


# ── build ──────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/sparsetable/build", json={"values": ARR}).json()
    assert body["size"] == 8 and body["op"] == "min"


def test_build_missing_values_422(client):
    assert client.post("/api/v1/sparsetable/build", json={}).status_code == 422


def test_build_bad_value_422(client):
    resp = client.post("/api/v1/sparsetable/build", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_bad_op_422(client):
    resp = client.post("/api/v1/sparsetable/build", json={"values": [1, 2], "op": "avg"})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_max_op(client):
    body = client.post("/api/v1/sparsetable/build", json={"values": ARR, "op": "max"}).json()
    assert body["op"] == "max"


# ── query ────────────────────────────────────────────────────────────────────────────────

def test_query_full(built_client):
    assert built_client.get("/api/v1/sparsetable/query", params={"lo": 0, "hi": 8}).json()["value"] == 1


def test_query_subrange(built_client):
    assert built_client.get("/api/v1/sparsetable/query", params={"lo": 4, "hi": 6}).json()["value"] == 5


def test_query_max_op(client):
    client.post("/api/v1/sparsetable/build", json={"values": ARR, "op": "max"})
    assert client.get("/api/v1/sparsetable/query", params={"lo": 0, "hi": 8}).json()["value"] == 9


def test_query_missing_param_422(built_client):
    assert built_client.get("/api/v1/sparsetable/query", params={"lo": 0}).status_code == 422


def test_query_lo_ge_hi_422(built_client):
    resp = built_client.get("/api/v1/sparsetable/query", params={"lo": 5, "hi": 5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_query_out_of_range_422(built_client):
    resp = built_client.get("/api/v1/sparsetable/query", params={"lo": 0, "hi": 99})
    assert resp.status_code == 422 and "error" in resp.json()


def test_query_negative_lo_422(built_client):
    assert built_client.get("/api/v1/sparsetable/query", params={"lo": -1, "hi": 3}).status_code == 422


# ── get ──────────────────────────────────────────────────────────────────────────────────

def test_get(built_client):
    assert built_client.get("/api/v1/sparsetable/get", params={"i": 2}).json()["value"] == 4


def test_get_out_of_range_422(built_client):
    resp = built_client.get("/api/v1/sparsetable/get", params={"i": 8})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/sparsetable/stats").json()) == {"size", "op", "levels"}


def test_stats_defaults(client):
    s = client.get("/api/v1/sparsetable/stats").json()
    assert s["size"] == 0 and s["op"] == "min" and s["levels"] == 0


def test_stats_after_build(built_client):
    s = built_client.get("/api/v1/sparsetable/stats").json()
    assert s["size"] == 8 and s["levels"] == 4


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/sparsetable/reset").json()
    assert body["size"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/sparsetable/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/sparsetable/build", json={"values": [10, 20, 5, 30, 15]})
    assert client.get("/api/v1/sparsetable/query", params={"lo": 1, "hi": 4}).json()["value"] == 5


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
                  "skewheap", "intervaltree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
