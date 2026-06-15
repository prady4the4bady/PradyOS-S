"""HTTP tests for the Sovereign Attention routes (/api/v1/attention)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_attend_then_top_roundtrip():
    c = _client()
    r = c.post("/api/v1/attention/attend", json={"tokens": ["agi"] * 50 + ["noise"]})
    assert r.status_code == 200 and r.json()["total_tokens"] == 51
    top = c.get("/api/v1/attention/top", params={"k": 1}).json()["top"]
    assert top[0]["token"] == "agi"


def test_attend_requires_tokens_list():
    c = _client()
    assert c.post("/api/v1/attention/attend", json={}).status_code == 422
    assert c.post("/api/v1/attention/attend", json={"tokens": "x"}).status_code == 422


def test_attend_empty_list_ok():
    c = _client()
    assert c.post("/api/v1/attention/attend", json={"tokens": []}).status_code == 200


def test_weight_requires_token():
    c = _client()
    assert c.get("/api/v1/attention/weight").status_code == 422


def test_weight_high_for_heavy_token():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": ["x"] * 1000 + ["y"]})
    assert c.get("/api/v1/attention/weight", params={"token": "x"}).json()["weight"] > 0.5
    assert c.get("/api/v1/attention/weight", params={"token": "y"}).json()["weight"] < 0.05


def test_weight_unseen_is_zero():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": ["a"]})
    assert c.get("/api/v1/attention/weight", params={"token": "never"}).json()["weight"] == 0.0


def test_top_k_validation():
    c = _client()
    assert c.get("/api/v1/attention/top", params={"k": 0}).status_code == 422
    assert c.get("/api/v1/attention/top", params={"k": -1}).status_code == 422


def test_top_respects_k():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": [f"t{i}" for i in range(20)]})
    assert len(c.get("/api/v1/attention/top", params={"k": 5}).json()["top"]) == 5


def test_top_orders_by_weight():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": ["big"] * 100 + ["mid"] * 10 + ["small"]})
    tokens = [d["token"] for d in c.get("/api/v1/attention/top", params={"k": 3}).json()["top"]]
    assert tokens == ["big", "mid", "small"]


def test_decay_decreases_weight():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": ["x"] * 50})
    before = c.get("/api/v1/attention/weight", params={"token": "x"}).json()["weight"]
    c.post("/api/v1/attention/decay")
    after = c.get("/api/v1/attention/weight", params={"token": "x"}).json()["weight"]
    assert after < before


def test_decay_counts_steps():
    c = _client()
    c.post("/api/v1/attention/decay")
    r = c.post("/api/v1/attention/decay")
    assert r.json()["decay_steps"] == 2


def test_stats_shape():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": ["a", "b"]})
    s = c.get("/api/v1/attention/stats").json()
    for k in ("total_tokens", "unique_tracked", "decay_steps", "scale", "count_sketch"):
        assert k in s
    assert s["total_tokens"] == 2


def test_reset_clears():
    c = _client()
    c.post("/api/v1/attention/attend", json={"tokens": ["x"] * 5})
    assert c.post("/api/v1/attention/reset").json()["total_tokens"] == 0


def test_top_empty():
    c = _client()
    assert c.get("/api/v1/attention/top", params={"k": 3}).json()["top"] == []


def test_each_app_isolated():
    c1, c2 = _client(), _client()
    c1.post("/api/v1/attention/attend", json={"tokens": ["only1"] * 10})
    assert c1.get("/api/v1/attention/stats").json()["total_tokens"] == 10
    assert c2.get("/api/v1/attention/stats").json()["total_tokens"] == 0
