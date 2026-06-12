"""SKILL LIBRARY tests — learn / match / reinforce / prune verified deterministically."""

from __future__ import annotations

import pytest

from pradyos.skills import SkillError, SkillLibrary


def _lib() -> SkillLibrary:
    return SkillLibrary()


# ── learn / recall ────────────────────────────────────────────────────────────


def test_learn_and_recall():
    lib = _lib()
    d = lib.learn("s1", "Deploy web", "deploy web service", ["build", "ship"])
    assert d["id"] == "s1" and d["trigger"] == ["deploy", "service", "web"]
    assert d["steps"] == ["build", "ship"] and d["version"] == 1
    assert d["confidence"] == 0.5  # (0+1)/(0+2), no evidence yet
    assert lib.recall("s1")["name"] == "Deploy web"


def test_learn_trigger_as_keyword_list():
    lib = _lib()
    d = lib.learn("s", "x", ["Deploy", "Web"], ["go"])
    assert d["trigger"] == ["deploy", "web"]


def test_learn_validation():
    lib = _lib()
    with pytest.raises(SkillError):
        lib.learn("", "n", "t word", ["s"])
    with pytest.raises(SkillError):
        lib.learn("s", "", "t word", ["s"])
    with pytest.raises(SkillError):
        lib.learn("s", "n", "", ["s"])  # empty trigger
    with pytest.raises(SkillError):
        lib.learn("s", "n", "trig", [])  # empty steps
    with pytest.raises(SkillError):
        lib.learn("s", "n", "trig", "not a list")
    with pytest.raises(SkillError):
        lib.learn("s", "n", "trig", ["ok"], preconditions="nope")


def test_learn_duplicate_raises():
    lib = _lib()
    lib.learn("s", "n", "trig word", ["s"])
    with pytest.raises(SkillError):
        lib.learn("s", "n2", "trig word", ["s2"])


# ── reinforce (confidence evolves) ────────────────────────────────────────────


def test_reinforce_updates_confidence():
    lib = _lib()
    lib.learn("s", "n", "trig word", ["s"])
    for _ in range(3):
        lib.reinforce("s", True, example="task-1")
    d = lib.recall("s")
    assert d["success"] == 3 and d["failure"] == 0
    assert d["confidence"] == 0.8  # (3+1)/(3+2)
    assert d["examples"] == ["task-1"]  # de-duplicated


def test_reinforce_failure_lowers_confidence():
    lib = _lib()
    lib.learn("s", "n", "trig word", ["s"])
    lib.reinforce("s", False)
    lib.reinforce("s", False)
    lib.reinforce("s", False)
    assert lib.recall("s")["confidence"] == 0.2  # (0+1)/(3+2)


def test_reinforce_validation():
    lib = _lib()
    lib.learn("s", "n", "trig word", ["s"])
    with pytest.raises(SkillError):
        lib.reinforce("s", "yes")  # not a bool
    with pytest.raises(SkillError):
        lib.reinforce("ghost", True)


# ── match (overlap × confidence) ──────────────────────────────────────────────


def test_match_ranks_by_overlap():
    lib = _lib()
    lib.learn("a", "A", "deploy web", ["x"])
    lib.learn("b", "B", "deploy database", ["x"])
    lib.learn("c", "C", "cook pasta", ["x"])
    out = lib.match("deploy the web service")
    assert [s["id"] for s in out] == ["a", "b"]  # c has zero overlap, excluded
    assert out[0]["match_overlap"] == 2 and out[1]["match_overlap"] == 1


def test_match_tiebreak_by_confidence():
    lib = _lib()
    lib.learn("x", "X", "alpha beta", ["s"])
    lib.learn("y", "Y", "alpha beta", ["s"])
    for _ in range(3):
        lib.reinforce("x", True)  # conf 0.8
        lib.reinforce("y", False)  # conf 0.2
    out = lib.match("alpha beta")
    assert [s["id"] for s in out] == ["x", "y"]  # equal overlap, higher confidence first


def test_match_limit_and_validation():
    lib = _lib()
    lib.learn("a", "A", "deploy web", ["x"])
    lib.learn("b", "B", "deploy api", ["x"])
    assert len(lib.match("deploy", limit=1)) == 1
    with pytest.raises(SkillError):
        lib.match("")
    with pytest.raises(SkillError):
        lib.match("deploy", limit=0)


def test_match_no_overlap_returns_empty():
    lib = _lib()
    lib.learn("a", "A", "deploy web", ["x"])
    assert lib.match("bake a cake") == []


# ── prune (self-healing) ──────────────────────────────────────────────────────


def test_prune_retires_failing_skills():
    lib = _lib()
    lib.learn("good", "G", "trig word", ["s"])
    lib.learn("bad", "B", "trig word", ["s"])
    lib.learn("untested", "U", "trig word", ["s"])
    for _ in range(3):
        lib.reinforce("good", True)  # conf 0.8 — keep
        lib.reinforce("bad", False)  # conf 0.2 — prune
    # 'untested' has 0 attempts → below min_attempts → kept regardless
    pruned = lib.prune(min_confidence=0.34, min_attempts=3)
    assert pruned == ["bad"]
    assert {s["id"] for s in lib.skills()} == {"good", "untested"}


def test_prune_validation():
    with pytest.raises(SkillError):
        _lib().prune(min_attempts=0)


# ── revise / list / stats / reset ─────────────────────────────────────────────


def test_revise_bumps_version():
    lib = _lib()
    lib.learn("s", "n", "trig word", ["old"])
    d = lib.revise("s", ["new", "better"])
    assert d["steps"] == ["new", "better"] and d["version"] == 2


def test_skills_listed_in_learn_order():
    lib = _lib()
    lib.learn("first", "1", "trig word", ["s"])
    lib.learn("second", "2", "trig word", ["s"])
    assert [s["id"] for s in lib.skills()] == ["first", "second"]


def test_stats_and_reset():
    lib = _lib()
    lib.learn("a", "A", "trig word", ["s"])
    lib.learn("b", "B", "trig word", ["s"])
    lib.reinforce("a", True)
    s = lib.stats()
    assert s["skills"] == 2 and s["proven"] == 1 and s["total_attempts"] == 1
    lib.reset()
    assert lib.stats() == {"skills": 0, "proven": 0, "total_attempts": 0}


def test_recall_unknown_raises():
    with pytest.raises(SkillError):
        _lib().recall("ghost")
