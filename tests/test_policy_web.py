"""Phase 14E — Policy web endpoint tests (10 tests).

FastAPI TestClient for:
    GET  /api/v1/policy/rules
    POST /api/v1/policy/rules

Covers:
 1.  GET /api/v1/policy/rules returns HTTP 200
 2.  GET response has "rules" key
 3.  rules is a list
 4.  POST /api/v1/policy/rules returns HTTP 200
 5.  POST response has "loaded" key
 6.  loaded == len(rules) sent
 7.  GET after POST reflects new rules
 8.  POST with empty list clears rules, GET returns []
 9.  Content-Type application/json on GET
10.  Content-Type application/json on POST
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.imperium.policy_engine import PolicyEngine
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(engine: PolicyEngine | None = None) -> TestClient:
    """Create a TestClient with an optional shared PolicyEngine."""
    app = create_app(policy_engine=engine)
    return TestClient(app)


_SAMPLE_RULES = [
    {
        "type": "constitutional_guard",
        "match": {"action": "drop"},
        "deny_reason": "drop is prohibited",
    },
    {
        "type": "rate_limit",
        "match": {},
        "max_per_minute": 100,
        "window_seconds": 60,
    },
]


# ---------------------------------------------------------------------------
# Test 1: GET /api/v1/policy/rules returns HTTP 200
# ---------------------------------------------------------------------------

def test_get_rules_returns_200():
    engine = PolicyEngine()
    client = _client(engine)
    resp = client.get("/api/v1/policy/rules")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 2: GET response has "rules" key
# ---------------------------------------------------------------------------

def test_get_rules_response_has_rules_key():
    engine = PolicyEngine()
    client = _client(engine)
    data = client.get("/api/v1/policy/rules").json()
    assert "rules" in data


# ---------------------------------------------------------------------------
# Test 3: rules is a list
# ---------------------------------------------------------------------------

def test_get_rules_value_is_list():
    engine = PolicyEngine()
    client = _client(engine)
    data = client.get("/api/v1/policy/rules").json()
    assert isinstance(data["rules"], list)


# ---------------------------------------------------------------------------
# Test 4: POST /api/v1/policy/rules returns HTTP 200
# ---------------------------------------------------------------------------

def test_post_rules_returns_200():
    engine = PolicyEngine()
    client = _client(engine)
    resp = client.post("/api/v1/policy/rules", json={"rules": _SAMPLE_RULES})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 5: POST response has "loaded" key
# ---------------------------------------------------------------------------

def test_post_rules_response_has_loaded_key():
    engine = PolicyEngine()
    client = _client(engine)
    data = client.post("/api/v1/policy/rules", json={"rules": _SAMPLE_RULES}).json()
    assert "loaded" in data


# ---------------------------------------------------------------------------
# Test 6: loaded == len(rules) sent
# ---------------------------------------------------------------------------

def test_post_rules_loaded_equals_sent_count():
    engine = PolicyEngine()
    client = _client(engine)
    data = client.post("/api/v1/policy/rules", json={"rules": _SAMPLE_RULES}).json()
    assert data["loaded"] == len(_SAMPLE_RULES)


# ---------------------------------------------------------------------------
# Test 7: GET after POST reflects new rules
# ---------------------------------------------------------------------------

def test_get_after_post_reflects_new_rules():
    engine = PolicyEngine()
    client = _client(engine)

    client.post("/api/v1/policy/rules", json={"rules": _SAMPLE_RULES})

    data = client.get("/api/v1/policy/rules").json()
    assert len(data["rules"]) == len(_SAMPLE_RULES)
    types = {r["type"] for r in data["rules"]}
    assert "constitutional_guard" in types
    assert "rate_limit" in types


# ---------------------------------------------------------------------------
# Test 8: POST with empty list clears rules, GET returns []
# ---------------------------------------------------------------------------

def test_post_empty_clears_rules():
    engine = PolicyEngine()
    client = _client(engine)

    # Load some rules first
    client.post("/api/v1/policy/rules", json={"rules": _SAMPLE_RULES})
    assert len(client.get("/api/v1/policy/rules").json()["rules"]) == len(_SAMPLE_RULES)

    # Clear them
    client.post("/api/v1/policy/rules", json={"rules": []})
    data = client.get("/api/v1/policy/rules").json()
    assert data["rules"] == []


# ---------------------------------------------------------------------------
# Test 9: Content-Type application/json on GET
# ---------------------------------------------------------------------------

def test_get_rules_content_type_is_json():
    engine = PolicyEngine()
    client = _client(engine)
    resp = client.get("/api/v1/policy/rules")
    ct = resp.headers.get("content-type", "")
    assert "application/json" in ct


# ---------------------------------------------------------------------------
# Test 10: Content-Type application/json on POST
# ---------------------------------------------------------------------------

def test_post_rules_content_type_is_json():
    engine = PolicyEngine()
    client = _client(engine)
    resp = client.post("/api/v1/policy/rules", json={"rules": []})
    ct = resp.headers.get("content-type", "")
    assert "application/json" in ct
