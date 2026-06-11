"""Phase 103 — tests for the /api/v1/spectralbloom endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.spectral_bloom import SpectralBloom
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SpectralBloom in the factory.
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    sb = SpectralBloom(capacity=10000, error_rate=0.01, seed=0)
    for i in range(1000):
        sb.add(f"member-{i}")
    return TestClient(create_app(spectral_bloom=sb))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_estimate(client):
    resp = client.post("/api/v1/spectralbloom/add", json={"item": "x"})
    assert resp.status_code == 200
    assert resp.json()["item"] == "x" and resp.json()["estimate"] == 1


def test_add_with_count(client):
    assert client.post("/api/v1/spectralbloom/add", json={"item": "x", "count": 5}).json()["estimate"] == 5


def test_add_accumulates(client):
    client.post("/api/v1/spectralbloom/add", json={"item": "x", "count": 3})
    assert client.post("/api/v1/spectralbloom/add", json={"item": "x", "count": 4}).json()["estimate"] == 7


def test_add_missing_item_returns_422(client):
    assert client.post("/api/v1/spectralbloom/add", json={}).status_code == 422


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/spectralbloom/add", json=["x"]).status_code == 422


def test_add_bad_count_returns_422(client):
    assert client.post("/api/v1/spectralbloom/add", json={"item": "x", "count": 0}).status_code == 422


# ── query ─────────────────────────────────────────────────────────────────────────

def test_query_member(client):
    client.post("/api/v1/spectralbloom/add", json={"item": "k", "count": 4})
    body = client.get("/api/v1/spectralbloom/query", params={"item": "k"}).json()
    assert body["item"] == "k" and body["count"] == 4


def test_query_absent_is_zero(client):
    assert client.get("/api/v1/spectralbloom/query", params={"item": "ghost"}).json()["count"] == 0


def test_query_missing_param_returns_422(client):
    assert client.get("/api/v1/spectralbloom/query").status_code == 422


def test_no_false_negatives_over_http(loaded_client):
    assert all(
        loaded_client.get("/api/v1/spectralbloom/query", params={"item": f"member-{i}"}).json()["count"] >= 1
        for i in range(0, 1000, 50)
    )


# ── remove (DELETE with body) ──────────────────────────────────────────────────────

def test_remove_decrements(client):
    client.post("/api/v1/spectralbloom/add", json={"item": "e", "count": 3})
    resp = client.request("DELETE", "/api/v1/spectralbloom/remove", json={"item": "e"})
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1 and resp.json()["estimate"] == 2


def test_remove_to_zero(client):
    client.post("/api/v1/spectralbloom/add", json={"item": "e", "count": 2})
    client.request("DELETE", "/api/v1/spectralbloom/remove", json={"item": "e", "count": 2})
    assert client.get("/api/v1/spectralbloom/query", params={"item": "e"}).json()["count"] == 0


def test_remove_non_member_returns_zero(client):
    resp = client.request("DELETE", "/api/v1/spectralbloom/remove", json={"item": "ghost"})
    assert resp.json()["removed"] == 0


def test_remove_missing_item_returns_422(client):
    assert client.request("DELETE", "/api/v1/spectralbloom/remove", json={}).status_code == 422


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/spectralbloom/stats").json()) == {
        "capacity", "error_rate", "num_bits", "num_hashes", "num_added", "estimated_fill_ratio"}


def test_stats_defaults(client):
    s = client.get("/api/v1/spectralbloom/stats").json()
    assert s["capacity"] == 10000 and s["error_rate"] == 0.01 and s["num_hashes"] >= 1


def test_stats_after_adds(client):
    client.post("/api/v1/spectralbloom/add", json={"item": "a", "count": 12})
    assert client.get("/api/v1/spectralbloom/stats").json()["num_added"] == 12


# ── reset ─────────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/spectralbloom/add", json={"item": "a", "count": 50})
    resp = client.post("/api/v1/spectralbloom/reset", json={})
    assert resp.status_code == 200 and resp.json()["num_added"] == 0


def test_reset_reconfigures(client):
    before = client.get("/api/v1/spectralbloom/stats").json()["num_bits"]
    resp = client.post("/api/v1/spectralbloom/reset", json={"capacity": 1000})
    assert resp.json()["capacity"] == 1000 and resp.json()["num_bits"] < before


def test_reset_bad_config_returns_422(client):
    assert client.post("/api/v1/spectralbloom/reset", json={"error_rate": 1.0}).status_code == 422


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch", "lossycount",
                  "ddsketch", "window", "sample", "misragries", "xorfilter", "ribbon", "heavykeeper"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
