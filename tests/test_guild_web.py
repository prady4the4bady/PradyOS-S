"""Tests for the /api/v1/guild endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.guild import GuildOrg
from pradyos.web.guild_web import register_guild_routes


def _worker(role, objective, context):
    return f"{role.name}: {objective}"


@pytest.fixture()
def client():
    app = FastAPI()
    register_guild_routes(app, GuildOrg(worker=_worker))
    return TestClient(app)


def test_roles(client):
    names = [r["name"] for r in client.get("/api/v1/guild/roles").json()["roles"]]
    assert "planner" in names and "synthesizer" in names


def test_run_full_roster(client):
    body = client.post("/api/v1/guild/run", json={"objective": "build a CLI"}).json()
    assert body["status"] == "complete" and body["id"] == "proj-1"
    assert len(body["contributions"]) == 6 and "build a CLI" in body["synthesis"]


def test_run_custom_roster(client):
    body = client.post(
        "/api/v1/guild/run", json={"objective": "x", "roster": ["planner", "critic"]}
    ).json()
    assert [c["role"] for c in body["contributions"]] == ["planner", "critic"]


def test_run_missing_objective_422(client):
    assert client.post("/api/v1/guild/run", json={}).status_code == 422


def test_run_bad_roster_type_422(client):
    assert (
        client.post("/api/v1/guild/run", json={"objective": "x", "roster": "planner"}).status_code
        == 422
    )


def test_run_unknown_role_422(client):
    resp = client.post("/api/v1/guild/run", json={"objective": "x", "roster": ["wizard"]})
    assert resp.status_code == 422


def test_project_roundtrip_and_unknown(client):
    client.post("/api/v1/guild/run", json={"objective": "x"})
    assert client.get("/api/v1/guild/project", params={"id": "proj-1"}).json()["id"] == "proj-1"
    assert client.get("/api/v1/guild/project", params={"id": "proj-9"}).status_code == 404


def test_projects_and_stats_and_reset(client):
    client.post("/api/v1/guild/run", json={"objective": "x"})
    assert len(client.get("/api/v1/guild/projects").json()["projects"]) == 1
    assert client.get("/api/v1/guild/stats").json()["worker_configured"] is True
    assert client.delete("/api/v1/guild/reset").json()["projects"] == 0
