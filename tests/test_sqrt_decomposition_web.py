"""Phase 147 — tests for the /api/v1/sqrtdecomp endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.sqrt_decomposition import SqrtDecomposition
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    sd = SqrtDecomposition([1, 2, 3, 4, 5, 6, 7, 8])
    return TestClient(create_app(sqrt_decomposition=sd))


# ── range_add ─────────────────────────────────────────────────────────────────────────────

def test_range_add_returns_total(filled_client):
    body = filled_client.post("/api/v1/sqrtdecomp/range_add",
                              json={"lo": 0, "hi": 7, "delta": 10}).json()
    assert body["total"] == 36 + 80


def test_range_add_missing_fields_422(client):
    assert client.post("/api/v1/sqrtdecomp/range_add", json={"lo": 0, "hi": 1}).status_code == 422


def test_range_add_out_of_range_422(client):
    resp = client.post("/api/v1/sqrtdecomp/range_add", json={"lo": 0, "hi": 99, "delta": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_add_lo_gt_hi_422(client):
    resp = client.post("/api/v1/sqrtdecomp/range_add", json={"lo": 5, "hi": 2, "delta": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_add_non_num_delta_422(client):
    resp = client.post("/api/v1/sqrtdecomp/range_add", json={"lo": 0, "hi": 0, "delta": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_sum ─────────────────────────────────────────────────────────────────────────────

def test_range_sum(filled_client):
    assert filled_client.get("/api/v1/sqrtdecomp/range_sum",
                             params={"lo": 0, "hi": 7}).json()["sum"] == 36


def test_range_sum_partial(filled_client):
    assert filled_client.get("/api/v1/sqrtdecomp/range_sum",
                             params={"lo": 2, "hi": 5}).json()["sum"] == 3 + 4 + 5 + 6


def test_range_sum_missing_422(filled_client):
    assert filled_client.get("/api/v1/sqrtdecomp/range_sum", params={"lo": 0}).status_code == 422


def test_range_sum_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/sqrtdecomp/range_sum", params={"lo": 0, "hi": 99})
    assert resp.status_code == 422 and "error" in resp.json()


# ── point_query ───────────────────────────────────────────────────────────────────────────

def test_point_query(filled_client):
    assert filled_client.get("/api/v1/sqrtdecomp/point_query", params={"i": 3}).json()["value"] == 4


def test_point_query_after_add(filled_client):
    filled_client.post("/api/v1/sqrtdecomp/range_add", json={"lo": 0, "hi": 7, "delta": 100})
    assert filled_client.get("/api/v1/sqrtdecomp/point_query", params={"i": 3}).json()["value"] == 104


# ── update ────────────────────────────────────────────────────────────────────────────────

def test_update_returns_total(filled_client):
    body = filled_client.post("/api/v1/sqrtdecomp/update", json={"i": 0, "value": 101}).json()
    assert body["total"] == 36 - 1 + 101


def test_update_missing_422(client):
    assert client.post("/api/v1/sqrtdecomp/update", json={"i": 0}).status_code == 422


def test_update_non_num_422(client):
    resp = client.post("/api/v1/sqrtdecomp/update", json={"i": 0, "value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ─────────────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/sqrtdecomp/stats").json()) == {"size", "block_size", "num_blocks", "total"}


def test_stats_defaults(client):
    s = client.get("/api/v1/sqrtdecomp/stats").json()
    assert s["size"] == 16 and s["total"] == 0 and s["block_size"] == 4


def test_stats_after_build(filled_client):
    assert filled_client.get("/api/v1/sqrtdecomp/stats").json()["total"] == 36


# ── reset ─────────────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/sqrtdecomp/reset", json={}).json()
    assert body["size"] == 0 and body["total"] == 0


def test_reset_with_values(client):
    body = client.request("DELETE", "/api/v1/sqrtdecomp/reset", json={"values": [1, 2, 3]}).json()
    assert body["size"] == 3 and body["total"] == 6


def test_reset_bad_values_422(client):
    resp = client.request("DELETE", "/api/v1/sqrtdecomp/reset", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/sqrtdecomp/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_range_add_then_sum(client):
    client.request("DELETE", "/api/v1/sqrtdecomp/reset", json={"values": [0] * 10})
    client.post("/api/v1/sqrtdecomp/range_add", json={"lo": 2, "hi": 5, "delta": 3})
    assert client.get("/api/v1/sqrtdecomp/range_sum", params={"lo": 2, "hi": 5}).json()["sum"] == 12
    assert client.get("/api/v1/sqrtdecomp/point_query", params={"i": 3}).json()["value"] == 3


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
                  "fenwick2d"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
