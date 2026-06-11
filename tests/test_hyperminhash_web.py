"""Phase 117 — tests for the /api/v1/hyperminhash endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.hyper_minhash import HyperMinHash
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    h = HyperMinHash(p=12, r=8, seed=0)
    h.add_many(range(10000))
    return TestClient(create_app(hyper_minhash=h))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_cardinality(client):
    resp = client.post("/api/v1/hyperminhash/add", json={"element": "a"})
    assert resp.status_code == 200 and resp.json()["cardinality"] > 0


def test_add_missing_element_422(client):
    assert client.post("/api/v1/hyperminhash/add", json={}).status_code == 422


def test_add_non_dict_422(client):
    assert client.post("/api/v1/hyperminhash/add", json=["x"]).status_code == 422


# ── cardinality ──────────────────────────────────────────────────────────────────

def test_cardinality_empty_zero(client):
    assert client.get("/api/v1/hyperminhash/cardinality").json()["cardinality"] == 0.0


def test_cardinality_accurate(loaded_client):
    est = loaded_client.get("/api/v1/hyperminhash/cardinality").json()["cardinality"]
    assert abs(est - 10000) / 10000 < 0.05


# ── compare (jaccard / union / intersection) ──────────────────────────────────────

def test_compare_self_jaccard_one(loaded_client):
    body = loaded_client.post("/api/v1/hyperminhash/compare",
                              json={"tokens": list(range(10000))}).json()
    assert abs(body["jaccard"] - 1.0) < 1e-9


def test_compare_partial_overlap(loaded_client):
    body = loaded_client.post("/api/v1/hyperminhash/compare",
                              json={"tokens": list(range(5000, 15000))}).json()
    # true Jaccard(0..10000, 5000..15000) = 5000/15000 = 0.333
    assert abs(body["jaccard"] - 0.3333) < 0.10
    assert abs(body["union"] - 15000) / 15000 < 0.06
    assert abs(body["intersection"] - 5000) / 5000 < 0.20


def test_compare_disjoint(loaded_client):
    body = loaded_client.post("/api/v1/hyperminhash/compare",
                              json={"tokens": list(range(50000, 60000))}).json()
    assert body["jaccard"] < 0.02


def test_compare_tokens_not_list_422(client):
    assert client.post("/api/v1/hyperminhash/compare", json={"tokens": "x"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/hyperminhash/stats").json()) == {
        "p", "r", "num_buckets", "filled", "cardinality", "seed"}


def test_stats_default_config(client):
    s = client.get("/api/v1/hyperminhash/stats").json()
    assert s["p"] == 8 and s["r"] == 8 and s["num_buckets"] == 256


def test_stats_filled(loaded_client):
    assert loaded_client.get("/api/v1/hyperminhash/stats").json()["filled"] > 0


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/hyperminhash/reset", json={})
    assert resp.status_code == 200 and resp.json()["filled"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/hyperminhash/reset",
                          json={"p": 10, "r": 4, "seed": 9}).json()
    assert body["p"] == 10 and body["r"] == 4 and body["num_buckets"] == 1024 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/hyperminhash/reset", json={"p": 2})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/hyperminhash/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────

def test_add_then_cardinality(client):
    for i in range(500):
        client.post("/api/v1/hyperminhash/add", json={"element": f"k{i}"})
    est = client.get("/api/v1/hyperminhash/cardinality").json()["cardinality"]
    assert abs(est - 500) / 500 < 0.12       # p=8 default → looser bound


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
