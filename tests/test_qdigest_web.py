"""Phase 105 — tests for the /api/v1/qdigest endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.q_digest import QDigest
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    qd = QDigest(compression_factor=100, value_range=1024, seed=0)
    rnd = random.Random(42)
    for _ in range(10000):
        qd.add(rnd.randrange(0, 1000))
    return TestClient(create_app(qdigest=qd))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_total(client):
    resp = client.post("/api/v1/qdigest/add", json={"value": 10})
    assert resp.status_code == 200
    assert resp.json()["value"] == 10 and resp.json()["total"] == 1


def test_add_with_count(client):
    assert client.post("/api/v1/qdigest/add", json={"value": 5, "count": 40}).json()["total"] == 40


def test_add_accumulates(client):
    client.post("/api/v1/qdigest/add", json={"value": 5, "count": 3})
    assert client.post("/api/v1/qdigest/add", json={"value": 7, "count": 4}).json()["total"] == 7


def test_add_missing_value_returns_422(client):
    assert client.post("/api/v1/qdigest/add", json={}).status_code == 422


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/qdigest/add", json=[1, 2]).status_code == 422


def test_add_out_of_range_returns_422(client):
    assert client.post("/api/v1/qdigest/add", json={"value": 999999}).status_code == 422


def test_add_bad_count_returns_422(client):
    assert client.post("/api/v1/qdigest/add", json={"value": 1, "count": 0}).status_code == 422


# ── quantile ───────────────────────────────────────────────────────────────────────

def test_quantile_uniform_p50(loaded_client):
    body = loaded_client.get("/api/v1/qdigest/quantile", params={"q": 0.5}).json()
    assert 475 <= body["value"] <= 525


def test_quantile_tail_p99(loaded_client):
    v = loaded_client.get("/api/v1/qdigest/quantile", params={"q": 0.99}).json()["value"]
    assert 990 * 0.95 <= v <= 990 * 1.05


def test_quantile_empty_returns_422(client):
    assert client.get("/api/v1/qdigest/quantile", params={"q": 0.5}).status_code == 422


def test_quantile_q_zero_returns_422(client):
    assert client.get("/api/v1/qdigest/quantile", params={"q": 0.0}).status_code == 422


def test_quantile_q_one_returns_422(client):
    assert client.get("/api/v1/qdigest/quantile", params={"q": 1.0}).status_code == 422


def test_quantile_monotonic(loaded_client):
    vals = [loaded_client.get("/api/v1/qdigest/quantile", params={"q": q}).json()["value"]
            for q in (0.25, 0.5, 0.75, 0.99)]
    assert vals == sorted(vals)


# ── merge ──────────────────────────────────────────────────────────────────────────

def test_merge_combines(client):
    client.post("/api/v1/qdigest/add", json={"value": 100, "count": 30})
    resp = client.post("/api/v1/qdigest/merge", json={"values": [200] * 70})
    assert resp.status_code == 200 and resp.json()["total_count"] == 100


def test_merge_missing_values_returns_422(client):
    assert client.post("/api/v1/qdigest/merge", json={}).status_code == 422


def test_merge_bad_value_returns_422(client):
    assert client.post("/api/v1/qdigest/merge", json={"values": [999999]}).status_code == 422


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/qdigest/stats").json()) == {
        "compression_factor", "value_range", "total_count", "num_nodes",
        "theoretical_max_nodes"}


def test_stats_defaults(client):
    s = client.get("/api/v1/qdigest/stats").json()
    assert s["compression_factor"] == 100 and s["value_range"] == 65536


def test_stats_after_adds(client):
    client.post("/api/v1/qdigest/add", json={"value": 3, "count": 12})
    assert client.get("/api/v1/qdigest/stats").json()["total_count"] == 12


# ── reset ─────────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/qdigest/add", json={"value": 5, "count": 50})
    resp = client.post("/api/v1/qdigest/reset", json={})
    assert resp.status_code == 200 and resp.json()["total_count"] == 0


def test_reset_reconfigures(client):
    resp = client.post("/api/v1/qdigest/reset",
                       json={"compression_factor": 25, "value_range": 4096})
    assert resp.json()["compression_factor"] == 25 and resp.json()["value_range"] == 4096


def test_reset_bad_config_returns_422(client):
    assert client.post("/api/v1/qdigest/reset",
                       json={"compression_factor": 0}).status_code == 422


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom", "augmentedsketch"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
