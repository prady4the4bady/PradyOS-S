"""Phase 94 — tests for the /api/v1/countsketch endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.count_sketch import CountSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app CountSketch (depth 5, width 2048).
    return TestClient(create_app())


@pytest.fixture()
def client_zipf():
    # A pre-built Zipf sketch injected into the factory (avoids thousands of HTTP calls).
    cs = CountSketch(depth=5, width=2048, seed=0)
    rnd = random.Random(0)
    stream = ["HEAVY0"] * 3000 + ["HEAVY1"] * 1500 + ["HEAVY2"] * 1000
    stream += [f"light{rnd.randint(0, 800)}" for _ in range(4500)]
    rnd.shuffle(stream)
    for e in stream:
        cs.update(e)
    return TestClient(create_app(count_sketch=cs))


# ── update ──────────────────────────────────────────────────────────────────────

def test_update_single_element(client):
    resp = client.post("/api/v1/countsketch/update", json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1 and resp.json()["total_count"] == 1


def test_update_with_count_query(client):
    resp = client.post("/api/v1/countsketch/update", params={"count": 50}, json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 50


def test_update_elements_list(client):
    resp = client.post("/api/v1/countsketch/update", json={"elements": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3 and resp.json()["total_count"] == 3


def test_update_missing_returns_422(client):
    assert client.post("/api/v1/countsketch/update", json={}).status_code == 422


def test_update_non_dict_body_returns_422(client):
    assert client.post("/api/v1/countsketch/update", json=["a"]).status_code == 422


def test_update_non_list_elements_returns_422(client):
    assert client.post("/api/v1/countsketch/update", json={"elements": "nope"}).status_code == 422


def test_update_invalid_count_returns_422(client):
    resp = client.post("/api/v1/countsketch/update", params={"count": "abc"}, json={"element": "a"})
    assert resp.status_code == 422


# ── estimate ────────────────────────────────────────────────────────────────────

def test_estimate_returns_value(client):
    client.post("/api/v1/countsketch/update", params={"count": 100}, json={"element": "x"})
    body = client.get("/api/v1/countsketch/estimate", params={"element": "x"}).json()
    assert body["element"] == "x" and body["estimate"] == 100


def test_estimate_unbiased_single_element():
    cs = CountSketch(depth=5, width=2048, seed=1)
    for _ in range(10_000):
        cs.update("solo")
    c = TestClient(create_app(count_sketch=cs))
    assert c.get("/api/v1/countsketch/estimate", params={"element": "solo"}).json()["estimate"] == 10_000


def test_estimate_unseen_is_zero(client):
    assert client.get("/api/v1/countsketch/estimate", params={"element": "ghost"}).json()["estimate"] == 0


def test_estimate_missing_element_returns_422(client):
    assert client.get("/api/v1/countsketch/estimate").status_code == 422


def test_deletion_via_negative_count_over_http(client):
    client.post("/api/v1/countsketch/update", params={"count": 1000}, json={"element": "x"})
    client.post("/api/v1/countsketch/update", params={"count": -300}, json={"element": "x"})
    assert client.get("/api/v1/countsketch/estimate", params={"element": "x"}).json()["estimate"] == 700


# ── heavy hitters ────────────────────────────────────────────────────────────────

def test_heavy_hitters_identifies_top(client_zipf):
    body = client_zipf.get("/api/v1/countsketch/heavy_hitters", params={"threshold": 0.01}).json()
    elems = [h["element"] for h in body["heavy_hitters"]]
    assert elems[:3] == ["HEAVY0", "HEAVY1", "HEAVY2"]


def test_heavy_hitters_structure(client_zipf):
    hh = client_zipf.get("/api/v1/countsketch/heavy_hitters", params={"threshold": 0.05}).json()["heavy_hitters"]
    assert hh and set(hh[0]) == {"element", "estimate"}


def test_heavy_hitters_threshold_above_one_returns_422(client):
    assert client.get("/api/v1/countsketch/heavy_hitters", params={"threshold": 1.5}).status_code == 422


def test_heavy_hitters_negative_threshold_returns_422(client):
    assert client.get("/api/v1/countsketch/heavy_hitters", params={"threshold": -0.1}).status_code == 422


def test_heavy_hitters_missing_threshold_returns_422(client):
    assert client.get("/api/v1/countsketch/heavy_hitters").status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/countsketch/stats").json()
    assert set(data) == {"depth", "width", "total_count", "unique_elements", "table_cells"}


def test_stats_tracks(client):
    client.post("/api/v1/countsketch/update", params={"count": 5}, json={"element": "a"})
    client.post("/api/v1/countsketch/update", json={"element": "b"})
    data = client.get("/api/v1/countsketch/stats").json()
    assert data["total_count"] == 6 and data["unique_elements"] == 2


def test_stats_default_dimensions(client):
    data = client.get("/api/v1/countsketch/stats").json()
    assert data["depth"] == 5 and data["width"] == 2048 and data["table_cells"] == 10_240


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/countsketch/update", params={"count": 100}, json={"element": "a"})
    resp = client.post("/api/v1/countsketch/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 0 and resp.json()["unique_elements"] == 0


def test_reset_reconfigures(client):
    resp = client.post("/api/v1/countsketch/reset", json={"depth": 3, "width": 512})
    assert resp.json()["depth"] == 3 and resp.json()["width"] == 512


def test_reset_bad_config_returns_422(client):
    assert client.post("/api/v1/countsketch/reset", json={"width": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_update_estimate_reset_round_trip(client):
    client.post("/api/v1/countsketch/update", params={"count": 500}, json={"element": "r"})
    assert client.get("/api/v1/countsketch/estimate", params={"element": "r"}).json()["estimate"] == 500
    client.post("/api/v1/countsketch/reset", json={})
    assert client.get("/api/v1/countsketch/estimate", params={"element": "r"}).json()["estimate"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–93 routes still respond
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
