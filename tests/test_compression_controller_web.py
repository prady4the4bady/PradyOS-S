"""HTTP tests for the Compression Controller routes (/api/v1/compression)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_strategies():
    c = _client()
    r = c.get("/api/v1/compression/strategies")
    assert r.status_code == 200
    assert "topk" in r.json()["strategies"]


def test_feed_topk():
    c = _client()
    r = c.post("/api/v1/compression/feed", json={
        "items": ["a", "b", "a", "c", "a"], "strategy": "topk"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["strategy"] == "topk"
    assert data["total"] == 5


def test_feed_bloom():
    c = _client()
    r = c.post("/api/v1/compression/feed", json={
        "items": ["x", "y", "z"], "strategy": "bloom"
    })
    assert r.status_code == 200
    assert r.json()["total_fed"] == 3


def test_feed_minhash():
    c = _client()
    r = c.post("/api/v1/compression/feed", json={
        "items": ["king", "queen", "man", "woman"], "strategy": "minhash"
    })
    assert r.status_code == 200
    assert r.json()["signature"] is not None


def test_feed_requires_body():
    c = _client()
    assert c.post("/api/v1/compression/feed", json={}).status_code == 422
    assert c.post("/api/v1/compression/feed", json={"items": "bad"}).status_code == 422
    assert c.post("/api/v1/compression/feed", json={"items": [], "strategy": "nonexistent"}).status_code == 422


def test_summarize_topk():
    c = _client()
    c.post("/api/v1/compression/feed", json={
        "items": ["a", "b", "a"], "strategy": "topk"
    })
    r = c.post("/api/v1/compression/summarize", json={"strategy": "topk"})
    assert r.status_code == 200
    assert r.json()["total"] == 3


def test_summarize_before_feed():
    c = _client()
    r = c.post("/api/v1/compression/summarize", json={"strategy": "bloom"})
    assert r.status_code == 200
    assert r.json()["total_fed"] == 0


def test_estimate():
    c = _client()
    r = c.post("/api/v1/compression/estimate", json={
        "items": ["hello", "world"], "strategy": "topk"
    })
    assert r.status_code == 200
    assert r.json()["raw_items"] == 2


def test_estimate_requires_items():
    c = _client()
    assert c.post("/api/v1/compression/estimate", json={}).status_code == 422


def test_stats():
    c = _client()
    r = c.get("/api/v1/compression/stats")
    assert r.status_code == 200
    assert "strategies" in r.json()


def test_reset():
    c = _client()
    c.post("/api/v1/compression/feed", json={
        "items": ["a"], "strategy": "topk"
    })
    assert c.post("/api/v1/compression/summarize", json={"strategy": "topk"}).json()["total"] == 1
    c.post("/api/v1/compression/reset", json={})
    assert c.post("/api/v1/compression/summarize", json={"strategy": "topk"}).json()["total"] == 0


def test_reset_single_strategy():
    c = _client()
    c.post("/api/v1/compression/feed", json={"items": ["a"], "strategy": "topk"})
    c.post("/api/v1/compression/feed", json={"items": ["x"], "strategy": "bloom"})
    c.post("/api/v1/compression/reset", json={"strategy": "topk"})
    assert c.post("/api/v1/compression/summarize", json={"strategy": "topk"}).json()["total"] == 0
    assert c.post("/api/v1/compression/summarize", json={"strategy": "bloom"}).json()["total_fed"] == 1


def test_each_app_isolated():
    c1, c2 = _client(), _client()
    c1.post("/api/v1/compression/feed", json={"items": ["only1"], "strategy": "topk"})
    assert c1.post("/api/v1/compression/summarize", json={"strategy": "topk"}).json()["total"] == 1
    assert c2.post("/api/v1/compression/summarize", json={"strategy": "topk"}).json()["total"] == 0
