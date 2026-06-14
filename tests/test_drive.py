"""Tests for DRIVE (L3) — the Sovereign-gated goal/drive manager.

The gate is the headline property: a goal must be APPROVED before it can run; the
OS never acts on an unapproved goal. Plus the REVERIE→DRIVE self-direction loop.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.drive import DriveError, DriveManager
from pradyos.sovereign_web import create_app
from pradyos.web.drive_web import register_drive_routes


def _client() -> TestClient:
    return TestClient(create_app())


# ── manager core ─────────────────────────────────────────────────────────────


def test_propose_creates_proposed_goal():
    m = DriveManager()
    g = m.propose("improve caching", source="reverie")
    assert g["status"] == "proposed"
    assert g["source"] == "reverie"


def test_propose_is_idempotent_for_open_goals():
    m = DriveManager()
    a = m.propose("same goal")
    b = m.propose("same goal")
    assert a["id"] == b["id"]
    assert len(m.list()) == 1


def test_approve_then_activate_gate():
    m = DriveManager()
    g = m.propose("do it")
    # cannot activate a merely-proposed goal
    try:
        m.activate(g["id"])
        raise AssertionError("expected DriveError")
    except DriveError as exc:
        assert "approved" in str(exc)
    m.approve(g["id"])
    assert m.activate(g["id"])["status"] == "active"


def test_next_approved_returns_oldest():
    m = DriveManager()
    g1 = m.propose("first")
    m.propose("second")
    m.approve(g1["id"])
    assert m.next_approved()["id"] == g1["id"]


def test_complete_sets_result():
    m = DriveManager()
    g = m.propose("x")
    m.approve(g["id"])
    done = m.complete(g["id"], "all done")
    assert done["status"] == "done" and done["result"] == "all done"


def test_list_filter_and_stats():
    m = DriveManager()
    a = m.propose("a")
    m.propose("b")
    m.approve(a["id"])
    assert len(m.list("approved")) == 1
    assert m.stats()["by_status"]["proposed"] == 1


# ── HTTP gate ────────────────────────────────────────────────────────────────


def test_http_run_requires_approval():
    c = _client()
    g = c.post("/api/v1/drive/propose", json={"text": "ship it"}).json()
    # running an unapproved goal is rejected (the gate)
    r = c.post(f"/api/v1/drive/{g['id']}/run")
    assert r.status_code == 409


def test_http_approve_then_run_completes():
    c = _client()
    g = c.post("/api/v1/drive/propose", json={"text": "summarise the logs"}).json()
    c.post(f"/api/v1/drive/{g['id']}/approve")
    done = c.post(f"/api/v1/drive/{g['id']}/run").json()
    assert done["status"] == "done"


def test_http_run_503_without_guild_runner():
    app = FastAPI()
    mgr = register_drive_routes(app, DriveManager(), guild_runner=None)
    mgr.approve(mgr.propose("x")["id"])
    c = TestClient(app)
    gid = c.get("/api/v1/drive/goals").json()["goals"][0]["id"]
    assert c.post(f"/api/v1/drive/{gid}/run").status_code == 503


def test_http_propose_requires_text():
    assert _client().post("/api/v1/drive/propose", json={}).status_code == 422


# ── REVERIE → DRIVE self-direction loop ──────────────────────────────────────


def test_reverie_reflection_proposes_a_goal_to_drive():
    c = _client()
    before = len(c.get("/api/v1/drive/goals").json()["goals"])
    c.post("/api/v1/reverie/reflect")
    goals = c.get("/api/v1/drive/goals").json()["goals"]
    assert len(goals) >= before + 1
    assert any(g["source"] == "reverie" for g in goals)
