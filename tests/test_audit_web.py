"""Phase 20D — Audit Trail web endpoint tests (10 tests).

FastAPI TestClient for GET /audit.

Covers:
  1.  GET /audit returns HTTP 200
  2.  Content-Type is text/html
  3.  Response body contains '<!DOCTYPE html'
  4.  Response body contains 'Event Ledger'
  5.  Response body contains 'Telemetry Spans'
  6.  Response body contains 'Intent Suggestions'
  7.  Response body contains '/api/v1/ledger'
  8.  Response body contains '/api/v1/telemetry'
  9.  Response body contains '/api/v1/intent/suggest'
 10.  Response is identical on two consecutive calls (idempotent)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> TestClient:
    """Return a TestClient for an app created with no injected dependencies."""
    app = create_app()
    return TestClient(app)


# ===========================================================================
# Test 1: GET /audit returns HTTP 200
# ===========================================================================

def test_get_audit_returns_200():
    client = _client()
    resp = client.get("/audit")
    assert resp.status_code == 200


# ===========================================================================
# Test 2: Content-Type is text/html
# ===========================================================================

def test_get_audit_content_type_is_html():
    client = _client()
    resp = client.get("/audit")
    assert "text/html" in resp.headers.get("content-type", "")


# ===========================================================================
# Test 3: Response body contains '<!DOCTYPE html'
# ===========================================================================

def test_get_audit_body_has_doctype():
    client = _client()
    resp = client.get("/audit")
    assert "<!DOCTYPE html" in resp.text


# ===========================================================================
# Test 4: Response body contains 'Event Ledger'
# ===========================================================================

def test_get_audit_body_has_event_ledger():
    client = _client()
    resp = client.get("/audit")
    assert "Event Ledger" in resp.text


# ===========================================================================
# Test 5: Response body contains 'Telemetry Spans'
# ===========================================================================

def test_get_audit_body_has_telemetry_spans():
    client = _client()
    resp = client.get("/audit")
    assert "Telemetry Spans" in resp.text


# ===========================================================================
# Test 6: Response body contains 'Intent Suggestions'
# ===========================================================================

def test_get_audit_body_has_intent_suggestions():
    client = _client()
    resp = client.get("/audit")
    assert "Intent Suggestions" in resp.text


# ===========================================================================
# Test 7: Response body contains '/api/v1/ledger'
# ===========================================================================

def test_get_audit_body_references_ledger_api():
    client = _client()
    resp = client.get("/audit")
    assert "/api/v1/ledger" in resp.text


# ===========================================================================
# Test 8: Response body contains '/api/v1/telemetry'
# ===========================================================================

def test_get_audit_body_references_telemetry_api():
    client = _client()
    resp = client.get("/audit")
    assert "/api/v1/telemetry" in resp.text


# ===========================================================================
# Test 9: Response body contains '/api/v1/intent/suggest'
# ===========================================================================

def test_get_audit_body_references_intent_suggest_api():
    client = _client()
    resp = client.get("/audit")
    assert "/api/v1/intent/suggest" in resp.text


# ===========================================================================
# Test 10: Two consecutive GET /audit calls return identical bodies
# ===========================================================================

def test_get_audit_response_is_idempotent():
    client = _client()
    resp1 = client.get("/audit")
    resp2 = client.get("/audit")
    assert resp1.text == resp2.text
