"""Tests for REVERIE — the idle cognition loop (reflection + curiosity).

It must reflect over the live FORESIGHT + skill signals: surface the biggest
blind spot, fall back to the weakest skill, and self-propose a curiosity goal,
without ever acting on its own.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.foresight import ForesightEngine
from pradyos.reverie import Reverie
from pradyos.skills import SkillLibrary
from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_cold_start_proposes_seeding():
    rev = Reverie(foresight=ForesightEngine(), skills=SkillLibrary())
    ins = rev.reflect()
    assert ins["focus"] == "cold_start"
    assert "Guild" in ins["curiosity_goal"]


def test_reflect_targets_biggest_blind_spot():
    fs = ForesightEngine()
    # action 'gamble' is wildly mispredicted (high surprise); 'steady' is calibrated
    for _ in range(6):
        fs.observe("game", "steady", 0.5)
    fs.observe("game", "gamble", 1.0)  # predicted ~0.5 → surprise ~0.5
    rev = Reverie(foresight=fs, skills=SkillLibrary())
    ins = rev.reflect()
    assert ins["focus"] == "blind_spot"
    assert ins["blind_spot"]["action"] == "gamble"
    assert "gamble" in ins["curiosity_goal"]


def test_reflect_falls_back_to_weakest_skill():
    fs = ForesightEngine()  # well-calibrated, no blind spot
    for _ in range(5):
        fs.observe("s", "a", 0.5)
    lib = SkillLibrary()
    lib.learn("good", "good skill", "trigger one", ["x"])
    lib.learn("bad", "bad skill", "trigger two", ["y"])
    for _ in range(3):
        lib.reinforce("good", True)
        lib.reinforce("bad", False)
    rev = Reverie(foresight=fs, skills=lib)
    ins = rev.reflect()
    assert ins["focus"] == "weak_skill"
    assert ins["weakest_skill"]["id"] == "bad"


def test_insights_are_recorded_and_capped():
    rev = Reverie(capacity=3)
    for _ in range(5):
        rev.reflect()
    assert len(rev.insights(99)) == 3
    assert rev.stats()["reflections"] == 3


# ── HTTP ─────────────────────────────────────────────────────────────────────


def test_http_reflect_and_insights():
    c = _client()
    r = c.post("/api/v1/reverie/reflect")
    assert r.status_code == 200 and "curiosity_goal" in r.json()
    ins = c.get("/api/v1/reverie/insights").json()["insights"]
    assert len(ins) >= 1


def test_http_reflect_uses_live_foresight():
    c = _client()
    # create a blind spot through the live foresight endpoint
    for _ in range(6):
        c.post("/api/v1/foresight/observe", json={"state": "g", "action": "steady", "value": 0.5})
    c.post("/api/v1/foresight/observe", json={"state": "g", "action": "wild", "value": 1.0})
    ins = c.post("/api/v1/reverie/reflect").json()
    assert ins["focus"] in ("blind_spot", "consolidate")  # depends on surprise threshold
