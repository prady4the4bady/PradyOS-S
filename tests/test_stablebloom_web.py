"""Phase 110 — tests for the /api/v1/stablebloom endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.stable_bloom import StableBloomFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app StableBloomFilter in the factory.
    return TestClient(create_app())


@pytest.fixture()
def small_client():
    # A small, fast filter for streaming/forgetting behaviour over HTTP.
    sbf = StableBloomFilter(num_cells=2000, num_hashes=4, max_value=3, seed=11)
    return TestClient(create_app(stable_bloom=sbf))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_count(client):
    resp = client.post("/api/v1/stablebloom/add", json={"element": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["element"] == "a" and body["count"] == 1


def test_add_missing_element_returns_422(client):
    resp = client.post("/api/v1/stablebloom/add", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/stablebloom/add", json=["not", "dict"]).status_code == 422


# ── contains ────────────────────────────────────────────────────────────────────

def test_contains_after_add_true(client):
    client.post("/api/v1/stablebloom/add", json={"element": "hello"})
    resp = client.get("/api/v1/stablebloom/contains", params={"element": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["element"] == "hello" and body["contains"] is True


def test_contains_absent_false(client):
    assert client.get("/api/v1/stablebloom/contains",
                      params={"element": "never"}).json()["contains"] is False


def test_contains_missing_param_returns_422(client):
    assert client.get("/api/v1/stablebloom/contains").status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/stablebloom/stats").json()) == {
        "num_cells", "num_hashes", "max_value", "decrement", "count",
        "fill_ratio", "seed"}


def test_stats_tracks_count(client):
    for i in range(7):
        client.post("/api/v1/stablebloom/add", json={"element": f"k{i}"})
    assert client.get("/api/v1/stablebloom/stats").json()["count"] == 7


def test_stats_initial_fill_zero(client):
    assert client.get("/api/v1/stablebloom/stats").json()["fill_ratio"] == 0.0


def test_stats_default_config(client):
    s = client.get("/api/v1/stablebloom/stats").json()
    assert s["num_cells"] == 10000 and s["num_hashes"] == 5 and s["max_value"] == 3
    assert s["decrement"] == 15           # k * Max


# ── reset (DELETE with body) ──────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(50):
        client.post("/api/v1/stablebloom/add", json={"element": f"k{i}"})
    resp = client.request("DELETE", "/api/v1/stablebloom/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0 and resp.json()["fill_ratio"] == 0.0


def test_reset_reconfigures(client):
    resp = client.request("DELETE", "/api/v1/stablebloom/reset",
                          json={"num_cells": 2048, "num_hashes": 7, "max_value": 7, "seed": 3})
    body = resp.json()
    assert body["num_cells"] == 2048 and body["num_hashes"] == 7
    assert body["max_value"] == 7 and body["seed"] == 3


def test_reset_explicit_decrement(client):
    resp = client.request("DELETE", "/api/v1/stablebloom/reset",
                          json={"num_cells": 5000, "decrement": 33})
    assert resp.json()["decrement"] == 33


def test_reset_bad_config_returns_422(client):
    resp = client.request("DELETE", "/api/v1/stablebloom/reset", json={"num_cells": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/stablebloom/reset").status_code == 200


# ── streaming behaviour over HTTP ────────────────────────────────────────────────

def test_fresh_add_recalled_over_http(small_client):
    small_client.post("/api/v1/stablebloom/add", json={"element": "fresh"})
    assert small_client.get("/api/v1/stablebloom/contains",
                            params={"element": "fresh"}).json()["contains"] is True


def test_fill_does_not_saturate_over_http(small_client):
    for i in range(2500):       # > num_cells → past the transient, fill is stable
        small_client.post("/api/v1/stablebloom/add", json={"element": f"s-{i}"})
    assert small_client.get("/api/v1/stablebloom/stats").json()["fill_ratio"] < 0.95


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
