"""Phase 95 — tests for the /api/v1/lossycount endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.lossy_count import LossyCount
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app LossyCount (epsilon=0.001) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_zipf():
    # A pre-built Zipf counter injected into the factory (avoids tens of thousands of calls).
    lc = LossyCount(epsilon=0.001)
    stream = []
    for i in range(1, 101):
        stream += [f"z{i}"] * (10000 // i)
    random.Random(1).shuffle(stream)
    for e in stream:
        lc.update(e)
    return TestClient(create_app(lossy=lc)), len(stream)


# ── update ──────────────────────────────────────────────────────────────────────

def test_update_single_element(client):
    resp = client.post("/api/v1/lossycount/update", json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1 and resp.json()["n"] == 1


def test_update_with_count_query(client):
    resp = client.post("/api/v1/lossycount/update", params={"count": 50}, json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["n"] == 50


def test_update_elements_list(client):
    resp = client.post("/api/v1/lossycount/update", json={"elements": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3 and resp.json()["n"] == 3


def test_update_missing_returns_422(client):
    assert client.post("/api/v1/lossycount/update", json={}).status_code == 422


def test_update_non_dict_body_returns_422(client):
    assert client.post("/api/v1/lossycount/update", json=["a"]).status_code == 422


def test_update_non_list_elements_returns_422(client):
    assert client.post("/api/v1/lossycount/update", json={"elements": "nope"}).status_code == 422


def test_update_negative_count_rejected_no_deletion(client):
    resp = client.post("/api/v1/lossycount/update", params={"count": -1}, json={"element": "x"})
    assert resp.status_code == 422
    assert "deletion" in resp.json()["error"]


# ── estimate ────────────────────────────────────────────────────────────────────

def test_estimate_returns_value(client):
    client.post("/api/v1/lossycount/update", params={"count": 100}, json={"element": "x"})
    body = client.get("/api/v1/lossycount/estimate", params={"element": "x"}).json()
    assert body["element"] == "x" and body["estimate"] == 100


def test_estimate_unseen_is_zero(client):
    assert client.get("/api/v1/lossycount/estimate", params={"element": "ghost"}).json()["estimate"] == 0


def test_estimate_missing_element_returns_422(client):
    assert client.get("/api/v1/lossycount/estimate").status_code == 422


# ── heavy hitters ────────────────────────────────────────────────────────────────

def test_heavy_hitters_zipf_ranked(client_zipf):
    c, _n = client_zipf
    hh = c.get("/api/v1/lossycount/heavy_hitters", params={"support": 0.05}).json()["heavy_hitters"]
    assert [h["element"] for h in hh[:3]] == ["z1", "z2", "z3"]


def test_heavy_hitters_no_false_negatives(client_zipf):
    c, n = client_zipf
    got = {h["element"] for h in
           c.get("/api/v1/lossycount/heavy_hitters", params={"support": 0.05}).json()["heavy_hitters"]}
    truth = {f"z{i}": 10000 // i for i in range(1, 101)}
    must = {e for e, f in truth.items() if f >= 0.05 * n}
    assert must.issubset(got)


def test_heavy_hitters_structure(client_zipf):
    c, _n = client_zipf
    hh = c.get("/api/v1/lossycount/heavy_hitters", params={"support": 0.05}).json()["heavy_hitters"]
    assert hh and set(hh[0]) == {"element", "frequency"}


def test_heavy_hitters_support_zero_returns_422(client):
    assert client.get("/api/v1/lossycount/heavy_hitters", params={"support": 0}).status_code == 422


def test_heavy_hitters_support_above_one_returns_422(client):
    assert client.get("/api/v1/lossycount/heavy_hitters", params={"support": 1.5}).status_code == 422


def test_heavy_hitters_missing_support_returns_422(client):
    assert client.get("/api/v1/lossycount/heavy_hitters").status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/lossycount/stats").json()
    assert set(data) == {"epsilon", "n", "bucket_width", "entries", "current_bucket"}


def test_stats_tracks(client):
    client.post("/api/v1/lossycount/update", params={"count": 2500}, json={"element": "a"})
    data = client.get("/api/v1/lossycount/stats").json()
    assert data["n"] == 2500 and data["bucket_width"] == 1000


def test_stats_default_epsilon(client):
    assert client.get("/api/v1/lossycount/stats").json()["epsilon"] == 0.001


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/lossycount/update", params={"count": 1000}, json={"element": "a"})
    resp = client.post("/api/v1/lossycount/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["n"] == 0 and resp.json()["entries"] == 0


def test_reset_reconfigures_epsilon(client):
    resp = client.post("/api/v1/lossycount/reset", json={"epsilon": 0.01})
    assert resp.json()["epsilon"] == 0.01 and resp.json()["bucket_width"] == 100


def test_reset_bad_epsilon_returns_422(client):
    assert client.post("/api/v1/lossycount/reset", json={"epsilon": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_update_estimate_reset_round_trip(client):
    client.post("/api/v1/lossycount/update", params={"count": 500}, json={"element": "r"})
    assert client.get("/api/v1/lossycount/estimate", params={"element": "r"}).json()["estimate"] == 500
    client.post("/api/v1/lossycount/reset", json={})
    assert client.get("/api/v1/lossycount/estimate", params={"element": "r"}).json()["estimate"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–94 routes still respond
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
