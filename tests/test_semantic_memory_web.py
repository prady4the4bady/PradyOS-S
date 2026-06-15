"""HTTP tests for the Sovereign Semantic Memory routes (/api/v1/semantic)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_store_then_recall_roundtrip():
    c = _client()
    r = c.post("/api/v1/semantic/store", json={"key": "d1", "content": "hi", "tokens": ["a", "b", "c"]})
    assert r.status_code == 200 and r.json()["size"] == 1
    rec = c.post("/api/v1/semantic/recall", json={"tokens": ["a", "b", "c"]})
    assert rec.status_code == 200
    assert rec.json()["results"][0]["key"] == "d1"


def test_store_requires_key_and_tokens():
    c = _client()
    assert c.post("/api/v1/semantic/store", json={"content": "x"}).status_code == 422
    assert c.post("/api/v1/semantic/store", json={"key": "k"}).status_code == 422


def test_store_tokens_must_be_list():
    c = _client()
    assert c.post("/api/v1/semantic/store", json={"key": "k", "tokens": "abc"}).status_code == 422


def test_recall_requires_tokens_list():
    c = _client()
    assert c.post("/api/v1/semantic/recall", json={}).status_code == 422
    assert c.post("/api/v1/semantic/recall", json={"tokens": "x"}).status_code == 422


def test_recall_top_k_validation():
    c = _client()
    assert c.post("/api/v1/semantic/recall", json={"tokens": ["a"], "top_k": 0}).status_code == 422
    assert c.post("/api/v1/semantic/recall", json={"tokens": ["a"], "top_k": -3}).status_code == 422


def test_recall_min_similarity_validation():
    c = _client()
    r = c.post("/api/v1/semantic/recall", json={"tokens": ["a"], "min_similarity": "high"})
    assert r.status_code == 422


def test_recall_respects_top_k():
    c = _client()
    for i in range(20):
        c.post("/api/v1/semantic/store", json={"key": f"d{i}", "tokens": ["a", "b", str(i)]})
    rec = c.post("/api/v1/semantic/recall", json={"tokens": ["a", "b"], "top_k": 5})
    assert rec.json()["count"] == 5


def test_recall_near_duplicate_ranks_first():
    c = _client()
    c.post("/api/v1/semantic/store", json={"key": "cats", "tokens": ["cat", "feline", "pet", "fur"]})
    c.post("/api/v1/semantic/store", json={"key": "cars", "tokens": ["car", "engine", "wheel", "road"]})
    rec = c.post("/api/v1/semantic/recall", json={"tokens": ["cat", "feline", "pet", "paw"]})
    assert rec.json()["results"][0]["key"] == "cats"


def test_recall_min_similarity_filters():
    c = _client()
    for i in range(30):
        c.post("/api/v1/semantic/store", json={"key": f"d{i}", "tokens": ["x", "y", str(i)]})
    rec = c.post("/api/v1/semantic/recall", json={"tokens": ["ZZ", "YY"], "top_k": 30, "min_similarity": 0.3})
    assert rec.json()["count"] < 30


def test_forget_prunes():
    c = _client()
    c.post("/api/v1/semantic/store", json={"key": "cold", "tokens": ["a"]})
    c.post("/api/v1/semantic/store", json={"key": "hot", "tokens": ["b"]})
    c.post("/api/v1/semantic/store", json={"key": "hot", "tokens": ["b"]})  # freq 2
    r = c.post("/api/v1/semantic/forget", json={"threshold": 2})
    assert r.json()["pruned"] == 1 and r.json()["size"] == 1


def test_forget_requires_threshold():
    c = _client()
    assert c.post("/api/v1/semantic/forget", json={}).status_code == 422


def test_forget_threshold_must_be_number():
    c = _client()
    assert c.post("/api/v1/semantic/forget", json={"threshold": "lots"}).status_code == 422


def test_stats_shape():
    c = _client()
    c.post("/api/v1/semantic/store", json={"key": "d", "tokens": ["a", "b"]})
    s = c.get("/api/v1/semantic/stats").json()
    for k in ("size", "num_hashes", "simhash_bits", "top_concepts", "capacity"):
        assert k in s
    assert s["size"] == 1


def test_reset_clears():
    c = _client()
    c.post("/api/v1/semantic/store", json={"key": "d", "tokens": ["a"]})
    assert c.delete("/api/v1/semantic/reset").json()["size"] == 0


def test_recall_empty_memory():
    c = _client()
    rec = c.post("/api/v1/semantic/recall", json={"tokens": ["a", "b"]})
    assert rec.status_code == 200 and rec.json()["count"] == 0


def test_each_app_has_isolated_memory():
    # factory scope — two apps do not share state
    c1, c2 = _client(), _client()
    c1.post("/api/v1/semantic/store", json={"key": "only-in-1", "tokens": ["a"]})
    assert c1.get("/api/v1/semantic/stats").json()["size"] == 1
    assert c2.get("/api/v1/semantic/stats").json()["size"] == 0
