"""Phase 96 — tests for the /api/v1/ddsketch endpoints in sovereign_web."""
from __future__ import annotations

import math
import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.ddsketch import DDSketch
from pradyos.sovereign_web import create_app


def uniform(n, lo=1.0, hi=1000.0, seed=0):
    rnd = random.Random(seed)
    return [rnd.uniform(lo, hi) for _ in range(n)]


def true_quantile(sorted_data, q):
    idx = min(len(sorted_data) - 1, max(0, math.ceil(q * len(sorted_data)) - 1))
    return sorted_data[idx]


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app DDSketch (alpha=0.01) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def data_client():
    # A pre-built sketch (uniform [1,1000]) injected for accuracy/merge assertions.
    data = uniform(10_000, seed=1)
    s = DDSketch(alpha=0.01)
    for v in data[:5000]:
        s.update(v)
    return TestClient(create_app(ddsketch=s)), data


# ── update ──────────────────────────────────────────────────────────────────────

def test_update_single_value(client):
    resp = client.post("/api/v1/ddsketch/update", params={"value": 100})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1 and resp.json()["n"] == 1


def test_update_with_count(client):
    resp = client.post("/api/v1/ddsketch/update", params={"value": 100, "count": 50})
    assert resp.status_code == 200
    assert resp.json()["n"] == 50


def test_update_values_list(client):
    resp = client.post("/api/v1/ddsketch/update", json={"values": [1, 2, 3, 4, 5]})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 5 and resp.json()["n"] == 5


def test_update_non_positive_value_returns_422(client):
    assert client.post("/api/v1/ddsketch/update", params={"value": -1}).status_code == 422


def test_update_zero_value_returns_422(client):
    assert client.post("/api/v1/ddsketch/update", params={"value": 0}).status_code == 422


def test_update_missing_returns_422(client):
    assert client.post("/api/v1/ddsketch/update").status_code == 422


def test_update_non_list_values_returns_422(client):
    assert client.post("/api/v1/ddsketch/update", json={"values": "nope"}).status_code == 422


def test_update_negative_in_values_returns_422(client):
    assert client.post("/api/v1/ddsketch/update", json={"values": [1, -2, 3]}).status_code == 422


# ── quantile ────────────────────────────────────────────────────────────────────

def test_quantile_accuracy(data_client):
    c, data = data_client
    sd = sorted(data[:5000])
    est = c.get("/api/v1/ddsketch/quantile", params={"q": 0.5}).json()["quantile"]
    tru = true_quantile(sd, 0.5)
    assert abs(est - tru) / tru <= 0.01


def test_quantile_empty_returns_422(client):
    resp = client.get("/api/v1/ddsketch/quantile", params={"q": 0.5})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_quantile_q_below_zero_returns_422(client):
    client.post("/api/v1/ddsketch/update", params={"value": 1})
    assert client.get("/api/v1/ddsketch/quantile", params={"q": -0.1}).status_code == 422


def test_quantile_q_above_one_returns_422(client):
    client.post("/api/v1/ddsketch/update", params={"value": 1})
    assert client.get("/api/v1/ddsketch/quantile", params={"q": 1.5}).status_code == 422


def test_quantile_missing_q_returns_422(client):
    assert client.get("/api/v1/ddsketch/quantile").status_code == 422


# ── merge (exact composability) ──────────────────────────────────────────────────

def test_merge_endpoint(data_client):
    c, data = data_client
    resp = c.post("/api/v1/ddsketch/merge", json={"values": data[5000:]})
    assert resp.status_code == 200
    assert resp.json()["n"] == 10_000
    sd = sorted(data)
    est = c.get("/api/v1/ddsketch/quantile", params={"q": 0.5}).json()["quantile"]
    assert abs(est - true_quantile(sd, 0.5)) / true_quantile(sd, 0.5) <= 0.01


def test_merge_missing_values_returns_422(client):
    assert client.post("/api/v1/ddsketch/merge", json={}).status_code == 422


def test_merge_non_list_values_returns_422(client):
    assert client.post("/api/v1/ddsketch/merge", json={"values": "nope"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/ddsketch/stats").json()
    assert set(data) == {"alpha", "gamma", "n", "num_buckets", "min", "max"}


def test_stats_tracks(client):
    client.post("/api/v1/ddsketch/update", params={"value": 7})
    client.post("/api/v1/ddsketch/update", params={"value": 700})
    data = client.get("/api/v1/ddsketch/stats").json()
    assert data["n"] == 2 and data["min"] == 7.0 and data["max"] == 700.0


def test_stats_default_alpha(client):
    assert client.get("/api/v1/ddsketch/stats").json()["alpha"] == 0.01


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/ddsketch/update", params={"value": 100, "count": 1000})
    resp = client.post("/api/v1/ddsketch/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["n"] == 0 and resp.json()["num_buckets"] == 0


def test_reset_reconfigures_alpha(client):
    resp = client.post("/api/v1/ddsketch/reset", json={"alpha": 0.05})
    assert resp.json()["alpha"] == 0.05


def test_reset_bad_alpha_returns_422(client):
    assert client.post("/api/v1/ddsketch/reset", json={"alpha": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_update_quantile_reset_round_trip(client):
    for v in (10, 20, 30, 40, 50):
        client.post("/api/v1/ddsketch/update", params={"value": v})
    assert client.get("/api/v1/ddsketch/quantile", params={"q": 0.5}).json()["quantile"] > 0
    client.post("/api/v1/ddsketch/reset", json={})
    assert client.get("/api/v1/ddsketch/stats").json()["n"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–95 routes still respond
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
