"""Agent 6 — tests for the /api/v1/synaptic endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed(client):
    client.post("/api/v1/synaptic/model", json={"name": "qwen", "provider": "ollama"})
    client.post("/api/v1/synaptic/model", json={"name": "gpt", "provider": "openai"})
    client.post("/api/v1/synaptic/benchmark", json={"name": "qwen", "score": 0.5})
    client.post("/api/v1/synaptic/benchmark", json={"name": "gpt", "score": 0.9})
    client.post("/api/v1/synaptic/default", json={"name": "qwen"})


def test_register_and_models(client):
    client.post("/api/v1/synaptic/model", json={"name": "m1"})
    assert client.get("/api/v1/synaptic/models").json()["models"][0]["name"] == "m1"


def test_register_missing_422(client):
    assert client.post("/api/v1/synaptic/model", json={}).status_code == 422


def test_benchmark_bad_score_422(client):
    client.post("/api/v1/synaptic/model", json={"name": "m"})
    assert (
        client.post("/api/v1/synaptic/benchmark", json={"name": "m", "score": 2}).status_code == 422
    )


def test_benchmark_unknown_404(client):
    assert (
        client.post("/api/v1/synaptic/benchmark", json={"name": "nope", "score": 0.5}).status_code
        == 404
    )


def test_evaluate_proposes_upgrade(client):
    _seed(client)
    ev = client.get("/api/v1/synaptic/evaluate").json()
    assert ev["recommended"] == "gpt" and ev["proposals"][0]["model"] == "gpt"


def test_evaluate_requires_default_422(client):
    client.post("/api/v1/synaptic/model", json={"name": "m"})
    assert client.get("/api/v1/synaptic/evaluate").status_code == 422


def test_promote_swaps_default(client):
    _seed(client)
    client.post("/api/v1/synaptic/promote", json={"name": "gpt"})
    ev = client.get("/api/v1/synaptic/evaluate").json()
    assert ev["default"] == "gpt" and ev["proposals"] == []


def test_stats_and_reset(client):
    _seed(client)
    stats = client.get("/api/v1/synaptic/stats").json()
    assert stats["models"] == 2 and stats["benchmarked"] == 2 and stats["default"] == "qwen"
    after = client.delete("/api/v1/synaptic/reset").json()
    assert after["models"] == 0
