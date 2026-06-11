"""Phase 152 — tests for the /api/v1/veb endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.van_emde_boas import VanEmdeBoas
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    v = VanEmdeBoas(256)
    for x in (10, 50, 200):
        v.insert(x)
    return TestClient(create_app(van_emde_boas=v))


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_added(client):
    body = client.post("/api/v1/veb/insert", json={"value": 10}).json()
    assert body["added"] is True and body["size"] == 1


def test_insert_duplicate_not_added(client):
    client.post("/api/v1/veb/insert", json={"value": 10})
    body = client.post("/api/v1/veb/insert", json={"value": 10}).json()
    assert body["added"] is False and body["size"] == 1


def test_insert_missing_422(client):
    assert client.post("/api/v1/veb/insert", json={}).status_code == 422


def test_insert_out_of_range_422(client):
    resp = client.post("/api/v1/veb/insert", json={"value": 10 ** 9})
    assert resp.status_code == 422 and "error" in resp.json()


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete_present(filled_client):
    body = filled_client.post("/api/v1/veb/delete", json={"value": 50}).json()
    assert body["deleted"] is True and body["size"] == 2


def test_delete_absent(filled_client):
    body = filled_client.post("/api/v1/veb/delete", json={"value": 99}).json()
    assert body["deleted"] is False and body["size"] == 3


def test_delete_missing_422(client):
    assert client.post("/api/v1/veb/delete", json={}).status_code == 422


# ── member ───────────────────────────────────────────────────────────────────────────────

def test_member_true(filled_client):
    assert filled_client.get("/api/v1/veb/member", params={"value": 50}).json()["member"] is True


def test_member_false(filled_client):
    assert filled_client.get("/api/v1/veb/member", params={"value": 99}).json()["member"] is False


def test_member_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/veb/member", params={"value": 999})
    assert resp.status_code == 422 and "error" in resp.json()


# ── successor / predecessor ──────────────────────────────────────────────────────────────

def test_successor(filled_client):
    assert filled_client.get("/api/v1/veb/successor", params={"value": 10}).json()["successor"] == 50


def test_successor_none(filled_client):
    assert filled_client.get("/api/v1/veb/successor", params={"value": 200}).json()["successor"] is None


def test_predecessor(filled_client):
    assert filled_client.get("/api/v1/veb/predecessor", params={"value": 200}).json()["predecessor"] == 50


def test_predecessor_none(filled_client):
    assert filled_client.get("/api/v1/veb/predecessor", params={"value": 10}).json()["predecessor"] is None


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/veb/stats").json()) == {"size", "universe", "min", "max"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/veb/stats").json()
    assert s["size"] == 3 and s["universe"] == 256 and s["min"] == 10 and s["max"] == 200


def test_stats_defaults(client):
    s = client.get("/api/v1/veb/stats").json()
    assert s["universe"] == 65536 and s["size"] == 0 and s["min"] is None


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/veb/reset").json()
    assert body["size"] == 0 and body["min"] is None


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    for x in (5, 3, 9):
        client.post("/api/v1/veb/insert", json={"value": x})
    s = client.get("/api/v1/veb/stats").json()
    assert s["min"] == 3 and s["max"] == 9
    assert client.get("/api/v1/veb/successor", params={"value": 3}).json()["successor"] == 5
    assert client.get("/api/v1/veb/predecessor", params={"value": 9}).json()["predecessor"] == 5
    client.post("/api/v1/veb/delete", json={"value": 5})
    assert client.get("/api/v1/veb/member", params={"value": 5}).json()["member"] is False
    assert client.get("/api/v1/veb/successor", params={"value": 3}).json()["successor"] == 9


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
                  "suffixautomaton"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
