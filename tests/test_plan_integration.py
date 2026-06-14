"""Tests for the L1 planner bridge — /api/v1/plan.

It glues two EXISTING planes: the skill library (match an intent to learned
skills) and FORESIGHT (deliberate over the matches). No new skill store is
introduced — this is integration, not duplication.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _learn(c, sid, name, trigger, steps):
    return c.post(
        "/api/v1/skills/learn",
        json={"id": sid, "name": name, "trigger": trigger, "steps": steps},
    )


def test_plan_requires_intent():
    assert _client().post("/api/v1/plan", json={}).status_code == 422


def test_plan_empty_when_no_skill_matches():
    c = _client()
    r = c.post("/api/v1/plan", json={"intent": "totally unrelated request xyzzy"})
    assert r.status_code == 200
    assert r.json()["chosen"] is None
    assert r.json()["steps"] == []


def test_plan_matches_and_returns_steps():
    c = _client()
    _learn(c, "cache1", "cache-results", "cache query results speed", ["detect", "store", "serve"])
    _learn(c, "mail1", "send-email", "email deliver user", ["compose", "send"])
    r = c.post("/api/v1/plan", json={"intent": "how to cache query results for speed"})
    body = r.json()
    assert body["chosen"] == "cache-results"
    assert body["skill_id"] == "cache1"
    assert body["steps"] == ["detect", "store", "serve"]
    assert body["ranked"]  # foresight produced a ranking


def test_plan_ranking_uses_foresight_outcomes():
    c = _client()
    _learn(c, "a1", "approach-a", "handle the task well", ["a"])
    _learn(c, "b1", "approach-b", "handle the task well", ["b"])
    # teach FORESIGHT that approach-a yields high value, approach-b low
    for _ in range(6):
        c.post("/api/v1/foresight/observe", json={"state": "handle the task well", "action": "approach-a", "value": 0.95})
        c.post("/api/v1/foresight/observe", json={"state": "handle the task well", "action": "approach-b", "value": 0.05})
    r = c.post("/api/v1/plan", json={"intent": "handle the task well"})
    assert r.json()["chosen"] == "approach-a"
