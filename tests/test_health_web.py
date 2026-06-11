"""Phase 24D — 10 tests for /api/v1/health/score and /api/v1/health/update."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.health_scorecard import HealthScorecard
from pradyos.sovereign_web import create_app


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client_no_scorecard():
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def scorecard():
    return HealthScorecard()


@pytest.fixture()
def client_with_scorecard(scorecard):
    app = create_app(scorecard=scorecard)
    return TestClient(app, raise_server_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_health_score_returns_200(client_with_scorecard):
    r = client_with_scorecard.get("/api/v1/health/score")
    assert r.status_code == 200


def test_get_health_score_has_required_keys(client_with_scorecard):
    r = client_with_scorecard.get("/api/v1/health/score")
    data = r.json()
    for key in ("score", "grade", "components", "timestamp"):
        assert key in data, f"Missing key: {key}"


def test_default_score_no_scorecard(client_no_scorecard):
    r = client_no_scorecard.get("/api/v1/health/score")
    assert r.json()["score"] == 100.0


def test_post_health_update_returns_200(client_with_scorecard):
    r = client_with_scorecard.post(
        "/api/v1/health/update", json={"name": "cpu", "score": 80.0}
    )
    assert r.status_code == 200


def test_post_health_update_has_updated_key(client_with_scorecard):
    r = client_with_scorecard.post(
        "/api/v1/health/update", json={"name": "cpu", "score": 80.0}
    )
    assert "updated" in r.json()


def test_post_update_no_scorecard_returns_updated_false(client_no_scorecard):
    r = client_no_scorecard.post(
        "/api/v1/health/update", json={"name": "cpu", "score": 80.0}
    )
    assert r.json()["updated"] is False


def test_get_score_no_scorecard_returns_100(client_no_scorecard):
    r = client_no_scorecard.get("/api/v1/health/score")
    assert r.json()["score"] == 100.0


def test_update_then_get_reflects_component(client_with_scorecard):
    client_with_scorecard.post(
        "/api/v1/health/update", json={"name": "disk", "score": 70.0}
    )
    r = client_with_scorecard.get("/api/v1/health/score")
    data = r.json()
    names = [c["name"] for c in data["components"]]
    assert "disk" in names


def test_grade_A_after_update_95(client_with_scorecard):
    client_with_scorecard.post(
        "/api/v1/health/update", json={"name": "perf", "score": 95.0}
    )
    r = client_with_scorecard.get("/api/v1/health/score")
    assert r.json()["grade"] == "A"


def test_grade_F_after_update_20(client_with_scorecard):
    client_with_scorecard.post(
        "/api/v1/health/update", json={"name": "perf", "score": 20.0}
    )
    r = client_with_scorecard.get("/api/v1/health/score")
    assert r.json()["grade"] == "F"
