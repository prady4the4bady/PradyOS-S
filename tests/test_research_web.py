"""Tests for the /api/v1/research endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.research import ResearchEngine, SourceDoc
from pradyos.sovereign_web import create_app
from pradyos.web.research_web import register_research_routes


class FakeSource:
    name = "web"

    def search(self, query, limit):
        return [
            SourceDoc(
                url="https://docs.example.com/async",
                title="python async web frameworks",
                snippet="fastapi and aiohttp are async python web frameworks",
                content="FastAPI is an async python web framework. It is fast.",
                source="web",
            ),
            SourceDoc(
                url="https://blog.example.org/django",
                title="django overview",
                snippet="django is a python web framework",
                source="web",
            ),
        ][:limit]


@pytest.fixture()
def client():
    app = FastAPI()
    register_research_routes(app, ResearchEngine(sources=[FakeSource()]))
    return TestClient(app)


def test_run_returns_ranked_brief(client):
    body = client.post(
        "/api/v1/research/run", json={"question": "python async web frameworks", "angles": []}
    ).json()
    assert body["question"] == "python async web frameworks"
    assert body["findings"][0]["url"] == "https://docs.example.com/async"
    assert body["sources_consulted"] == ["web"]
    assert body["finding_count"] == 2


def test_run_missing_question_422(client):
    assert client.post("/api/v1/research/run", json={}).status_code == 422


def test_run_bad_providers_422(client):
    r = client.post("/api/v1/research/run", json={"question": "q", "providers": "web"})
    assert r.status_code == 422


def test_run_unknown_provider_404(client):
    r = client.post("/api/v1/research/run", json={"question": "q", "providers": ["ghost"]})
    assert r.status_code == 404


def test_plan_returns_queries(client):
    body = client.post(
        "/api/v1/research/plan", json={"question": "topic", "angles": ["a", "b"]}
    ).json()
    assert body["queries"] == ["topic", "topic a", "topic b"]


def test_brief_roundtrip_and_unknown(client):
    client.post("/api/v1/research/run", json={"question": "python", "angles": []})
    assert client.get("/api/v1/research/brief", params={"seq": 1}).json()["seq"] == 1
    assert client.get("/api/v1/research/brief", params={"seq": 99}).status_code == 404


def test_briefs_and_sources(client):
    client.post("/api/v1/research/run", json={"question": "python", "angles": []})
    assert len(client.get("/api/v1/research/briefs").json()["briefs"]) == 1
    assert client.get("/api/v1/research/sources").json()["sources"] == ["web"]


def test_stats_and_reset(client):
    client.post("/api/v1/research/run", json={"question": "python", "angles": []})
    assert client.get("/api/v1/research/stats").json()["briefs"] == 1
    after = client.delete("/api/v1/research/reset").json()
    assert after["briefs"] == 0


def test_wired_into_create_app_default_is_io_free():
    # The default factory engine has no live sources, so this never touches the
    # network: it returns a well-formed empty brief noting that.
    c = TestClient(create_app())
    assert c.get("/api/v1/research/stats").json() == {
        "sources": [],
        "briefs": 0,
        "max_results_per_query": 5,
    }
    brief = c.post("/api/v1/research/run", json={"question": "what is rust", "angles": []}).json()
    assert brief["findings"] == [] and brief["confidence"] == "low"
    assert any("no research sources" in n for n in brief["notes"])
