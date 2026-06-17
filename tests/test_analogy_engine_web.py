"""HTTP tests for the Sovereign Analogy Engine routes (/api/v1/analogy)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_observe_creates():
    c = _client()
    r = c.post("/api/v1/analogy/observe", json={
        "analogy_id": "a1", "source_tokens": ["king", "man"], "target_tokens": ["queen", "woman"]
    })
    assert r.status_code == 200
    assert r.json()["status"] == "stored"


def test_observe_requires_field():
    c = _client()
    assert c.post("/api/v1/analogy/observe", json={}).status_code == 422
    assert c.post("/api/v1/analogy/observe", json={"analogy_id": "x"}).status_code == 422
    assert c.post("/api/v1/analogy/observe", json={"analogy_id": "x", "source_tokens": []}).status_code == 422


def test_observe_duplicate():
    c = _client()
    body = {"analogy_id": "x", "source_tokens": ["a"], "target_tokens": ["b"]}
    assert c.post("/api/v1/analogy/observe", json=body).status_code == 200
    assert c.post("/api/v1/analogy/observe", json=body).status_code == 200


def test_analogize_exact():
    c = _client()
    c.post("/api/v1/analogy/observe", json={
        "analogy_id": "a1", "source_tokens": ["x"], "target_tokens": ["y"]
    })
    r = c.post("/api/v1/analogy/analogize", json={
        "source_tokens": ["x"], "target_tokens": ["y"]
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data["analogies"]) == 1
    assert data["analogies"][0]["score"] == 1.0


def test_analogize_empty():
    c = _client()
    r = c.post("/api/v1/analogy/analogize", json={
        "source_tokens": ["x"], "target_tokens": ["y"]
    })
    assert r.status_code == 200
    assert r.json()["analogies"] == []


def test_analogize_requires_body():
    c = _client()
    assert c.post("/api/v1/analogy/analogize", json={"source_tokens": "bad"}).status_code == 422


def test_complete():
    c = _client()
    c.post("/api/v1/analogy/observe", json={
        "analogy_id": "a1", "source_tokens": ["king", "man"], "target_tokens": ["queen", "woman"]
    })
    r = c.post("/api/v1/analogy/complete", json={"source_tokens": ["king", "man"]})
    assert r.status_code == 200
    comps = r.json()["completions"]
    assert len(comps) >= 1
    assert "queen" in " ".join(comps[0]["target_tokens"])


def test_complete_empty():
    c = _client()
    r = c.post("/api/v1/analogy/complete", json={"source_tokens": ["x"]})
    assert r.status_code == 200
    assert r.json()["completions"] == []


def test_stats():
    c = _client()
    r = c.get("/api/v1/analogy/stats")
    assert r.status_code == 200
    assert "size" in r.json()
    assert "capacity" in r.json()


def test_reset():
    c = _client()
    c.post("/api/v1/analogy/observe", json={
        "analogy_id": "x", "source_tokens": ["a"], "target_tokens": ["b"]
    })
    assert c.get("/api/v1/analogy/stats").json()["size"] == 1
    r = c.post("/api/v1/analogy/reset")
    assert r.status_code == 200
    assert r.json()["size"] == 0


def test_each_app_isolated():
    c1, c2 = _client(), _client()
    c1.post("/api/v1/analogy/observe", json={
        "analogy_id": "a1", "source_tokens": ["x"], "target_tokens": ["y"]
    })
    assert c1.get("/api/v1/analogy/stats").json()["size"] == 1
    assert c2.get("/api/v1/analogy/stats").json()["size"] == 0
