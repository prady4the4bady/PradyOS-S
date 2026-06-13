"""Tests for the /api/v1/evolve endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.evolve import EvolveEngine
from pradyos.web.evolve_web import register_evolve_routes

_WEAK = "def f():\n    try:\n        g()\n    except:\n        pass\n"
_FIXED = "def f():\n    try:\n        g()\n    except ValueError:\n        log()\n"


@pytest.fixture()
def client():
    app = FastAPI()
    register_evolve_routes(app, EvolveEngine())
    return TestClient(app)


def test_evaluate_promote(client):
    body = client.post(
        "/api/v1/evolve/evaluate", json={"path": "pradyos/x.py", "before": _WEAK, "after": _FIXED}
    ).json()
    assert body["verdict"] == "promote" and body["risk_delta"] == -3 and body["seq"] == 1


def test_evaluate_reject(client):
    body = client.post(
        "/api/v1/evolve/evaluate",
        json={
            "path": "pradyos/x.py",
            "before": "def a():\n    pass\n\n\ndef b():\n    pass\n",
            "after": "def a():\n    pass\n",
        },
    ).json()
    assert body["verdict"] == "reject"


def test_evaluate_escalate(client):
    body = client.post(
        "/api/v1/evolve/evaluate", json={"path": "pradyos/core/constitution.py", "after": "x = 2\n"}
    ).json()
    assert body["verdict"] == "escalate"


def test_evaluate_missing_fields_422(client):
    assert client.post("/api/v1/evolve/evaluate", json={"path": "p"}).status_code == 422


def test_evaluate_after_not_string_422(client):
    assert client.post("/api/v1/evolve/evaluate", json={"path": "p", "after": 5}).status_code == 422


def test_evaluation_roundtrip_and_unknown(client):
    client.post("/api/v1/evolve/evaluate", json={"path": "pradyos/a.py", "after": "x = 1\n"})
    assert client.get("/api/v1/evolve/evaluation", params={"seq": 1}).json()["seq"] == 1
    assert client.get("/api/v1/evolve/evaluation", params={"seq": 99}).status_code == 404


def test_stats_and_reset(client):
    client.post("/api/v1/evolve/evaluate", json={"path": "pradyos/a.py", "after": "x = 1\n"})
    assert client.get("/api/v1/evolve/stats").json()["evaluations"] == 1
    assert client.delete("/api/v1/evolve/reset").json()["evaluations"] == 0


def test_propose_route_with_proposer():
    app = FastAPI()
    register_evolve_routes(app, EvolveEngine(proposer=lambda b, d: "def f():\n    return 1\n"))
    body = TestClient(app).post(
        "/api/v1/evolve/propose",
        json={"path": "pradyos/x.py", "directive": "improve", "before": "def f():\n    return 0\n"},
    ).json()
    assert body["proposed"] is True and body["evaluation"]["verdict"] == "promote"


def test_propose_missing_fields_422(client):
    assert client.post("/api/v1/evolve/propose", json={"path": "p"}).status_code == 422


def test_propose_without_proposer_graceful(client):
    body = client.post(
        "/api/v1/evolve/propose", json={"path": "pradyos/x.py", "directive": "improve"}
    ).json()
    assert body["proposed"] is False
