"""Phase 115 — tests for the /api/v1/minhashlsh endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.minhash_lsh import MinHashLSH
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    lsh = MinHashLSH(bands=16, rows=4, seed=1)
    lsh.insert("doc", list(range(200)))
    lsh.insert("other", list(range(5000, 5200)))      # disjoint
    return TestClient(create_app(minhash_lsh=lsh))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_returns_num_items(client):
    resp = client.post("/api/v1/minhashlsh/insert", json={"id": "a", "tokens": [1, 2, 3]})
    assert resp.status_code == 200
    assert resp.json()["id"] == "a" and resp.json()["num_items"] == 1


def test_insert_missing_id_422(client):
    assert client.post("/api/v1/minhashlsh/insert", json={"tokens": [1, 2]}).status_code == 422


def test_insert_tokens_not_list_422(client):
    assert client.post("/api/v1/minhashlsh/insert",
                       json={"id": "a", "tokens": "nope"}).status_code == 422


def test_insert_non_dict_422(client):
    assert client.post("/api/v1/minhashlsh/insert", json=["x"]).status_code == 422


# ── query ──────────────────────────────────────────────────────────────────────────

def test_query_finds_near_duplicate(loaded_client):
    resp = loaded_client.post("/api/v1/minhashlsh/query", json={"tokens": list(range(20, 220))})
    body = resp.json()
    ids = [c["id"] for c in body["candidates"]]
    assert "doc" in ids


def test_query_excludes_disjoint(loaded_client):
    resp = loaded_client.post("/api/v1/minhashlsh/query", json={"tokens": list(range(99000, 99200))})
    assert all(c["id"] != "doc" and c["id"] != "other" for c in resp.json()["candidates"])


def test_query_threshold_filters(loaded_client):
    near = list(range(40, 240))                       # Jaccard ~0.667 with doc
    lo = loaded_client.post("/api/v1/minhashlsh/query",
                            json={"tokens": near, "threshold": 0.4}).json()
    hi = loaded_client.post("/api/v1/minhashlsh/query",
                            json={"tokens": near, "threshold": 0.9}).json()
    assert any(c["id"] == "doc" for c in lo["candidates"])
    assert not any(c["id"] == "doc" for c in hi["candidates"])


def test_query_tokens_not_list_422(client):
    assert client.post("/api/v1/minhashlsh/query", json={"tokens": "x"}).status_code == 422


def test_query_bad_threshold_422(client):
    client.post("/api/v1/minhashlsh/insert", json={"id": "a", "tokens": [1, 2]})
    resp = client.post("/api/v1/minhashlsh/query", json={"tokens": [1, 2], "threshold": 1.5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_query_empty_index(client):
    resp = client.post("/api/v1/minhashlsh/query", json={"tokens": [1, 2, 3]})
    assert resp.json()["count"] == 0


def test_query_candidates_have_similarity(loaded_client):
    resp = loaded_client.post("/api/v1/minhashlsh/query", json={"tokens": list(range(200))})
    cands = resp.json()["candidates"]
    assert cands and all("id" in c and "similarity" in c for c in cands)
    sims = [c["similarity"] for c in cands]
    assert sims == sorted(sims, reverse=True)


# ── remove ───────────────────────────────────────────────────────────────────────

def test_remove_present(loaded_client):
    body = loaded_client.request("DELETE", "/api/v1/minhashlsh/remove", json={"id": "doc"}).json()
    assert body["removed"] is True and body["num_items"] == 1


def test_remove_absent(client):
    body = client.request("DELETE", "/api/v1/minhashlsh/remove", json={"id": "ghost"}).json()
    assert body["removed"] is False


def test_remove_missing_id_422(client):
    assert client.request("DELETE", "/api/v1/minhashlsh/remove", json={}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/minhashlsh/stats").json()) == {
        "num_items", "bands", "rows", "num_perm", "threshold_estimate", "seed"}


def test_stats_values(loaded_client):
    s = loaded_client.get("/api/v1/minhashlsh/stats").json()
    assert s["num_items"] == 2 and s["bands"] == 16 and s["rows"] == 4 and s["num_perm"] == 64


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/minhashlsh/reset", json={})
    assert resp.status_code == 200 and resp.json()["num_items"] == 0


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/minhashlsh/reset",
                          json={"bands": 8, "rows": 2, "seed": 5}).json()
    assert body["bands"] == 8 and body["rows"] == 2 and body["num_perm"] == 16 and body["seed"] == 5


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/minhashlsh/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────

def test_insert_query_roundtrip(client):
    for i in range(5):
        client.post("/api/v1/minhashlsh/insert",
                    json={"id": f"v{i}", "tokens": list(range(i, i + 200))})
    resp = client.post("/api/v1/minhashlsh/query", json={"tokens": list(range(200))})
    assert resp.json()["count"] >= 3


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
