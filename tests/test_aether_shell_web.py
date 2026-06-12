"""Plane 10 — tests for the /api/v1/aether endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_capture_intent_routes(client):
    body = client.post(
        "/api/v1/aether/intent", json={"id": "i1", "text": "approve the proposal"}
    ).json()
    assert body["surface"] == "governance"


def test_intent_missing_422(client):
    assert client.post("/api/v1/aether/intent", json={"id": "i"}).status_code == 422


def test_push_card_and_experience(client):
    client.post(
        "/api/v1/aether/card",
        json={"id": "c1", "surface": "alerts", "title": "breach!", "urgency": "urgent"},
    )
    exp = client.get("/api/v1/aether/experience").json()
    assert exp["counts"]["urgent"] == 1 and "attention" in exp["headline"]


def test_push_bad_surface_422(client):
    resp = client.post("/api/v1/aether/card", json={"id": "c", "surface": "void", "title": "t"})
    assert resp.status_code == 422


def test_push_bad_urgency_422(client):
    resp = client.post(
        "/api/v1/aether/card",
        json={"id": "c", "surface": "governance", "title": "t", "urgency": "panic"},
    )
    assert resp.status_code == 422


def test_ack_card(client):
    client.post("/api/v1/aether/card", json={"id": "c", "surface": "projects", "title": "x"})
    client.post("/api/v1/aether/ack", json={"id": "c"})
    assert client.get("/api/v1/aether/experience").json()["counts"]["active"] == 0


def test_ack_unknown_404(client):
    assert client.post("/api/v1/aether/ack", json={"id": "nope"}).status_code == 404


def test_experience_urgent_ordering(client):
    client.post("/api/v1/aether/card", json={"id": "c1", "surface": "projects", "title": "info"})
    client.post(
        "/api/v1/aether/card",
        json={"id": "c2", "surface": "alerts", "title": "urgent", "urgency": "urgent"},
    )
    order = [c["id"] for c in client.get("/api/v1/aether/experience").json()["active"]]
    assert order == ["c2", "c1"]


def test_stats_and_reset(client):
    client.post("/api/v1/aether/intent", json={"id": "i", "text": "build"})
    client.post("/api/v1/aether/card", json={"id": "c", "surface": "projects", "title": "x"})
    stats = client.get("/api/v1/aether/stats").json()
    assert stats["intents"] == 1 and stats["cards"] == 1
    after = client.delete("/api/v1/aether/reset").json()
    assert after["cards"] == 0
