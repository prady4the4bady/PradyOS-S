"""Tests for the /api/v1/skills endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.skills import SkillLibrary
from pradyos.web.skills_web import register_skills_routes


@pytest.fixture()
def client():
    app = FastAPI()
    register_skills_routes(app, SkillLibrary())
    return TestClient(app)


def _learn(client, sid="s", name="Deploy", trigger="deploy web service", steps=None):
    return client.post(
        "/api/v1/skills/learn",
        json={"id": sid, "name": name, "trigger": trigger, "steps": steps or ["build", "ship"]},
    )


def test_learn_and_recall(client):
    body = _learn(client).json()
    assert body["id"] == "s" and body["confidence"] == 0.5
    assert client.get("/api/v1/skills/recall", params={"id": "s"}).json()["name"] == "Deploy"


def test_learn_missing_fields_422(client):
    assert client.post("/api/v1/skills/learn", json={"id": "s"}).status_code == 422


def test_learn_duplicate_422(client):
    _learn(client)
    assert _learn(client).status_code == 422


def test_reinforce_and_confidence(client):
    _learn(client)
    for _ in range(3):
        client.post("/api/v1/skills/reinforce", json={"id": "s", "success": True})
    assert client.get("/api/v1/skills/recall", params={"id": "s"}).json()["confidence"] == 0.8


def test_reinforce_non_bool_422(client):
    _learn(client)
    assert (
        client.post("/api/v1/skills/reinforce", json={"id": "s", "success": "yes"}).status_code
        == 422
    )


def test_reinforce_unknown_404(client):
    assert (
        client.post("/api/v1/skills/reinforce", json={"id": "ghost", "success": True}).status_code
        == 404
    )


def test_match_ranks(client):
    _learn(client, sid="a", trigger="deploy web", steps=["x"])
    _learn(client, sid="b", trigger="deploy database", steps=["x"])
    out = client.post("/api/v1/skills/match", json={"intent": "deploy the web service"}).json()
    assert [s["id"] for s in out["skills"]] == ["a", "b"]


def test_match_missing_intent_422(client):
    assert client.post("/api/v1/skills/match", json={}).status_code == 422


def test_revise(client):
    _learn(client)
    body = client.post("/api/v1/skills/revise", json={"id": "s", "steps": ["new"]}).json()
    assert body["steps"] == ["new"] and body["version"] == 2


def test_prune_retires_failing(client):
    _learn(client, sid="good", trigger="trig word", steps=["s"])
    _learn(client, sid="bad", trigger="trig word", steps=["s"])
    for _ in range(3):
        client.post("/api/v1/skills/reinforce", json={"id": "good", "success": True})
        client.post("/api/v1/skills/reinforce", json={"id": "bad", "success": False})
    pruned = client.post(
        "/api/v1/skills/prune", json={"min_confidence": 0.34, "min_attempts": 3}
    ).json()
    assert pruned["pruned"] == ["bad"]


def test_recall_unknown_404(client):
    assert client.get("/api/v1/skills/recall", params={"id": "ghost"}).status_code == 404


def test_list_stats_reset(client):
    _learn(client, sid="a", steps=["s"])
    _learn(client, sid="b", steps=["s"])
    assert len(client.get("/api/v1/skills/list").json()["skills"]) == 2
    assert client.get("/api/v1/skills/stats").json()["skills"] == 2
    assert client.delete("/api/v1/skills/reset").json()["skills"] == 0
