"""Phase 21D — Config Hot-Reload web endpoint tests (10 tests).

FastAPI TestClient for:
  GET  /api/v1/config/status
  POST /api/v1/config/reload

Covers:
  1.  GET /api/v1/config/status returns 200
  2.  Status response has "running", "config_path", "last_reload", "poll_interval" keys
  3.  POST /api/v1/config/reload returns 200
  4.  Reload response has "success", "timestamp", "changes", "error" keys
  5.  POST reload with valid reloader calls load() and returns success
  6.  No reloader injected → GET status returns running=False
  7.  No reloader injected → POST reload returns success=False
  8.  POST reload error field is None on success
  9.  GET status config_path matches reloader's config_path
 10.  POST reload changes is a list
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pradyos.core.config_hot_reload import ConfigHotReloader, ReloadResult
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _client_no_reloader() -> TestClient:
    """App with no config_reloader injected."""
    return TestClient(create_app())


def _client_with_reloader(cfg_path: Path) -> tuple[TestClient, ConfigHotReloader]:
    """App with a real ConfigHotReloader injected (no external components)."""
    reloader = ConfigHotReloader(cfg_path)
    app = create_app(config_reloader=reloader)
    return TestClient(app), reloader


# ===========================================================================
# Test 1: GET /api/v1/config/status returns 200
# ===========================================================================

def test_get_config_status_returns_200():
    client = _client_no_reloader()
    resp = client.get("/api/v1/config/status")
    assert resp.status_code == 200


# ===========================================================================
# Test 2: Status response has required keys
# ===========================================================================

def test_get_config_status_has_required_keys():
    client = _client_no_reloader()
    resp = client.get("/api/v1/config/status")
    data = resp.json()
    for key in ("running", "config_path", "last_reload", "poll_interval"):
        assert key in data, f"missing key: {key}"


# ===========================================================================
# Test 3: POST /api/v1/config/reload returns 200
# ===========================================================================

def test_post_config_reload_returns_200():
    client = _client_no_reloader()
    resp = client.post("/api/v1/config/reload")
    assert resp.status_code == 200


# ===========================================================================
# Test 4: Reload response has required keys
# ===========================================================================

def test_post_config_reload_has_required_keys():
    client = _client_no_reloader()
    resp = client.post("/api/v1/config/reload")
    data = resp.json()
    for key in ("success", "timestamp", "changes", "error"):
        assert key in data, f"missing key: {key}"


# ===========================================================================
# Test 5: POST reload with valid reloader calls load() and returns success
# ===========================================================================

def test_post_reload_with_valid_reloader_returns_success():
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "config.json"
        _write_json(cfg, {})
        client, _ = _client_with_reloader(cfg)
        resp = client.post("/api/v1/config/reload")
        data = resp.json()
        assert data["success"] is True


# ===========================================================================
# Test 6: No reloader injected → GET status returns running=False
# ===========================================================================

def test_get_status_no_reloader_running_false():
    client = _client_no_reloader()
    data = client.get("/api/v1/config/status").json()
    assert data["running"] is False


# ===========================================================================
# Test 7: No reloader injected → POST reload returns success=False
# ===========================================================================

def test_post_reload_no_reloader_success_false():
    client = _client_no_reloader()
    data = client.post("/api/v1/config/reload").json()
    assert data["success"] is False


# ===========================================================================
# Test 8: POST reload error field is None on success
# ===========================================================================

def test_post_reload_error_none_on_success():
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "config.json"
        _write_json(cfg, {})
        client, _ = _client_with_reloader(cfg)
        data = client.post("/api/v1/config/reload").json()
        assert data["error"] is None


# ===========================================================================
# Test 9: GET status config_path matches reloader's config_path
# ===========================================================================

def test_get_status_config_path_matches_reloader():
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "config.json"
        _write_json(cfg, {})
        client, reloader = _client_with_reloader(cfg)
        data = client.get("/api/v1/config/status").json()
        assert data["config_path"] == str(reloader._config_path)


# ===========================================================================
# Test 10: POST reload changes is a list
# ===========================================================================

def test_post_reload_changes_is_list():
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "config.json"
        _write_json(cfg, {})
        client, _ = _client_with_reloader(cfg)
        data = client.post("/api/v1/config/reload").json()
        assert isinstance(data["changes"], list)
