"""Tests for the /api/v1/review endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.review import ReviewGate
from pradyos.web.review_web import register_review_routes


@pytest.fixture()
def client():
    app = FastAPI()
    register_review_routes(app, ReviewGate())
    return TestClient(app)


def test_assess_approve(client):
    body = client.post(
        "/api/v1/review/assess",
        json={
            "path": "pradyos/foo.py",
            "before": "def f():\n    pass\n",
            "after": "def f():\n    return 1\n",
        },
    ).json()
    assert body["decision"] == "approve" and body["seq"] == 1


def test_assess_deny_on_api_removal(client):
    body = client.post(
        "/api/v1/review/assess",
        json={
            "path": "pradyos/foo.py",
            "before": "def a():\n    pass\n\n\ndef b():\n    pass\n",
            "after": "def a():\n    pass\n",
        },
    ).json()
    assert body["decision"] == "deny"


def test_assess_escalate_on_forbidden_path(client):
    body = client.post(
        "/api/v1/review/assess",
        json={"path": "pradyos/core/constitution.py", "after": "x = 2\n"},
    ).json()
    assert body["decision"] == "escalate"


def test_assess_missing_fields_422(client):
    assert client.post("/api/v1/review/assess", json={"path": "p"}).status_code == 422


def test_assess_after_not_string_422(client):
    assert client.post("/api/v1/review/assess", json={"path": "p", "after": 5}).status_code == 422


def test_review_roundtrip_and_unknown(client):
    client.post("/api/v1/review/assess", json={"path": "pradyos/a.py", "after": "x = 1\n"})
    assert client.get("/api/v1/review/review", params={"seq": 1}).json()["seq"] == 1
    assert client.get("/api/v1/review/review", params={"seq": 99}).status_code == 404


def test_reviews_and_stats_and_reset(client):
    client.post("/api/v1/review/assess", json={"path": "pradyos/a.py", "after": "x = 1\n"})
    client.post("/api/v1/review/assess", json={"path": "pradyos/bastion/x.py", "after": "y = 1\n"})
    assert len(client.get("/api/v1/review/reviews").json()["reviews"]) == 2
    stats = client.get("/api/v1/review/stats").json()
    assert stats["reviews"] == 2 and stats["by_decision"]["escalate"] == 1
    assert client.delete("/api/v1/review/reset").json()["reviews"] == 0
