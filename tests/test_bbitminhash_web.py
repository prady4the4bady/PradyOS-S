"""Phase 122 — tests for the /api/v1/bbitminhash endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bbit_minhash import BBitMinHash
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    s = BBitMinHash(num_perm=512, b=4, seed=0)
    s.add_many(range(1000))
    return TestClient(create_app(bbit_minhash=s))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_count(client):
    resp = client.post("/api/v1/bbitminhash/add", json={"element": "a"})
    assert resp.status_code == 200 and resp.json()["count"] == 1


def test_add_accumulates(client):
    for i in range(5):
        client.post("/api/v1/bbitminhash/add", json={"element": f"k{i}"})
    assert client.get("/api/v1/bbitminhash/stats").json()["count"] == 5


def test_add_missing_element_422(client):
    assert client.post("/api/v1/bbitminhash/add", json={}).status_code == 422


def test_add_non_dict_422(client):
    assert client.post("/api/v1/bbitminhash/add", json=["x"]).status_code == 422


# ── compare ──────────────────────────────────────────────────────────────────────

def test_compare_self_jaccard_one(loaded_client):
    body = loaded_client.post("/api/v1/bbitminhash/compare",
                              json={"tokens": list(range(1000))}).json()
    assert abs(body["jaccard"] - 1.0) < 1e-9


def test_compare_partial_overlap(loaded_client):
    # true Jaccard(0..1000, 500..1500) = 500/1500 = 0.333
    body = loaded_client.post("/api/v1/bbitminhash/compare",
                              json={"tokens": list(range(500, 1500))}).json()
    assert abs(body["jaccard"] - 0.3333) < 0.1


def test_compare_disjoint(loaded_client):
    body = loaded_client.post("/api/v1/bbitminhash/compare",
                              json={"tokens": list(range(50000, 51000))}).json()
    assert body["jaccard"] < 0.05


def test_compare_tokens_not_list_422(client):
    assert client.post("/api/v1/bbitminhash/compare", json={"tokens": "x"}).status_code == 422


# ── signature ────────────────────────────────────────────────────────────────────

def test_signature_shape(client):
    body = client.get("/api/v1/bbitminhash/signature").json()
    assert len(body["signature"]) == 128 and body["signature_bits"] == 256   # defaults k=128,b=2


def test_signature_values_in_range(loaded_client):
    sig = loaded_client.get("/api/v1/bbitminhash/signature").json()["signature"]
    assert all(0 <= v < 16 for v in sig)             # b=4 ⇒ values < 16


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/bbitminhash/stats").json()) == {
        "num_perm", "b", "count", "signature_bits", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/bbitminhash/stats").json()
    assert s["num_perm"] == 128 and s["b"] == 2


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/bbitminhash/reset", json={})
    assert resp.status_code == 200 and resp.json()["count"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/bbitminhash/reset",
                          json={"num_perm": 256, "b": 4, "seed": 9}).json()
    assert body["num_perm"] == 256 and body["b"] == 4 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/bbitminhash/reset", json={"b": 99})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/bbitminhash/reset").status_code == 200


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash", "scalablebloom",
                  "rendezvous", "maglev", "iblt"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
