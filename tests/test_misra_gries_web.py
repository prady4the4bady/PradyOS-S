"""Phase 99 — tests for the /api/v1/misragries endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.misra_gries import MisraGries
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app MisraGries (k=100) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def zipf_client():
    # A pre-built Zipf counter (k=20, so support 0.05 > 1/(k+1)) injected into the factory.
    truth = {f"e{i}": 10000 // i for i in range(1, 201)}
    stream = []
    for e, c in truth.items():
        stream += [e] * c
    random.Random(0).shuffle(stream)
    mg = MisraGries(k=20)
    for e in stream:
        mg.update(e)
    return TestClient(create_app(misra_gries=mg)), len(stream), truth


# ── update ──────────────────────────────────────────────────────────────────────

def test_update_single(client):
    resp = client.post("/api/v1/misragries/update", json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1 and resp.json()["n"] == 1


def test_update_with_count(client):
    resp = client.post("/api/v1/misragries/update", params={"count": 50}, json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["n"] == 50


def test_update_elements_list(client):
    resp = client.post("/api/v1/misragries/update", json={"elements": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3 and resp.json()["n"] == 3


def test_update_missing_returns_422(client):
    assert client.post("/api/v1/misragries/update", json={}).status_code == 422


def test_update_non_dict_body_returns_422(client):
    assert client.post("/api/v1/misragries/update", json=["a"]).status_code == 422


def test_update_non_list_elements_returns_422(client):
    assert client.post("/api/v1/misragries/update", json={"elements": "nope"}).status_code == 422


def test_update_count_zero_returns_422(client):
    assert client.post("/api/v1/misragries/update", params={"count": 0},
                       json={"element": "a"}).status_code == 422


def test_update_count_negative_returns_422(client):
    assert client.post("/api/v1/misragries/update", params={"count": -1},
                       json={"element": "a"}).status_code == 422


# ── estimate ────────────────────────────────────────────────────────────────────

def test_estimate_returns_value(client):
    client.post("/api/v1/misragries/update", params={"count": 100}, json={"element": "x"})
    body = client.get("/api/v1/misragries/estimate", params={"element": "x"}).json()
    assert body["element"] == "x" and body["estimate"] == 100


def test_estimate_unseen_is_zero(client):
    assert client.get("/api/v1/misragries/estimate", params={"element": "ghost"}).json()["estimate"] == 0


def test_estimate_missing_element_returns_422(client):
    assert client.get("/api/v1/misragries/estimate").status_code == 422


# ── heavy hitters ────────────────────────────────────────────────────────────────

def test_heavy_hitters_ranked(zipf_client):
    c, _n, _truth = zipf_client
    hh = c.get("/api/v1/misragries/heavy_hitters", params={"support": 0.05}).json()["heavy_hitters"]
    assert [h["element"] for h in hh[:3]] == ["e1", "e2", "e3"]


def test_heavy_hitters_no_false_negatives(zipf_client):
    c, n, truth = zipf_client
    got = {h["element"] for h in
           c.get("/api/v1/misragries/heavy_hitters", params={"support": 0.05}).json()["heavy_hitters"]}
    must = {e for e, f in truth.items() if f >= 0.05 * n}
    assert must.issubset(got)


def test_heavy_hitters_structure(zipf_client):
    c, _n, _truth = zipf_client
    hh = c.get("/api/v1/misragries/heavy_hitters", params={"support": 0.05}).json()["heavy_hitters"]
    assert hh and set(hh[0]) == {"element", "count"}


def test_heavy_hitters_support_zero_returns_422(client):
    assert client.get("/api/v1/misragries/heavy_hitters", params={"support": 0}).status_code == 422


def test_heavy_hitters_support_above_one_returns_422(client):
    assert client.get("/api/v1/misragries/heavy_hitters", params={"support": 1.5}).status_code == 422


def test_heavy_hitters_missing_support_returns_422(client):
    assert client.get("/api/v1/misragries/heavy_hitters").status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/misragries/stats").json()
    assert set(data) == {"k", "n", "counters", "threshold"}


def test_stats_tracks(client):
    client.post("/api/v1/misragries/update", params={"count": 90}, json={"element": "a"})
    data = client.get("/api/v1/misragries/stats").json()
    assert data["n"] == 90 and data["threshold"] == 90 / 101


def test_stats_default_k(client):
    assert client.get("/api/v1/misragries/stats").json()["k"] == 100


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/misragries/update", params={"count": 1000}, json={"element": "a"})
    resp = client.post("/api/v1/misragries/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["n"] == 0 and resp.json()["counters"] == 0


def test_reset_reconfigures_k(client):
    resp = client.post("/api/v1/misragries/reset", json={"k": 20})
    assert resp.json()["k"] == 20


def test_reset_bad_k_returns_422(client):
    assert client.post("/api/v1/misragries/reset", json={"k": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_update_estimate_reset_round_trip(client):
    client.post("/api/v1/misragries/update", params={"count": 500}, json={"element": "r"})
    assert client.get("/api/v1/misragries/estimate", params={"element": "r"}).json()["estimate"] == 500
    client.post("/api/v1/misragries/reset", json={})
    assert client.get("/api/v1/misragries/estimate", params={"element": "r"}).json()["estimate"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–98 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
    assert client.get("/api/v1/minhash/stats").status_code == 200
    assert client.get("/api/v1/simhash/stats").status_code == 200
    assert client.get("/api/v1/quotient/stats").status_code == 200
    assert client.get("/api/v1/quantile/stats").status_code == 200
    assert client.get("/api/v1/kll/stats").status_code == 200
    assert client.get("/api/v1/theta/stats").status_code == 200
    assert client.get("/api/v1/countsketch/stats").status_code == 200
    assert client.get("/api/v1/lossycount/stats").status_code == 200
    assert client.get("/api/v1/ddsketch/stats").status_code == 200
    assert client.get("/api/v1/window/stats").status_code == 200
    assert client.get("/api/v1/sample/stats").status_code == 200
