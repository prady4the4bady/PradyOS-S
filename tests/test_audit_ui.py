"""Phase 20C — Audit Trail UI unit tests (10 tests).

Tests the ``pradyos.sovereign.audit_ui`` module in isolation.

Covers:
  1.  build_audit_html() returns a non-empty string
  2.  Return value starts with '<!DOCTYPE html'
  3.  Contains '/api/v1/ledger'
  4.  Contains '/api/v1/telemetry'
  5.  Contains '/api/v1/intent/suggest'
  6.  Contains 'Event Ledger' section heading
  7.  Contains 'Telemetry Spans' section heading
  8.  Contains 'Intent Suggestions' section heading
  9.  Contains auto-refresh logic (setInterval or setTimeout)
 10.  build_audit_html() called twice returns identical strings (idempotent)
"""
from __future__ import annotations

import pytest

from pradyos.sovereign.audit_ui import AUDIT_HTML, build_audit_html


# ===========================================================================
# Test 1: build_audit_html() returns a non-empty string
# ===========================================================================

def test_build_audit_html_returns_nonempty_string():
    result = build_audit_html()
    assert isinstance(result, str)
    assert len(result) > 0


# ===========================================================================
# Test 2: Return value contains '<!DOCTYPE html'
# ===========================================================================

def test_build_audit_html_has_doctype():
    result = build_audit_html()
    assert "<!DOCTYPE html" in result


# ===========================================================================
# Test 3: Contains '/api/v1/ledger'
# ===========================================================================

def test_build_audit_html_references_ledger_api():
    result = build_audit_html()
    assert "/api/v1/ledger" in result


# ===========================================================================
# Test 4: Contains '/api/v1/telemetry'
# ===========================================================================

def test_build_audit_html_references_telemetry_api():
    result = build_audit_html()
    assert "/api/v1/telemetry" in result


# ===========================================================================
# Test 5: Contains '/api/v1/intent/suggest'
# ===========================================================================

def test_build_audit_html_references_intent_suggest_api():
    result = build_audit_html()
    assert "/api/v1/intent/suggest" in result


# ===========================================================================
# Test 6: Contains 'Event Ledger' section heading
# ===========================================================================

def test_build_audit_html_has_event_ledger_section():
    result = build_audit_html()
    assert "Event Ledger" in result


# ===========================================================================
# Test 7: Contains 'Telemetry Spans' section heading
# ===========================================================================

def test_build_audit_html_has_telemetry_spans_section():
    result = build_audit_html()
    assert "Telemetry Spans" in result


# ===========================================================================
# Test 8: Contains 'Intent Suggestions' section heading
# ===========================================================================

def test_build_audit_html_has_intent_suggestions_section():
    result = build_audit_html()
    assert "Intent Suggestions" in result


# ===========================================================================
# Test 9: Contains auto-refresh logic
# ===========================================================================

def test_build_audit_html_has_auto_refresh():
    result = build_audit_html()
    has_interval = "setInterval" in result
    has_timeout = "setTimeout" in result
    assert has_interval or has_timeout, (
        "Expected setInterval or setTimeout for auto-refresh"
    )


# ===========================================================================
# Test 10: Idempotent — two calls return identical strings
# ===========================================================================

def test_build_audit_html_is_idempotent():
    first = build_audit_html()
    second = build_audit_html()
    assert first == second
