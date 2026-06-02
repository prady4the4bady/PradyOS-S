"""Phase 118 — tests for the /api/v1/scalablebloom endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.scalable_bloom import ScalableBloomFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def grown_client():
    # Pre-grown in-process (avoids thousands of HTTP adds), then served over HTTP.
    sb = ScalableBloomFilter(initial_capacity=500, error_rate=0.01, seed=0)
    for i in range(6000):
        sb.add(f"member-{i}")
    return TestClient(create_app(scalable_bloom=sb))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_count(client):
    resp = client.post("/api/v1/scalablebloom/add", json={"element": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] is True and body["count"] == 1


def test_add_duplicate_returns_false(client):
    client.post("/api/v1/scalablebloom/add", json={"element": "x"})
    body = client.post("/api/v1/scalablebloom/add", json={"element": "x"}).json()
    assert body["added"] is False and body["count"] == 1


def test_add_missing_element_422(client):
    assert client.post("/api/v1/scalablebloom/add", json={}).status_code == 422


def test_add_non_dict_422(client):
    assert client.post("/api/v1/scalablebloom/add", json=["x"]).status_code == 422


# ── contains ────────────────────────────────────────────────────────────────────

def test_contains_after_add(client):
    client.post("/api/v1/scalablebloom/add", json={"element": "hello"})
    assert client.get("/api/v1/scalablebloom/contains", params={"element": "hello"}).json()["contains"] is True


def test_contains_absent(client):
    assert client.get("/api/v1/scalablebloom/contains", params={"element": "ghost"}).json()["contains"] is False


def test_contains_missing_param_422(client):
    assert client.get("/api/v1/scalablebloom/contains").status_code == 422


def test_no_false_negatives_after_growth(grown_client):
    assert all(
        grown_client.get("/api/v1/scalablebloom/contains", params={"element": f"member-{i}"}).json()["contains"]
        for i in range(0, 6000, 50))


def test_fp_bounded_over_http(grown_client):
    fp = sum(
        1 for i in range(1500)
        if grown_client.get("/api/v1/scalablebloom/contains",
                            params={"element": f"absent-{i}"}).json()["contains"])
    assert fp / 1500 <= 0.02


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/scalablebloom/stats").json()) == {
        "count", "num_layers", "initial_capacity", "error_rate", "ratio",
        "growth", "total_bits", "false_positive_rate", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/scalablebloom/stats").json()
    assert s["initial_capacity"] == 1000 and s["error_rate"] == 0.01
    assert s["num_layers"] == 1 and s["ratio"] == 0.9 and s["growth"] == 2


def test_stats_grown(grown_client):
    s = grown_client.get("/api/v1/scalablebloom/stats").json()
    assert s["num_layers"] >= 3 and s["false_positive_rate"] <= 0.01


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(grown_client):
    resp = grown_client.request("DELETE", "/api/v1/scalablebloom/reset", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0 and body["num_layers"] == 1


def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/scalablebloom/reset",
                          json={"initial_capacity": 2000, "error_rate": 0.05,
                                "ratio": 0.8, "growth": 3, "seed": 9}).json()
    assert body["initial_capacity"] == 2000 and body["error_rate"] == 0.05
    assert body["ratio"] == 0.8 and body["growth"] == 3 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/scalablebloom/reset", json={"error_rate": 2.0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/scalablebloom/reset").status_code == 200


# ── round-trip / growth over HTTP ────────────────────────────────────────────────

def test_growth_over_http(client):
    # Small initial capacity so a modest number of HTTP adds triggers growth.
    client.request("DELETE", "/api/v1/scalablebloom/reset", json={"initial_capacity": 50})
    for i in range(300):
        client.post("/api/v1/scalablebloom/add", json={"element": f"k{i}"})
    assert client.get("/api/v1/scalablebloom/stats").json()["num_layers"] >= 2


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
