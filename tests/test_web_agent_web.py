"""Phase 46D — 10 tests for WebAgent endpoints in sovereign_web."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.web_agent import WebAgent, WebResult
from pradyos.sovereign_web import create_app


class _StubAgent:
    """Minimal stub matching the WebAgent surface used by the web layer."""
    def __init__(self) -> None:
        self.fetch_calls: list[str] = []
        self.search_calls: list[tuple[str, int]] = []

    def status(self) -> dict:
        return {"cache_enabled": False, "guardrail_enabled": False,
                "max_age": 60, "timeout": 5}

    def fetch(self, url: str) -> WebResult:
        self.fetch_calls.append(url)
        return WebResult(
            url=url, status_code=200, body_text="ok",
            content_type="text/plain", fetched_at=time.time(), error="",
        )

    def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        self.search_calls.append((query, max_results))
        return [WebResult(
            url=f"http://result/{query}",
            status_code=200, body_text="hit",
            content_type="text/html",
            fetched_at=time.time(), error="",
        )]


@pytest.fixture()
def client_no_agent():
    return TestClient(create_app())


@pytest.fixture()
def client_with_agent():
    agent = _StubAgent()
    app = create_app(web_agent=agent)
    return TestClient(app), agent


# ── status ────────────────────────────────────────────────────────────────────

def test_get_status_returns_200(client_no_agent):
    assert client_no_agent.get("/api/v1/web/status").status_code == 200


def test_status_has_required_keys(client_with_agent):
    client, _ = client_with_agent
    data = client.get("/api/v1/web/status").json()
    for k in ("cache_enabled", "guardrail_enabled", "max_age", "timeout"):
        assert k in data


def test_status_no_agent_returns_defaults(client_no_agent):
    resp = client_no_agent.get("/api/v1/web/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cache_enabled"] is False
    assert data["guardrail_enabled"] is False


# ── fetch ─────────────────────────────────────────────────────────────────────

def test_fetch_no_url_param_returns_422(client_with_agent):
    client, _ = client_with_agent
    resp = client.get("/api/v1/web/fetch")
    assert resp.status_code == 422


def test_fetch_no_agent_returns_400(client_no_agent):
    resp = client_no_agent.get("/api/v1/web/fetch?url=http://x")
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_fetch_with_agent_returns_webresult_fields(client_with_agent):
    client, _ = client_with_agent
    data = client.get("/api/v1/web/fetch?url=http://example.com").json()
    for k in ("url", "status_code", "body_text", "content_type", "fetched_at", "error"):
        assert k in data


# ── search ────────────────────────────────────────────────────────────────────

def test_search_no_agent_returns_400(client_no_agent):
    resp = client_no_agent.post("/api/v1/web/search", json={"query": "x"})
    assert resp.status_code == 400


def test_search_missing_query_returns_400(client_with_agent):
    client, _ = client_with_agent
    resp = client.post("/api/v1/web/search", json={})
    assert resp.status_code == 400


def test_search_with_agent_returns_results_key(client_with_agent):
    client, _ = client_with_agent
    data = client.post("/api/v1/web/search", json={"query": "python"}).json()
    assert "results" in data


def test_search_results_is_list(client_with_agent):
    client, _ = client_with_agent
    data = client.post("/api/v1/web/search", json={"query": "python"}).json()
    assert isinstance(data["results"], list)
