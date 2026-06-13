"""Tests for the /api/v1/ascent endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.ascent import AscentLoop
from pradyos.web.ascent_web import register_ascent_routes

WEAK = "def f():\n    try:\n        g()\n    except:\n        pass\n"
CLEAN = "x = 1\n"


class _FakeEvolve:
    def propose(self, path: str, directive: str, before: str = "") -> dict:
        return {
            "path": path,
            "directive": directive,
            "proposed": True,
            "after": "x = 1\n",
            "evaluation": {"verdict": "promote", "risk_before": 3, "risk_after": 1, "path": path},
            "note": "verdict=promote",
        }

    def stats(self) -> dict:
        return {"proposer_configured": True}


@pytest.fixture()
def client():
    app = FastAPI()
    register_ascent_routes(app, AscentLoop(evolve=_FakeEvolve()))
    return TestClient(app)


@pytest.fixture()
def bare_client():
    """No EVOLVE wired — survey/direct only."""
    app = FastAPI()
    register_ascent_routes(app, AscentLoop())
    return TestClient(app)


def test_survey_ranks(bare_client):
    body = bare_client.post(
        "/api/v1/ascent/survey", json={"candidates": {"a.py": WEAK, "c.py": CLEAN}}
    ).json()
    assert [e["module"] for e in body["survey"]] == ["a.py", "c.py"]


def test_survey_requires_candidates(bare_client):
    assert bare_client.post("/api/v1/ascent/survey", json={}).status_code == 422


def test_survey_invalid_candidates_422(bare_client):
    assert bare_client.post("/api/v1/ascent/survey", json={"candidates": {}}).status_code == 422


def test_cycle_promote_applies_and_queues(client):
    body = client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}}).json()
    assert len(body["cycles"]) == 1
    assert body["cycles"][0]["verdict"] == "promote"
    assert body["cycles"][0]["decision"] == "apply"
    pend = client.get("/api/v1/ascent/pending").json()["pending"]
    assert len(pend) == 1 and pend[0]["module"] == "a.py"


def test_cycle_no_evolve_skips(bare_client):
    body = bare_client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}}).json()
    assert body["cycles"][0]["decision"] == "skipped"


def test_cycle_requires_candidates(client):
    assert client.post("/api/v1/ascent/cycle", json={}).status_code == 422


def test_cycle_bad_max_targets_422(client):
    resp = client.post(
        "/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}, "max_targets": 0}
    )
    assert resp.status_code == 422


def test_cycle_get_roundtrip_and_unknown(client):
    client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}})
    assert client.get("/api/v1/ascent/cycle", params={"seq": 1}).json()["seq"] == 1
    assert client.get("/api/v1/ascent/cycle", params={"seq": 99}).status_code == 404


def test_cycles_list_and_stats(client):
    client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}})
    assert len(client.get("/api/v1/ascent/cycles").json()["cycles"]) == 1
    stats = client.get("/api/v1/ascent/stats").json()
    assert stats["cycles"] == 1 and stats["evolve_wired"] is True


def test_reset_clears(client):
    client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}})
    stats = client.delete("/api/v1/ascent/reset").json()
    assert stats["cycles"] == 0 and stats["pending"] == 0


# ── Sovereign review surface ────────────────────────────────────────────────────


def test_queue_resolve_decisions_flow(client):
    client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}})
    queue = client.get("/api/v1/ascent/queue").json()["queue"]
    assert len(queue) == 1
    seq = queue[0]["seq"]
    rec = client.post("/api/v1/ascent/resolve", json={"seq": seq, "decision": "approve"}).json()
    assert rec["status"] == "approved"
    assert client.get("/api/v1/ascent/queue").json()["queue"] == []  # dequeued
    assert client.get("/api/v1/ascent/decisions").json()["decisions"][-1]["seq"] == seq


def test_resolve_missing_fields_422(client):
    assert client.post("/api/v1/ascent/resolve", json={"seq": 1}).status_code == 422


def test_resolve_unknown_seq_404(client):
    resp = client.post("/api/v1/ascent/resolve", json={"seq": 999, "decision": "approve"})
    assert resp.status_code == 404


def test_resolve_bad_decision_422(client):
    client.post("/api/v1/ascent/cycle", json={"candidates": {"a.py": WEAK}})
    seq = client.get("/api/v1/ascent/queue").json()["queue"][0]["seq"]
    resp = client.post("/api/v1/ascent/resolve", json={"seq": seq, "decision": "applied"})
    assert resp.status_code == 422
