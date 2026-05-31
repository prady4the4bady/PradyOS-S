"""Phase 106 — tests for the /api/v1/momentsketch endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.moment_sketch import MomentSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    ms = MomentSketch(k=15, seed=0)
    rnd = random.Random(42)
    for _ in range(10000):
        ms.add(rnd.uniform(0, 1000))
    return TestClient(create_app(moment_sketch=ms))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_count(client):
    resp = client.post("/api/v1/momentsketch/add", json={"value": 10.0})
    assert resp.status_code == 200
    assert resp.json()["value"] == 10.0 and resp.json()["total_count"] == 1


def test_add_accumulates(client):
    client.post("/api/v1/momentsketch/add", json={"value": 5.0})
    assert client.post("/api/v1/momentsketch/add", json={"value": 7.0}).json()["total_count"] == 2


def test_add_accepts_int(client):
    assert client.post("/api/v1/momentsketch/add", json={"value": 3}).status_code == 200


def test_add_missing_value_returns_422(client):
    assert client.post("/api/v1/momentsketch/add", json={}).status_code == 422


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/momentsketch/add", json=[1, 2]).status_code == 422


def test_add_bad_value_returns_422(client):
    assert client.post("/api/v1/momentsketch/add", json={"value": "nope"}).status_code == 422


# ── quantile ───────────────────────────────────────────────────────────────────────

def test_quantile_uniform_p50(loaded_client):
    body = loaded_client.get("/api/v1/momentsketch/quantile", params={"q": 0.5}).json()
    assert 475 <= body["value"] <= 525


def test_quantile_tail_p99(loaded_client):
    v = loaded_client.get("/api/v1/momentsketch/quantile", params={"q": 0.99}).json()["value"]
    assert 990 * 0.95 <= v <= 990 * 1.05


def test_quantile_empty_returns_422(client):
    assert client.get("/api/v1/momentsketch/quantile", params={"q": 0.5}).status_code == 422


def test_quantile_q_zero_returns_422(client):
    assert client.get("/api/v1/momentsketch/quantile", params={"q": 0.0}).status_code == 422


def test_quantile_q_one_returns_422(client):
    assert client.get("/api/v1/momentsketch/quantile", params={"q": 1.0}).status_code == 422


def test_quantile_monotonic(loaded_client):
    vals = [loaded_client.get("/api/v1/momentsketch/quantile", params={"q": q}).json()["value"]
            for q in (0.25, 0.5, 0.75, 0.99)]
    assert vals == sorted(vals)


# ── merge ──────────────────────────────────────────────────────────────────────────

def test_merge_combines(client):
    src = MomentSketch(k=15)
    for v in range(100):
        src.add(float(v))
    resp = client.post("/api/v1/momentsketch/merge", json=src.stats())
    assert resp.status_code == 200 and resp.json()["total_count"] == 100


def test_merge_missing_moments_returns_422(client):
    assert client.post("/api/v1/momentsketch/merge", json={}).status_code == 422


def test_merge_then_quantile(client):
    src = MomentSketch(k=15)
    rnd = random.Random(3)
    for _ in range(5000):
        src.add(rnd.uniform(0, 1000))
    client.post("/api/v1/momentsketch/merge", json=src.stats())
    v = client.get("/api/v1/momentsketch/quantile", params={"q": 0.5}).json()["value"]
    assert 450 <= v <= 550


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/momentsketch/stats").json()) == {
        "k", "seed", "total_count", "min_val", "max_val", "moments"}


def test_stats_defaults(client):
    s = client.get("/api/v1/momentsketch/stats").json()
    assert s["k"] == 15 and s["total_count"] == 0


def test_stats_after_adds(client):
    client.post("/api/v1/momentsketch/add", json={"value": 12.0})
    s = client.get("/api/v1/momentsketch/stats").json()
    assert s["total_count"] == 1 and s["min_val"] == 12.0


# ── reset (DELETE with body) ────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/momentsketch/add", json={"value": 5.0})
    resp = client.request("DELETE", "/api/v1/momentsketch/reset", json={})
    assert resp.status_code == 200 and resp.json()["total_count"] == 0


def test_reset_reconfigures(client):
    resp = client.request("DELETE", "/api/v1/momentsketch/reset", json={"k": 8, "seed": 3})
    assert resp.json()["k"] == 8 and resp.json()["seed"] == 3


def test_reset_bad_config_returns_422(client):
    resp = client.request("DELETE", "/api/v1/momentsketch/reset", json={"k": 0})
    assert resp.status_code == 422


def test_reset_no_body(client):
    resp = client.request("DELETE", "/api/v1/momentsketch/reset")
    assert resp.status_code == 200


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
