"""Phase 126 — tests for the /api/v1/simhashlsh endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.simhash_lsh import SimHashLSH
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def lsh_client():
    # Small dimension for compact test vectors; k = 8*4 = 32 hyperplanes.
    sl = SimHashLSH(dim=8, bands=8, rows=4, seed=0)
    return TestClient(create_app(simhash_lsh=sl))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_returns_num_items(lsh_client):
    resp = lsh_client.post("/api/v1/simhashlsh/insert",
                           json={"id": "a", "vector": [1, 0, 0, 0, 0, 0, 0, 0]})
    assert resp.status_code == 200 and resp.json()["num_items"] == 1


def test_insert_missing_id_422(lsh_client):
    assert lsh_client.post("/api/v1/simhashlsh/insert",
                           json={"vector": [1, 0, 0, 0, 0, 0, 0, 0]}).status_code == 422


def test_insert_vector_not_list_422(lsh_client):
    assert lsh_client.post("/api/v1/simhashlsh/insert",
                           json={"id": "a", "vector": "nope"}).status_code == 422


def test_insert_wrong_dim_422(lsh_client):
    resp = lsh_client.post("/api/v1/simhashlsh/insert", json={"id": "a", "vector": [1, 2, 3]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── query ──────────────────────────────────────────────────────────────────────────

def test_query_finds_near_parallel(lsh_client):
    lsh_client.post("/api/v1/simhashlsh/insert", json={"id": "base", "vector": [1, 1, 0, 0, 0, 0, 0, 0]})
    resp = lsh_client.post("/api/v1/simhashlsh/query", json={"vector": [1, 0.9, 0, 0, 0, 0, 0, 0]})
    assert any(c["id"] == "base" for c in resp.json()["candidates"])


def test_query_candidates_have_similarity(lsh_client):
    lsh_client.post("/api/v1/simhashlsh/insert", json={"id": "base", "vector": [1, 1, 1, 0, 0, 0, 0, 0]})
    resp = lsh_client.post("/api/v1/simhashlsh/query", json={"vector": [1, 1, 1, 0, 0, 0, 0, 0]})
    cands = resp.json()["candidates"]
    assert cands and all("id" in c and "similarity" in c for c in cands)
    sims = [c["similarity"] for c in cands]
    assert sims == sorted(sims, reverse=True)


def test_query_vector_not_list_422(lsh_client):
    assert lsh_client.post("/api/v1/simhashlsh/query", json={"vector": "x"}).status_code == 422


def test_query_bad_threshold_422(lsh_client):
    resp = lsh_client.post("/api/v1/simhashlsh/query",
                           json={"vector": [1, 0, 0, 0, 0, 0, 0, 0], "threshold": 2.0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_query_empty_index(lsh_client):
    resp = lsh_client.post("/api/v1/simhashlsh/query", json={"vector": [1, 0, 0, 0, 0, 0, 0, 0]})
    assert resp.json()["count"] == 0


# ── remove ───────────────────────────────────────────────────────────────────────

def test_remove_present(lsh_client):
    lsh_client.post("/api/v1/simhashlsh/insert", json={"id": "a", "vector": [1, 0, 0, 0, 0, 0, 0, 0]})
    body = lsh_client.request("DELETE", "/api/v1/simhashlsh/remove", json={"id": "a"}).json()
    assert body["removed"] is True and body["num_items"] == 0


def test_remove_absent(lsh_client):
    assert lsh_client.request("DELETE", "/api/v1/simhashlsh/remove",
                              json={"id": "ghost"}).json()["removed"] is False


def test_remove_missing_id_422(lsh_client):
    assert lsh_client.request("DELETE", "/api/v1/simhashlsh/remove", json={}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/simhashlsh/stats").json()) == {
        "num_items", "dim", "bands", "rows", "num_perm", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/simhashlsh/stats").json()
    assert s["dim"] == 64 and s["bands"] == 16 and s["rows"] == 4 and s["num_perm"] == 64


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(lsh_client):
    lsh_client.post("/api/v1/simhashlsh/insert", json={"id": "a", "vector": [1, 0, 0, 0, 0, 0, 0, 0]})
    resp = lsh_client.request("DELETE", "/api/v1/simhashlsh/reset", json={})
    assert resp.status_code == 200 and resp.json()["num_items"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/simhashlsh/reset",
                          json={"dim": 16, "bands": 8, "rows": 2, "seed": 9}).json()
    assert body["dim"] == 16 and body["bands"] == 8 and body["rows"] == 2 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/simhashlsh/reset", json={"dim": 0})
    assert resp.status_code == 422 and "error" in resp.json()


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
                  "rendezvous", "maglev", "iblt", "bbitminhash", "cusketch", "jump", "frugal"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
