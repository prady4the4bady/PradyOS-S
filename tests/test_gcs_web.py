"""Phase 128 — tests for the /api/v1/gcs endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.golomb_coded_set import GolombCodedSet
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    gcs = GolombCodedSet(["alpha", "beta", "gamma", "delta"], p=0.01, seed=0)
    return TestClient(create_app(gcs=gcs))


# ── build ──────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    resp = client.post("/api/v1/gcs/build", json={"items": ["a", "b", "c"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["num_items"] == 3 and body["num_bits"] > 0


def test_build_then_contains_member(client):
    client.post("/api/v1/gcs/build", json={"items": ["alpha", "beta", "gamma"]})
    assert client.post("/api/v1/gcs/contains", json={"item": "alpha"}).json()["contains"] is True


def test_build_missing_items_422(client):
    assert client.post("/api/v1/gcs/build", json={}).status_code == 422


def test_build_with_config(client):
    body = client.post("/api/v1/gcs/build",
                       json={"items": ["x", "y"], "p": 0.05, "seed": 9}).json()
    assert body["p"] == 0.05 and body["seed"] == 9 and body["num_items"] == 2


def test_build_invalid_p_422(client):
    resp = client.post("/api/v1/gcs/build", json={"items": ["x"], "p": 2.0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_invalid_item_type_422(client):
    resp = client.post("/api/v1/gcs/build", json={"items": ["ok", 3.14]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── contains ─────────────────────────────────────────────────────────────────────────

def test_contains_member(built_client):
    assert built_client.post("/api/v1/gcs/contains", json={"item": "beta"}).json()["contains"] is True


def test_contains_absent_is_bool(built_client):
    body = built_client.post("/api/v1/gcs/contains", json={"item": "not-in-set-xyz"}).json()
    assert isinstance(body["contains"], bool)


def test_contains_int_item(client):
    client.post("/api/v1/gcs/build", json={"items": [10, 20, 30]})
    assert client.post("/api/v1/gcs/contains", json={"item": 20}).json()["contains"] is True


def test_contains_missing_item_422(built_client):
    assert built_client.post("/api/v1/gcs/contains", json={}).status_code == 422


def test_contains_null_item_422(built_client):
    resp = built_client.post("/api/v1/gcs/contains", json={"item": None})
    assert resp.status_code == 422 and "error" in resp.json()


# ── contains_many ─────────────────────────────────────────────────────────────────────

def test_contains_many(built_client):
    body = built_client.post("/api/v1/gcs/contains_many",
                             json={"items": ["alpha", "delta", "absent-zzz"]}).json()
    assert body["results"][0] is True and body["results"][1] is True
    assert len(body["results"]) == 3 and body["count"] >= 2


def test_contains_many_missing_422(built_client):
    assert built_client.post("/api/v1/gcs/contains_many", json={}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/gcs/stats").json()) == {
        "p", "num_items", "universe", "golomb_m", "num_bits", "bits_per_item", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/gcs/stats").json()
    assert s["num_items"] == 0 and s["p"] == 0.01


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    assert built_client.request("DELETE", "/api/v1/gcs/reset", json={}).json()["num_items"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/gcs/reset", json={"p": 0.1, "seed": 4}).json()
    assert body["p"] == 0.1 and body["seed"] == 4


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/gcs/reset", json={"p": 0.0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/gcs/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_rebuild_replaces(client):
    client.post("/api/v1/gcs/build", json={"items": ["one", "two"]})
    client.post("/api/v1/gcs/build", json={"items": ["three", "four", "five"]})
    assert client.get("/api/v1/gcs/stats").json()["num_items"] == 3
    assert client.post("/api/v1/gcs/contains", json={"item": "three"}).json()["contains"] is True


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
                  "frugal", "simhashlsh", "randomprojection"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
