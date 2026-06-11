"""Phase 149 — tests for the /api/v1/perseg endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.persistent_segment_tree import PersistentSegmentTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    return TestClient(create_app(persistent_segment_tree=PersistentSegmentTree([1, 2, 3, 4])))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/perseg/build", json={"values": [1, 2, 3, 4, 5]}).json()
    assert body["size"] == 5 and body["num_versions"] == 1


def test_build_missing_422(client):
    assert client.post("/api/v1/perseg/build", json={}).status_code == 422


def test_build_empty_422(client):
    resp = client.post("/api/v1/perseg/build", json={"values": []})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_non_num_422(client):
    resp = client.post("/api/v1/perseg/build", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── update ────────────────────────────────────────────────────────────────────────────────

def test_update_returns_new_version(filled_client):
    body = filled_client.post("/api/v1/perseg/update", json={"version": 0, "i": 0, "value": 100}).json()
    assert body["version"] == 1 and body["num_versions"] == 2


def test_update_missing_422(client):
    assert client.post("/api/v1/perseg/update", json={"version": 0, "i": 0}).status_code == 422


def test_update_bad_version_422(filled_client):
    resp = filled_client.post("/api/v1/perseg/update", json={"version": 9, "i": 0, "value": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_update_non_num_422(filled_client):
    resp = filled_client.post("/api/v1/perseg/update", json={"version": 0, "i": 0, "value": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_sum ────────────────────────────────────────────────────────────────────────────

def test_range_sum(filled_client):
    assert filled_client.get("/api/v1/perseg/range_sum",
                             params={"version": 0, "lo": 0, "hi": 3}).json()["sum"] == 10


def test_range_sum_v0_unchanged_after_update(filled_client):
    filled_client.post("/api/v1/perseg/update", json={"version": 0, "i": 0, "value": 100})
    assert filled_client.get("/api/v1/perseg/range_sum",
                             params={"version": 0, "lo": 0, "hi": 3}).json()["sum"] == 10
    assert filled_client.get("/api/v1/perseg/range_sum",
                             params={"version": 1, "lo": 0, "hi": 3}).json()["sum"] == 109


def test_range_sum_missing_422(filled_client):
    assert filled_client.get("/api/v1/perseg/range_sum",
                             params={"version": 0, "lo": 0}).status_code == 422


def test_range_sum_bad_version_422(filled_client):
    resp = filled_client.get("/api/v1/perseg/range_sum", params={"version": 9, "lo": 0, "hi": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_sum_lo_gt_hi_422(filled_client):
    resp = filled_client.get("/api/v1/perseg/range_sum", params={"version": 0, "lo": 2, "hi": 1})
    assert resp.status_code == 422 and "error" in resp.json()


# ── point_query ───────────────────────────────────────────────────────────────────────────

def test_point_query(filled_client):
    assert filled_client.get("/api/v1/perseg/point_query",
                             params={"version": 0, "i": 2}).json()["value"] == 3


def test_point_query_after_update(filled_client):
    filled_client.post("/api/v1/perseg/update", json={"version": 0, "i": 2, "value": 30})
    assert filled_client.get("/api/v1/perseg/point_query", params={"version": 1, "i": 2}).json()["value"] == 30
    assert filled_client.get("/api/v1/perseg/point_query", params={"version": 0, "i": 2}).json()["value"] == 3


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/perseg/stats").json()) == {"size", "num_versions", "nodes"}


def test_stats_defaults(client):
    s = client.get("/api/v1/perseg/stats").json()
    assert s["size"] == 16 and s["num_versions"] == 1


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/perseg/reset").json()
    assert body["num_versions"] == 0 and body["size"] == 0


# ── round-trip / persistence over HTTP ───────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/perseg/build", json={"values": [1, 2, 3, 4, 5]})
    assert client.get("/api/v1/perseg/range_sum",
                      params={"version": 0, "lo": 0, "hi": 4}).json()["sum"] == 15


def test_persistence_over_http(client):
    client.post("/api/v1/perseg/build", json={"values": [10, 20, 30]})
    client.post("/api/v1/perseg/update", json={"version": 0, "i": 0, "value": 99})
    assert client.get("/api/v1/perseg/range_sum", params={"version": 0, "lo": 0, "hi": 2}).json()["sum"] == 60
    assert client.get("/api/v1/perseg/range_sum", params={"version": 1, "lo": 0, "hi": 2}).json()["sum"] == 149


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
                  "fenwick2d", "sqrtdecomp", "lichao"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
