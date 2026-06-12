"""Tests for the /api/v1/fortify endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.fortify import FortifyEngine
from pradyos.web.fortify_web import register_fortify_routes

WEAK = "def f(items=[]):\n    try:\n        x()\n    except:\n        pass\n"


@pytest.fixture()
def client():
    app = FastAPI()
    register_fortify_routes(app, FortifyEngine())
    return TestClient(app)


def test_audit_returns_report(client):
    body = client.post("/api/v1/fortify/audit", json={"module": "demo", "source": WEAK}).json()
    rules = {f["rule"] for f in body["findings"]}
    assert "mutable_default" in rules and "bare_except" in rules
    assert body["risk"] >= 6


def test_audit_missing_fields_422(client):
    assert client.post("/api/v1/fortify/audit", json={"module": "m"}).status_code == 422


def test_audit_source_not_string_422(client):
    assert (
        client.post("/api/v1/fortify/audit", json={"module": "m", "source": 5}).status_code == 422
    )


def test_report_roundtrip_and_unknown(client):
    client.post("/api/v1/fortify/audit", json={"module": "demo", "source": WEAK})
    assert (
        client.get("/api/v1/fortify/report", params={"module": "demo"}).json()["module"] == "demo"
    )
    assert client.get("/api/v1/fortify/report", params={"module": "ghost"}).status_code == 404


def test_rules_and_reports(client):
    client.post("/api/v1/fortify/audit", json={"module": "demo", "source": WEAK})
    assert "bare_except" in client.get("/api/v1/fortify/rules").json()["rules"]
    assert len(client.get("/api/v1/fortify/reports").json()["reports"]) == 1


def test_stats_and_reset(client):
    client.post("/api/v1/fortify/audit", json={"module": "demo", "source": WEAK})
    assert client.get("/api/v1/fortify/stats").json()["modules"] == 1
    assert client.delete("/api/v1/fortify/reset").json()["modules"] == 0
