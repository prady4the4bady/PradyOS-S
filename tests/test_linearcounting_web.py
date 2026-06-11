"""Phase 112 — tests for the /api/v1/linearcounting endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.linear_counter import LinearCounter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app LinearCounter in the factory.
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    # 20 000 distinct items populated in-process (fast), then served over HTTP.
    lc = LinearCounter(num_bits=65536, seed=1)
    for i in range(20000):
        lc.add(f"item-{i}")
    return TestClient(create_app(linear_counter=lc))


@pytest.fixture()
def saturated_client():
    lc = LinearCounter(num_bits=256, seed=4)
    for i in range(20000):
        lc.add(f"s-{i}")
    return TestClient(create_app(linear_counter=lc))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_bits_set(client):
    resp = client.post("/api/v1/linearcounting/add", json={"element": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["element"] == "a" and body["bits_set"] == 1


def test_add_missing_element_returns_422(client):
    resp = client.post("/api/v1/linearcounting/add", json={})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/linearcounting/add", json=["nope"]).status_code == 422


def test_add_duplicate_idempotent(client):
    for _ in range(5):
        client.post("/api/v1/linearcounting/add", json={"element": "same"})
    assert client.get("/api/v1/linearcounting/stats").json()["bits_set"] == 1


# ── estimate ─────────────────────────────────────────────────────────────────────

def test_estimate_empty_is_zero(client):
    body = client.get("/api/v1/linearcounting/estimate").json()
    assert body["estimate"] == 0.0 and body["bits_set"] == 0


def test_estimate_accurate(loaded_client):
    est = loaded_client.get("/api/v1/linearcounting/estimate").json()["estimate"]
    assert abs(est - 20000) / 20000 < 0.03


def test_estimate_saturated_returns_400(saturated_client):
    resp = saturated_client.get("/api/v1/linearcounting/estimate")
    assert resp.status_code == 400 and "saturated" in resp.json()["error"]


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/linearcounting/stats").json()) == {
        "num_bits", "bits_set", "zero_bits", "load_factor", "estimate", "seed"}


def test_stats_default_num_bits(client):
    assert client.get("/api/v1/linearcounting/stats").json()["num_bits"] == 65536


def test_stats_estimate_null_when_saturated(saturated_client):
    assert saturated_client.get("/api/v1/linearcounting/stats").json()["estimate"] is None


def test_stats_reflects_adds(loaded_client):
    s = loaded_client.get("/api/v1/linearcounting/stats").json()
    assert s["bits_set"] > 0 and s["zero_bits"] == s["num_bits"] - s["bits_set"]
    assert s["estimate"] > 0


# ── reset (DELETE with body) ──────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/linearcounting/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["bits_set"] == 0 and resp.json()["estimate"] == 0.0


def test_reset_reconfigures(client):
    resp = client.request("DELETE", "/api/v1/linearcounting/reset",
                          json={"num_bits": 8192, "seed": 9})
    body = resp.json()
    assert body["num_bits"] == 8192 and body["seed"] == 9


def test_reset_bad_config_returns_422(client):
    resp = client.request("DELETE", "/api/v1/linearcounting/reset", json={"num_bits": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/linearcounting/reset").status_code == 200


# ── round-trip over HTTP ──────────────────────────────────────────────────────────

def test_add_then_estimate_small(client):
    for i in range(50):
        client.post("/api/v1/linearcounting/add", json={"element": f"k{i}"})
    body = client.get("/api/v1/linearcounting/estimate").json()
    assert body["bits_set"] == 50 and body["estimate"] > 0


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
