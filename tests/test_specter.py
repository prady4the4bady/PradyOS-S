"""SPECTER tests — fallback-first routing + checkpointed flow verified."""

from __future__ import annotations

import pytest

from pradyos.specter import Specter, SpecterError
from pradyos.specter.specter import MAX_ATTEMPTS


def _s() -> Specter:
    return Specter()


def _steps():
    return [
        {"kind": "navigate", "arg": "https://x"},
        {"kind": "login", "arg": "user"},
        {"kind": "extract", "arg": "balance"},
    ]


# ── routing ────────────────────────────────────────────────────────────────────


def test_plan_prefers_api():
    p = Specter.plan("github", has_api=True)
    assert p["mode"] == "api" and "preferred" in p["reason"]


def test_plan_falls_back_to_browser():
    p = Specter.plan("legacy-portal", has_api=False)
    assert p["mode"] == "browser" and "falling back" in p["reason"]


def test_plan_validation():
    with pytest.raises(SpecterError):
        Specter.plan("", True)
    with pytest.raises(SpecterError):
        Specter.plan("x", "yes")  # type: ignore[arg-type]


# ── flows ──────────────────────────────────────────────────────────────────────


def test_create_flow_validation():
    s = _s()
    with pytest.raises(SpecterError):
        s.create_flow("f", "t", [])
    with pytest.raises(SpecterError):
        s.create_flow("f", "t", [{"kind": "teleport"}])


def test_step_walks_to_done_with_checkpoints():
    s = _s()
    s.create_flow("f", "portal", _steps())
    m = s.step("f")
    assert m["status"] == "running" and m["checkpoint"] == 0 and m["cursor"] == 1
    s.step("f")
    m = s.step("f")  # last step
    assert m["status"] == "done" and m["checkpoint"] == 2 and m["remaining"] == 0


def test_step_past_end_raises():
    s = _s()
    s.create_flow("f", "t", [{"kind": "navigate"}])
    s.step("f")  # done
    with pytest.raises(SpecterError):
        s.step("f")


def test_extract_records_state():
    s = _s()
    s.create_flow("f", "t", _steps())
    s.step("f")
    m = s.extract("f", "balance", 4200)
    assert m["state"]["balance"] == 4200


def test_fail_step_retries_then_fails():
    s = _s()
    s.create_flow("f", "t", _steps())
    s.step("f")
    for _ in range(MAX_ATTEMPTS - 1):
        m = s.fail_step("f", "selector missing")
        assert m["status"] == "running"
    m = s.fail_step("f", "selector missing")
    assert m["status"] == "failed" and m["state"]["_failure"] == "selector missing"


def test_terminal_flow_rejects_step():
    s = _s()
    s.create_flow("f", "t", _steps())
    s.step("f")
    for _ in range(MAX_ATTEMPTS):
        try:
            s.fail_step("f")
        except SpecterError:
            break
    with pytest.raises(SpecterError):
        s.step("f")


def test_dupe_and_unknown():
    s = _s()
    s.create_flow("f", "t", _steps())
    with pytest.raises(SpecterError):
        s.create_flow("f", "t", _steps())
    with pytest.raises(SpecterError):
        s.flow("ghost")


def test_stats_and_reset():
    s = _s()
    s.create_flow("f", "t", _steps())
    s.step("f")
    st = s.stats()
    assert st["flows"] == 1 and st["by_status"]["running"] == 1
    s.reset()
    assert s.stats()["flows"] == 0 and s.flows() == []
