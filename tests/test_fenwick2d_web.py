"""Phase 146 — tests for the /api/v1/fenwick2d endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.fenwick_2d import Fenwick2D
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    ft = Fenwick2D(rows=4, cols=4)
    for (i, j, d) in [(0, 0, 1), (1, 1, 5), (2, 2, 3)]:
        ft.update(i, j, d)
    return TestClient(create_app(fenwick2d=ft))


# ── update ─────────────────────────────────────────────────────────────────────────────

def test_update_returns_total(client):
    body = client.post("/api/v1/fenwick2d/update", json={"i": 0, "j": 0, "delta": 7}).json()
    assert body["total"] == 7


def test_update_missing_fields_422(client):
    assert client.post("/api/v1/fenwick2d/update", json={"i": 0, "j": 0}).status_code == 422


def test_update_out_of_range_422(client):
    resp = client.post("/api/v1/fenwick2d/update", json={"i": 99, "j": 0, "delta": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_update_non_num_delta_422(client):
    resp = client.post("/api/v1/fenwick2d/update", json={"i": 0, "j": 0, "delta": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── prefix_sum ───────────────────────────────────────────────────────────────────────────

def test_prefix_sum(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/prefix_sum", params={"i": 2, "j": 2}).json()["sum"] == 9


def test_prefix_sum_partial(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/prefix_sum", params={"i": 1, "j": 1}).json()["sum"] == 6


def test_prefix_sum_missing_422(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/prefix_sum", params={"i": 2}).status_code == 422


def test_prefix_sum_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/fenwick2d/prefix_sum", params={"i": 4, "j": 0})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_sum ────────────────────────────────────────────────────────────────────────────

def test_range_sum(filled_client):
    body = filled_client.get("/api/v1/fenwick2d/range_sum",
                             params={"r1": 1, "c1": 1, "r2": 2, "c2": 2}).json()
    assert body["sum"] == 8                          # cells (1,1)=5 + (2,2)=3


def test_range_sum_full(filled_client):
    body = filled_client.get("/api/v1/fenwick2d/range_sum",
                             params={"r1": 0, "c1": 0, "r2": 3, "c2": 3}).json()
    assert body["sum"] == 9


def test_range_sum_r1_gt_r2_422(filled_client):
    resp = filled_client.get("/api/v1/fenwick2d/range_sum",
                             params={"r1": 2, "c1": 0, "r2": 1, "c2": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_sum_missing_422(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/range_sum",
                             params={"r1": 0, "c1": 0, "r2": 1}).status_code == 422


# ── point_value ────────────────────────────────────────────────────────────────────────────

def test_point_value(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/point_value", params={"i": 1, "j": 1}).json()["value"] == 5


def test_point_value_zero(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/point_value", params={"i": 3, "j": 3}).json()["value"] == 0


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/fenwick2d/stats").json()) == {"rows", "cols", "cells", "total"}


def test_stats_defaults(client):
    s = client.get("/api/v1/fenwick2d/stats").json()
    assert s["rows"] == 16 and s["cols"] == 16 and s["total"] == 0


def test_stats_after_update(filled_client):
    assert filled_client.get("/api/v1/fenwick2d/stats").json()["total"] == 9


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/fenwick2d/reset", json={}).json()
    assert body["total"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/fenwick2d/reset", json={"rows": 5, "cols": 8}).json()
    assert body["rows"] == 5 and body["cols"] == 8


def test_reset_bad_dims_422(client):
    resp = client.request("DELETE", "/api/v1/fenwick2d/reset", json={"rows": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/fenwick2d/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_update_then_range(client):
    client.request("DELETE", "/api/v1/fenwick2d/reset", json={"rows": 5, "cols": 5})
    for (i, j) in ((1, 1), (2, 2), (3, 3)):
        client.post("/api/v1/fenwick2d/update", json={"i": i, "j": j, "delta": 10})
    assert client.get("/api/v1/fenwick2d/range_sum",
                      params={"r1": 1, "c1": 1, "r2": 3, "c2": 3}).json()["sum"] == 30


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
                  "suffixarray", "ahocorasick", "xortrie", "minmaxheap", "cartesiantree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
