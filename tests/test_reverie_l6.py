"""Tests for REVERIE L6 — the LLM reflector + memory consolidation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.foresight import ForesightEngine
from pradyos.reverie import Reverie
from pradyos.reverie.llm_reflector import make_llm_reflector
from pradyos.skills import SkillLibrary
from pradyos.sovereign_web import create_app


class _FakeProvider:
    name = "fake"

    def __init__(self, out: str = "", boom: bool = False) -> None:
        self.out = out
        self.boom = boom

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        if self.boom:
            raise RuntimeError("down")
        return self.out


# ── reflector ────────────────────────────────────────────────────────────────


def test_reflector_overrides_heuristic_goal():
    rev = Reverie(reflector=lambda ctx: "Probe the cache eviction policy")
    ins = rev.reflect()
    assert ins["curiosity_goal"] == "Probe the cache eviction policy"
    assert ins["source"] == "llm"


def test_reflector_none_falls_back_to_heuristic():
    rev = Reverie(reflector=lambda ctx: None)
    ins = rev.reflect()
    assert ins["source"] == "heuristic"
    assert ins["curiosity_goal"]


def test_reflector_exception_falls_back():
    def _boom(ctx):  # noqa: ANN001, ARG001
        raise RuntimeError("nope")

    ins = Reverie(reflector=_boom).reflect()
    assert ins["source"] == "heuristic"


def test_make_llm_reflector_parses_and_failsoft():
    good = make_llm_reflector(_FakeProvider('"Investigate the slow path"'))
    assert good({"focus": "x"}) == "Investigate the slow path"
    assert make_llm_reflector(_FakeProvider(boom=True))({"focus": "x"}) is None
    assert make_llm_reflector(_FakeProvider("   "))({"focus": "x"}) is None


# ── consolidation ────────────────────────────────────────────────────────────


def test_consolidate_empty():
    assert Reverie().consolidate()["status"] == "empty"


def test_consolidate_finds_dominant_focus():
    # a blind spot persists → 'blind_spot' should dominate
    fs = ForesightEngine()
    for _ in range(6):
        fs.observe("g", "steady", 0.5)
    fs.observe("g", "wild", 1.0)
    rev = Reverie(foresight=fs, skills=SkillLibrary())
    for _ in range(4):
        rev.reflect()
    con = rev.consolidate()
    assert con["status"] == "ok"
    assert con["dominant_focus"] == "blind_spot"
    assert con["standing_directive"]


def test_http_consolidate():
    c = TestClient(create_app())
    c.post("/api/v1/reverie/reflect")
    assert c.get("/api/v1/reverie/consolidate").json()["status"] in ("ok", "empty")
