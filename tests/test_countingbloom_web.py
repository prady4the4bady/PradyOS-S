"""Phase 107 — tests for the /api/v1/countingbloom endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.counting_bloom import CountingBloom
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    cb = CountingBloom(capacity=1000, error_rate=0.01, seed=0)
    for i in range(1000):
        cb.add(f"member-{i}")
    return TestClient(create_app(counting_bloom=cb))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_count(client):
    resp = client.post("/api/v1/countingbloom/add", json={"element": "apple"})
    assert resp.status_code == 200
    assert resp.json()["element"] == "apple" and resp.json()["count"] == 1


def test_add_accumulates(client):
    client.post("/api/v1/countingbloom/add", json={"element": "a"})
    assert client.post("/api/v1/countingbloom/add", json={"element": "b"}).json()["count"] == 2


def test_add_missing_element_returns_422(client):
    assert client.post("/api/v1/countingbloom/add", json={}).status_code == 422


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/countingbloom/add", json=["a"]).status_code == 422


# ── contains ───────────────────────────────────────────────────────────────────────

def test_contains_after_add(client):
    client.post("/api/v1/countingbloom/add", json={"element": "x"})
    body = client.get("/api/v1/countingbloom/contains", params={"element": "x"}).json()
    assert body["element"] == "x" and body["contains"] is True


def test_contains_absent_is_false(client):
    client.post("/api/v1/countingbloom/add", json={"element": "x"})
    assert client.get("/api/v1/countingbloom/contains", params={"element": "ghost"}).json()["contains"] is False


def test_contains_missing_param_returns_422(client):
    assert client.get("/api/v1/countingbloom/contains").status_code == 422


def test_no_false_negatives(loaded_client):
    assert all(
        loaded_client.get("/api/v1/countingbloom/contains", params={"element": f"member-{i}"}).json()["contains"]
        for i in range(0, 1000, 50))


# ── remove ───────────────────────────────────────────────────────────────────────────

def test_remove_deletes(client):
    client.post("/api/v1/countingbloom/add", json={"element": "apple"})
    resp = client.post("/api/v1/countingbloom/remove", json={"element": "apple"})
    assert resp.status_code == 200
    assert client.get("/api/v1/countingbloom/contains", params={"element": "apple"}).json()["contains"] is False


def test_remove_absent_returns_400(client):
    resp = client.post("/api/v1/countingbloom/remove", json={"element": "ghost"})
    assert resp.status_code == 400 and "not in filter" in resp.json()["error"]


def test_remove_missing_element_returns_422(client):
    assert client.post("/api/v1/countingbloom/remove", json={}).status_code == 422


def test_double_add_single_remove_still_present(client):
    client.post("/api/v1/countingbloom/add", json={"element": "dup"})
    client.post("/api/v1/countingbloom/add", json={"element": "dup"})
    client.post("/api/v1/countingbloom/remove", json={"element": "dup"})
    assert client.get("/api/v1/countingbloom/contains", params={"element": "dup"}).json()["contains"] is True


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/countingbloom/stats").json()) == {
        "capacity", "error_rate", "num_hash_functions", "num_counters",
        "count", "false_positive_rate"}


def test_stats_defaults(client):
    s = client.get("/api/v1/countingbloom/stats").json()
    assert s["capacity"] == 10000 and s["error_rate"] == 0.01 and s["count"] == 0


def test_stats_after_adds(client):
    client.post("/api/v1/countingbloom/add", json={"element": "a"})
    assert client.get("/api/v1/countingbloom/stats").json()["count"] == 1


# ── reset (DELETE with body) ────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/countingbloom/add", json={"element": "a"})
    resp = client.request("DELETE", "/api/v1/countingbloom/reset", json={})
    assert resp.status_code == 200 and resp.json()["count"] == 0


def test_reset_reconfigures(client):
    resp = client.request("DELETE", "/api/v1/countingbloom/reset",
                          json={"capacity": 2000, "error_rate": 0.05, "seed": 3})
    assert resp.json()["capacity"] == 2000 and resp.json()["error_rate"] == 0.05


def test_reset_bad_config_returns_422(client):
    resp = client.request("DELETE", "/api/v1/countingbloom/reset", json={"error_rate": 0.0})
    assert resp.status_code == 422


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/countingbloom/reset").status_code == 200


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
