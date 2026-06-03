"""Phase 137 — tests for the /api/v1/intervaltree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.interval_tree import IntervalTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    t = IntervalTree()
    for lo, hi in [(1, 5), (2, 8), (10, 12)]:
        t.insert(lo, hi)
    return TestClient(create_app(interval_tree=t))


# ── insert ─────────────────────────────────────────────────────────────────────────────

def test_insert_returns_size(client):
    body = client.post("/api/v1/intervaltree/insert", json={"low": 1, "high": 5}).json()
    assert body["size"] == 1


def test_insert_missing_fields_422(client):
    assert client.post("/api/v1/intervaltree/insert", json={"low": 1}).status_code == 422


def test_insert_low_gt_high_422(client):
    resp = client.post("/api/v1/intervaltree/insert", json={"low": 5, "high": 2})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_bool_422(client):
    resp = client.post("/api/v1/intervaltree/insert", json={"low": True, "high": 5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_non_numeric_422(client):
    resp = client.post("/api/v1/intervaltree/insert", json={"low": "a", "high": 5})
    assert resp.status_code == 422 and "error" in resp.json()


# ── overlap ──────────────────────────────────────────────────────────────────────────────

def test_overlap(built_client):
    body = built_client.get("/api/v1/intervaltree/overlap", params={"low": 3, "high": 4}).json()
    assert body["intervals"] == [[1, 5], [2, 8]] and body["count"] == 2


def test_overlap_inclusive_endpoints(built_client):
    body = built_client.get("/api/v1/intervaltree/overlap", params={"low": 5, "high": 5}).json()
    assert body["intervals"] == [[1, 5], [2, 8]]          # both contain 5


def test_overlap_empty(built_client):
    body = built_client.get("/api/v1/intervaltree/overlap", params={"low": 20, "high": 30}).json()
    assert body["intervals"] == [] and body["count"] == 0


def test_overlap_missing_param_422(built_client):
    assert built_client.get("/api/v1/intervaltree/overlap", params={"low": 3}).status_code == 422


def test_overlap_low_gt_high_422(built_client):
    resp = built_client.get("/api/v1/intervaltree/overlap", params={"low": 5, "high": 2})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stab ─────────────────────────────────────────────────────────────────────────────────

def test_stab(built_client):
    body = built_client.get("/api/v1/intervaltree/stab", params={"point": 11}).json()
    assert body["intervals"] == [[10, 12]] and body["count"] == 1


def test_stab_multiple(built_client):
    body = built_client.get("/api/v1/intervaltree/stab", params={"point": 3}).json()
    assert body["intervals"] == [[1, 5], [2, 8]]


def test_stab_missing_param_422(built_client):
    assert built_client.get("/api/v1/intervaltree/stab").status_code == 422


# ── remove ───────────────────────────────────────────────────────────────────────────────

def test_remove_present(built_client):
    body = built_client.request("DELETE", "/api/v1/intervaltree/remove",
                                json={"low": 2, "high": 8}).json()
    assert body["removed"] is True and body["size"] == 2


def test_remove_absent(built_client):
    body = built_client.request("DELETE", "/api/v1/intervaltree/remove",
                                json={"low": 99, "high": 100}).json()
    assert body["removed"] is False


def test_remove_missing_fields_422(client):
    assert client.request("DELETE", "/api/v1/intervaltree/remove", json={"low": 1}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/intervaltree/stats").json()) == {
        "size", "max_endpoint", "height"}


def test_stats_defaults(client):
    s = client.get("/api/v1/intervaltree/stats").json()
    assert s["size"] == 0 and s["max_endpoint"] is None


def test_stats_after_insert(built_client):
    s = built_client.get("/api/v1/intervaltree/stats").json()
    assert s["size"] == 3 and s["max_endpoint"] == 12


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/intervaltree/reset").json()
    assert body["size"] == 0 and body["max_endpoint"] is None


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/intervaltree/reset").status_code == 200


# ── float intervals ───────────────────────────────────────────────────────────────────────

def test_float_intervals(client):
    client.post("/api/v1/intervaltree/insert", json={"low": 1.5, "high": 2.5})
    body = client.get("/api/v1/intervaltree/stab", params={"point": 2.0}).json()
    assert body["intervals"] == [[1.5, 2.5]]


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
                  "skewheap"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
