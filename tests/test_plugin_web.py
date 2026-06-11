"""
tests/test_plugin_web.py
Phase 26 — 10 FastAPI TestClient tests for /api/v1/plugins endpoints.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app
from pradyos.core.plugin_sandbox import PluginSandbox

VALID_PLUGIN_SRC = textwrap.dedent("""\
    PLUGIN_MANIFEST = {"name": "web_test_plugin", "version": "1.0", "hooks": ["on_start"]}
    def on_start(): pass
""")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_no_sandbox() -> TestClient:
    """TestClient with no plugin_sandbox injected."""
    return TestClient(create_app())


@pytest.fixture()
def client_with_sandbox(tmp_path: Path) -> TestClient:
    """TestClient with a real PluginSandbox pointed at tmp_path."""
    (tmp_path / "web_test_plugin.py").write_text(VALID_PLUGIN_SRC, encoding="utf-8")
    sandbox = PluginSandbox(tmp_path)
    sandbox.reload_all()
    return TestClient(create_app(plugin_sandbox=sandbox))


# ---------------------------------------------------------------------------
# GET /api/v1/plugins — basic
# ---------------------------------------------------------------------------

def test_get_plugins_returns_200(client_no_sandbox: TestClient) -> None:
    r = client_no_sandbox.get("/api/v1/plugins")
    assert r.status_code == 200


def test_get_plugins_response_has_plugins_and_status_keys(client_no_sandbox: TestClient) -> None:
    body = client_no_sandbox.get("/api/v1/plugins").json()
    assert "plugins" in body
    assert "status" in body


def test_get_plugins_no_sandbox_plugins_is_empty_list(client_no_sandbox: TestClient) -> None:
    body = client_no_sandbox.get("/api/v1/plugins").json()
    assert body["plugins"] == []


def test_get_plugins_no_sandbox_status_is_empty_dict(client_no_sandbox: TestClient) -> None:
    body = client_no_sandbox.get("/api/v1/plugins").json()
    assert body["status"] == {}


# ---------------------------------------------------------------------------
# POST /api/v1/plugins/reload — basic
# ---------------------------------------------------------------------------

def test_post_reload_returns_200(client_no_sandbox: TestClient) -> None:
    r = client_no_sandbox.post("/api/v1/plugins/reload")
    assert r.status_code == 200


def test_post_reload_response_has_reloaded_and_plugins_keys(client_no_sandbox: TestClient) -> None:
    body = client_no_sandbox.post("/api/v1/plugins/reload").json()
    assert "reloaded" in body
    assert "plugins" in body


def test_post_reload_no_sandbox_reloaded_is_zero(client_no_sandbox: TestClient) -> None:
    body = client_no_sandbox.post("/api/v1/plugins/reload").json()
    assert body["reloaded"] == 0


# ---------------------------------------------------------------------------
# With a real PluginSandbox
# ---------------------------------------------------------------------------

def test_get_plugins_with_sandbox_returns_list(client_with_sandbox: TestClient) -> None:
    body = client_with_sandbox.get("/api/v1/plugins").json()
    assert isinstance(body["plugins"], list)
    assert len(body["plugins"]) >= 1


def test_post_reload_with_sandbox_reloaded_gte_zero(client_with_sandbox: TestClient) -> None:
    body = client_with_sandbox.post("/api/v1/plugins/reload").json()
    assert body["reloaded"] >= 0


def test_plugins_field_is_list_type(client_with_sandbox: TestClient) -> None:
    body = client_with_sandbox.get("/api/v1/plugins").json()
    assert isinstance(body["plugins"], list)
