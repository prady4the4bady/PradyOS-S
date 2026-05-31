"""Phase 97 — tests for the /api/v1/window endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.exponential_histogram import ExponentialHistogram
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app ExponentialHistogram (window=1000) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def dense_client():
    # A pre-built dense histogram injected for count-accuracy assertions over HTTP.
    eh = ExponentialHistogram(window=500, epsilon=0.5)
    for _ in range(1000):
        eh.update()
    return TestClient(create_app(exp_histogram=eh))


# ── update ──────────────────────────────────────────────────────────────────────

def test_update_single(client):
    resp = client.post("/api/v1/window/update")
    assert resp.status_code == 200
    body = resp.json()
    assert body["now"] == 0 and body["num_buckets"] == 1


def test_update_with_value(client):
    resp = client.post("/api/v1/window/update", params={"value": 10})
    assert resp.status_code == 200
    assert resp.json()["now"] == 0 and resp.json()["count"] > 0


def test_update_with_timestamp(client):
    resp = client.post("/api/v1/window/update", params={"timestamp": 42})
    assert resp.status_code == 200
    assert resp.json()["now"] == 42


def test_update_invalid_value_returns_422(client):
    assert client.post("/api/v1/window/update", params={"value": 0}).status_code == 422


def test_update_non_monotone_timestamp_returns_422(client):
    client.post("/api/v1/window/update", params={"timestamp": 10})
    resp = client.post("/api/v1/window/update", params={"timestamp": 5})
    assert resp.status_code == 422
    assert "error" in resp.json()


# ── count ───────────────────────────────────────────────────────────────────────

def test_count_accuracy(dense_client):
    body = dense_client.get("/api/v1/window/count").json()
    assert abs(body["count"] - 500) / 500 <= 0.25      # window 500, ε=0.5 → ε/2


def test_count_empty_is_zero(client):
    assert client.get("/api/v1/window/count").json()["count"] == 0


def test_count_after_updates(client):
    for _ in range(10):
        client.post("/api/v1/window/update")
    body = client.get("/api/v1/window/count").json()
    assert body["now"] == 9 and body["count"] > 0


# ── oldest ──────────────────────────────────────────────────────────────────────

def test_oldest_returns_timestamp(client):
    for _ in range(50):
        client.post("/api/v1/window/update")
    assert isinstance(client.get("/api/v1/window/oldest").json()["oldest"], int)


def test_oldest_empty_is_null(client):
    assert client.get("/api/v1/window/oldest").json()["oldest"] is None


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/window/stats").json()
    assert set(data) == {"window", "epsilon", "k", "num_buckets", "count", "oldest", "now"}


def test_stats_tracks(client):
    for _ in range(100):
        client.post("/api/v1/window/update")
    data = client.get("/api/v1/window/stats").json()
    assert data["now"] == 99 and data["num_buckets"] > 0


def test_stats_default_window(client):
    assert client.get("/api/v1/window/stats").json()["window"] == 1000


# ── sliding-window over HTTP ──────────────────────────────────────────────────────

def test_sliding_expiry_over_http(client):
    client.post("/api/v1/window/reset", params={"window": 500, "epsilon": 0.2})
    for i in range(50):
        client.post("/api/v1/window/update", params={"timestamp": i})
    for i in range(30):
        client.post("/api/v1/window/update", params={"timestamp": 800 + i})
    count = client.get("/api/v1/window/count").json()["count"]
    assert abs(count - 30) / 30 <= 0.3                 # the first 50 (ticks 0..49) expired


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for _ in range(100):
        client.post("/api/v1/window/update")
    resp = client.post("/api/v1/window/reset")
    assert resp.status_code == 200
    assert resp.json()["now"] == -1 and resp.json()["count"] == 0


def test_reset_reconfigures_window(client):
    resp = client.post("/api/v1/window/reset", params={"window": 256})
    assert resp.json()["window"] == 256


def test_reset_reconfigures_epsilon(client):
    resp = client.post("/api/v1/window/reset", params={"epsilon": 0.1})
    assert resp.json()["epsilon"] == 0.1 and resp.json()["k"] == 10


def test_reset_bad_window_returns_422(client):
    assert client.post("/api/v1/window/reset", params={"window": 0}).status_code == 422


def test_reset_bad_epsilon_returns_422(client):
    assert client.post("/api/v1/window/reset", params={"epsilon": 1.5}).status_code == 422


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–96 routes still respond
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
    assert client.get("/api/v1/ddsketch/stats").status_code == 200
