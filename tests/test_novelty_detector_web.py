"""HTTP tests for the Sovereign Novelty Detector routes (/api/v1/novelty)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_observe_creates_observation():
    c = _client()
    r = c.post("/api/v1/novelty/observe", json={"item": "hello"})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_observe_requires_item():
    c = _client()
    assert c.post("/api/v1/novelty/observe", json={}).status_code == 422
    assert c.post("/api/v1/novelty/observe", json={"not_item": "x"}).status_code == 422


def test_observe_increments_total():
    c = _client()
    r1 = c.post("/api/v1/novelty/observe", json={"item": "x"})
    assert r1.json()["total"] == 1
    r2 = c.post("/api/v1/novelty/observe", json={"item": "x"})
    assert r2.json()["total"] == 2


def test_is_novel_first_time():
    c = _client()
    r = c.get("/api/v1/novelty/is_novel", params={"item": "fresh"})
    assert r.status_code == 200
    assert r.json()["is_novel"] is True


def test_is_novel_after_observe():
    c = _client()
    c.post("/api/v1/novelty/observe", json={"item": "seen"})
    r = c.get("/api/v1/novelty/is_novel", params={"item": "seen"})
    assert r.status_code == 200
    assert r.json()["is_novel"] is False


def test_is_novel_requires_item():
    c = _client()
    assert c.get("/api/v1/novelty/is_novel").status_code == 422


def test_rate_empty():
    c = _client()
    r = c.get("/api/v1/novelty/rate")
    assert r.status_code == 200
    assert r.json()["novelty_rate"] == 0.0


def test_rate_after_observations():
    c = _client()
    c.post("/api/v1/novelty/observe", json={"item": "a"})
    c.post("/api/v1/novelty/observe", json={"item": "a"})
    c.post("/api/v1/novelty/observe", json={"item": "b"})
    r = c.get("/api/v1/novelty/rate")
    assert r.json()["novelty_rate"] == pytest.approx(2.0 / 3.0)


def test_surprise_returns_score():
    c = _client()
    c.post("/api/v1/novelty/observe", json={"item": "test"})
    r = c.get("/api/v1/novelty/surprise", params={"item": "test"})
    assert r.status_code == 200
    assert "surprise_score" in r.json()
    assert isinstance(r.json()["surprise_score"], (int, float))


def test_surprise_requires_item():
    c = _client()
    assert c.get("/api/v1/novelty/surprise").status_code == 422


def test_stats_returns_dict():
    c = _client()
    r = c.get("/api/v1/novelty/stats")
    assert r.status_code == 200
    assert "total_observations" in r.json()
    assert "unique_estimate" in r.json()


def test_reset_clears():
    c = _client()
    c.post("/api/v1/novelty/observe", json={"item": "x"})
    assert c.get("/api/v1/novelty/stats").json()["total_observations"] == 1
    r = c.request("DELETE", "/api/v1/novelty/reset")
    assert r.status_code == 200
    assert r.json()["total_observations"] == 0


def test_each_app_isolated():
    c1, c2 = _client(), _client()
    c1.post("/api/v1/novelty/observe", json={"item": "only1"})
    assert c1.get("/api/v1/novelty/stats").json()["total_observations"] == 1
    assert c2.get("/api/v1/novelty/stats").json()["total_observations"] == 0
