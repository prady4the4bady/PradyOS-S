"""Tests for the cross-plane integration: FORESIGHT → CAUSALITY, causal-aware plan.

Observing outcomes through FORESIGHT must auto-feed CAUSALITY (action causes
success), and /api/v1/plan must re-weight skills by that causal strength.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_foresight_observe_feeds_causality():
    c = _client()
    for _ in range(8):
        c.post("/api/v1/foresight/observe", json={"state": "t", "action": "cache", "value": 0.9})
        c.post("/api/v1/foresight/observe", json={"state": "t", "action": "slow", "value": 0.1})
    # CAUSALITY learned the trials with no direct call
    st = c.get("/api/v1/causality/stats").json()
    assert st["trials"] >= 16
    cf = c.get("/api/v1/causality/counterfactual", params={"cause": "cache", "effect": "success"}).json()
    assert cf["status"] == "ok"
    assert cf["strength"] > 0.5


def test_plan_is_causal_aware():
    c = _client()
    # two equally-matched skills; make 'cache' causally good, 'slow' causally bad
    c.post("/api/v1/skills/learn", json={"id": "cache", "name": "cache",
                                          "trigger": "speed up requests fast", "steps": ["x"]})
    c.post("/api/v1/skills/learn", json={"id": "slow", "name": "slow",
                                          "trigger": "speed up requests fast", "steps": ["y"]})
    for _ in range(8):
        c.post("/api/v1/foresight/observe", json={"state": "speed up requests fast", "action": "cache", "value": 0.95})
        c.post("/api/v1/foresight/observe", json={"state": "speed up requests fast", "action": "slow", "value": 0.05})
    plan = c.post("/api/v1/plan", json={"intent": "speed up requests fast"}).json()
    assert plan["chosen"] == "cache"
    # the ranking now carries a causal_strength signal
    assert "causal_strength" in plan["ranked"][0]
    top = next(r for r in plan["ranked"] if r["action"] == "cache")
    assert top["causal_strength"] > 0
