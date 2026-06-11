"""Agent 7 — tests for the /api/v1/chronicle endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_record_and_entries(client):
    client.post("/api/v1/chronicle/record", json={"type": "deployment", "title": "v1"})
    client.post("/api/v1/chronicle/record", json={"type": "changelog", "title": "added X"})
    deploys = client.get("/api/v1/chronicle/entries", params={"type": "deployment"}).json()[
        "entries"
    ]
    assert len(deploys) == 1 and deploys[0]["title"] == "v1"


def test_record_missing_422(client):
    assert client.post("/api/v1/chronicle/record", json={"type": "doc"}).status_code == 422


def test_record_bad_type_422(client):
    assert (
        client.post("/api/v1/chronicle/record", json={"type": "rumor", "title": "x"}).status_code
        == 422
    )


def test_entries_by_tag(client):
    client.post(
        "/api/v1/chronicle/record",
        json={"type": "incident", "title": "outage", "tags": ["network"]},
    )
    sel = client.get("/api/v1/chronicle/entries", params={"tag": "network"}).json()["entries"]
    assert len(sel) == 1 and sel[0]["title"] == "outage"


def test_latest(client):
    client.post("/api/v1/chronicle/record", json={"type": "changelog", "title": "a"})
    client.post("/api/v1/chronicle/record", json={"type": "changelog", "title": "b"})
    assert client.get("/api/v1/chronicle/latest").json()["latest"]["title"] == "b"


def test_digest(client):
    client.post("/api/v1/chronicle/record", json={"type": "deployment", "title": "d1"})
    client.post("/api/v1/chronicle/record", json={"type": "post_mortem", "title": "p1"})
    d = client.get("/api/v1/chronicle/digest").json()
    assert d["total"] == 2 and d["by_type"]["deployment"] == 1


def test_stats_and_reset(client):
    client.post("/api/v1/chronicle/record", json={"type": "doc", "title": "readme"})
    assert client.get("/api/v1/chronicle/stats").json()["entries"] == 1
    after = client.delete("/api/v1/chronicle/reset").json()
    assert after["entries"] == 0
