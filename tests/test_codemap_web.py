"""Tests for the /api/v1/codemap endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.codemap import CodeMap
from pradyos.web.codemap_web import register_codemap_routes

SRC = "from app.util import helper\nimport os\n\n\ndef run(a, b):\n    return helper(a, b)\n"


@pytest.fixture()
def client():
    app = FastAPI()
    register_codemap_routes(app, CodeMap())
    return TestClient(app)


def test_analyze_and_module(client):
    body = client.post("/api/v1/codemap/analyze", json={"module": "app.main", "source": SRC}).json()
    assert body["counts"]["functions"] == 1 and body["dependencies"] == ["app.util", "os"]
    m = client.get("/api/v1/codemap/module", params={"name": "app.main"}).json()
    assert m["functions"][0]["signature"] == "run(a, b)"


def test_analyze_missing_fields_422(client):
    assert client.post("/api/v1/codemap/analyze", json={"module": "m"}).status_code == 422


def test_analyze_syntax_error_422(client):
    r = client.post("/api/v1/codemap/analyze", json={"module": "m", "source": "def (:"})
    assert r.status_code == 422


def test_defines_and_dependencies_and_importers(client):
    client.post("/api/v1/codemap/analyze", json={"module": "app.main", "source": SRC})
    client.post(
        "/api/v1/codemap/analyze",
        json={"module": "app.util", "source": "def helper(a, b):\n    return a + b\n"},
    )
    assert (
        client.get("/api/v1/codemap/defines", params={"symbol": "run"}).json()["definitions"][0][
            "module"
        ]
        == "app.main"
    )
    deps = client.get("/api/v1/codemap/dependencies", params={"name": "app.main"}).json()
    assert deps["dependencies"] == ["app.util", "os"]
    imps = client.get("/api/v1/codemap/importers", params={"target": "app.util"}).json()
    assert imps["importers"] == ["app.main"]


def test_symbols_and_modules(client):
    client.post("/api/v1/codemap/analyze", json={"module": "app.main", "source": SRC})
    funcs = client.get("/api/v1/codemap/symbols", params={"kind": "function"}).json()
    assert [s["name"] for s in funcs["symbols"]] == ["run"]
    assert client.get("/api/v1/codemap/modules").json()["modules"] == ["app.main"]


def test_module_unknown_404(client):
    assert client.get("/api/v1/codemap/module", params={"name": "ghost"}).status_code == 404


def test_summary_and_reset(client):
    client.post("/api/v1/codemap/analyze", json={"module": "app.main", "source": SRC})
    assert client.get("/api/v1/codemap/summary").json()["modules"] == 1
    assert client.delete("/api/v1/codemap/reset").json()["modules"] == 0
