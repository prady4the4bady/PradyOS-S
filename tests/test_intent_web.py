"""Phase 19D — Intent web endpoint tests (10 tests).

FastAPI TestClient for:
  GET  /api/v1/intent/rules
  POST /api/v1/intent/rules
  POST /api/v1/intent/suggest

Covers:
  1.  GET /api/v1/intent/rules returns 200
  2.  rules response has "rules" and "count" keys
  3.  POST /api/v1/intent/rules returns 200 with "loaded" key
  4.  POST /api/v1/intent/suggest returns 200
  5.  suggest response has "suggestions" and "count" keys
  6.  count == len(suggestions)
  7.  POST suggest with graph_nodes_gt rule fires correctly
  8.  GET rules after POST reflects loaded rules
  9.  No intent injected -> GET rules returns {"rules": [], "count": 0}
 10.  No intent injected -> POST suggest returns {"suggestions": [], "count": 0}
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.intent_engine import IntentEngine
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(*rules) -> IntentEngine:
    return IntentEngine(rules=list(rules))


def _client_with_engine(engine: IntentEngine) -> TestClient:
    app = create_app(intent=engine)
    return TestClient(app)


def _client_no_intent() -> TestClient:
    app = create_app()
    return TestClient(app)


def _graph_nodes_gt_rule(threshold: float = 5.0) -> dict:
    return {
        "id": "r_graph",
        "condition": "graph_nodes_gt",
        "threshold": threshold,
        "action": "scale_workers",
        "target": "worker_pool",
        "reason": "graph grew large",
        "confidence": 0.85,
    }


# ===========================================================================
# Test 1: GET /api/v1/intent/rules returns 200
# ===========================================================================

def test_get_rules_returns_200():
    client = _client_with_engine(IntentEngine())
    resp = client.get("/api/v1/intent/rules")
    assert resp.status_code == 200


# ===========================================================================
# Test 2: rules response has "rules" and "count" keys
# ===========================================================================

def test_get_rules_response_has_required_keys():
    client = _client_with_engine(IntentEngine())
    data = client.get("/api/v1/intent/rules").json()
    assert "rules" in data
    assert "count" in data


# ===========================================================================
# Test 3: POST /api/v1/intent/rules returns 200 with "loaded" key
# ===========================================================================

def test_post_rules_returns_200_with_loaded_key():
    client = _client_with_engine(IntentEngine())
    resp = client.post("/api/v1/intent/rules", json={"rules": [_graph_nodes_gt_rule()]})
    assert resp.status_code == 200
    data = resp.json()
    assert "loaded" in data
    assert data["loaded"] == 1


# ===========================================================================
# Test 4: POST /api/v1/intent/suggest returns 200
# ===========================================================================

def test_post_suggest_returns_200():
    client = _client_with_engine(IntentEngine())
    resp = client.post("/api/v1/intent/suggest", json={})
    assert resp.status_code == 200


# ===========================================================================
# Test 5: suggest response has "suggestions" and "count" keys
# ===========================================================================

def test_post_suggest_response_has_required_keys():
    client = _client_with_engine(IntentEngine())
    data = client.post("/api/v1/intent/suggest", json={}).json()
    assert "suggestions" in data
    assert "count" in data


# ===========================================================================
# Test 6: count == len(suggestions)
# ===========================================================================

def test_post_suggest_count_matches_length():
    engine = _make_engine(_graph_nodes_gt_rule(threshold=2.0))
    client = _client_with_engine(engine)
    body = {"graph_stats": {"nodes": 10}}
    data = client.post("/api/v1/intent/suggest", json=body).json()
    assert data["count"] == len(data["suggestions"])


# ===========================================================================
# Test 7: POST suggest with graph_nodes_gt rule fires correctly
# ===========================================================================

def test_post_suggest_graph_nodes_gt_fires():
    engine = _make_engine(_graph_nodes_gt_rule(threshold=5.0))
    client = _client_with_engine(engine)
    body = {"graph_stats": {"nodes": 10}}
    data = client.post("/api/v1/intent/suggest", json=body).json()
    assert data["count"] == 1
    s = data["suggestions"][0]
    assert s["action"] == "scale_workers"
    assert s["target"] == "worker_pool"
    assert "suggestion_id" in s
    assert "ts" in s


# ===========================================================================
# Test 8: GET rules after POST reflects loaded rules
# ===========================================================================

def test_get_rules_reflects_posted_rules():
    engine = IntentEngine()
    client = _client_with_engine(engine)

    # Start empty
    data_before = client.get("/api/v1/intent/rules").json()
    assert data_before["count"] == 0

    # Load one rule
    client.post("/api/v1/intent/rules", json={"rules": [_graph_nodes_gt_rule()]})

    # GET should now reflect it
    data_after = client.get("/api/v1/intent/rules").json()
    assert data_after["count"] == 1
    assert data_after["rules"][0]["condition"] == "graph_nodes_gt"


# ===========================================================================
# Test 9: No intent injected -> GET rules returns {"rules": [], "count": 0}
# ===========================================================================

def test_get_rules_no_intent_safe_empty():
    client = _client_no_intent()
    data = client.get("/api/v1/intent/rules").json()
    assert data["rules"] == []
    assert data["count"] == 0


# ===========================================================================
# Test 10: No intent injected -> POST suggest returns {"suggestions": [], "count": 0}
# ===========================================================================

def test_post_suggest_no_intent_safe_empty():
    client = _client_no_intent()
    data = client.post("/api/v1/intent/suggest", json={"graph_stats": {"nodes": 999}}).json()
    assert data["suggestions"] == []
    assert data["count"] == 0
