"""Phase 45C — 20 tests for pradyos.core.reasoning_engine.ReasoningEngine."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.reasoning_engine import (
    ReasoningEngine,
    ReasoningPlan,
    ReasoningStep,
)


def _rule(trigger="restart", action="restart_service db",
          risk_level="medium", rationale="recover from failure",
          preconditions=None) -> dict:
    return {
        "trigger": trigger,
        "action": action,
        "risk_level": risk_level,
        "rationale": rationale,
        "preconditions": preconditions if preconditions is not None else {},
    }


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_rules():
    e = ReasoningEngine()
    assert e._rules == []


def test_rule_count_zero_initially():
    e = ReasoningEngine()
    assert e.rule_count() == 0


# ── add_rule ──────────────────────────────────────────────────────────────────

def test_add_rule_increases_count():
    e = ReasoningEngine()
    e.add_rule(_rule())
    assert e.rule_count() == 1


def test_add_rule_missing_key_raises():
    e = ReasoningEngine()
    bad = {"trigger": "x", "action": "y"}  # missing risk_level etc
    with pytest.raises(ValueError):
        e.add_rule(bad)


# ── plan empty ────────────────────────────────────────────────────────────────

def test_plan_empty_rules_empty_steps():
    e = ReasoningEngine()
    plan = e.plan("anything", {})
    assert plan.steps == []


def test_plan_empty_rules_confidence_one():
    e = ReasoningEngine()
    plan = e.plan("anything", {})
    assert plan.confidence == 1.0


# ── trigger matching ──────────────────────────────────────────────────────────

def test_plan_matching_trigger_returns_step():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="restart"))
    plan = e.plan("please restart the db", {})
    assert len(plan.steps) == 1


def test_plan_non_matching_trigger_no_step():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="restart"))
    plan = e.plan("scale the cluster", {})
    assert plan.steps == []


# ── step fields ───────────────────────────────────────────────────────────────

def test_plan_step_action_correct():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="r", action="restart_service db"))
    plan = e.plan("r now", {})
    assert plan.steps[0].action == "restart_service db"


def test_plan_step_risk_level_correct():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="r", risk_level="high"))
    plan = e.plan("r now", {})
    assert plan.steps[0].risk_level == "high"


def test_plan_step_rationale_correct():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="r", rationale="because"))
    plan = e.plan("r now", {})
    assert plan.steps[0].rationale == "because"


# ── ordering ──────────────────────────────────────────────────────────────────

def test_plan_satisfied_preconditions_first():
    e = ReasoningEngine()
    # Rule A: preconditions unsatisfied
    e.add_rule(_rule(trigger="goal", action="action_unsat",
                     preconditions={"flag": "off"}))
    # Rule B: preconditions satisfied
    e.add_rule(_rule(trigger="goal", action="action_sat",
                     preconditions={"flag": "on"}))
    plan = e.plan("goal here", {"flag": "on"})
    assert plan.steps[0].action == "action_sat"
    assert plan.steps[1].action == "action_unsat"


def test_plan_unsatisfied_steps_come_after_satisfied():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="g", action="A", preconditions={"x": 1}))
    e.add_rule(_rule(trigger="g", action="B", preconditions={"x": 2}))
    plan = e.plan("g", {"x": 1})
    assert [s.action for s in plan.steps] == ["A", "B"]


# ── confidence ────────────────────────────────────────────────────────────────

def test_confidence_one_when_all_satisfied():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="g", preconditions={"a": 1, "b": 2}))
    plan = e.plan("g", {"a": 1, "b": 2})
    assert plan.confidence == 1.0


def test_confidence_partial_when_some_unmet():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="g", preconditions={"a": 1, "b": 2}))
    plan = e.plan("g", {"a": 1})  # b is unmet
    assert plan.confidence == 0.5


def test_confidence_zero_when_none_met():
    e = ReasoningEngine()
    e.add_rule(_rule(trigger="g", preconditions={"a": 1, "b": 2}))
    plan = e.plan("g", {})
    assert plan.confidence == 0.0


# ── state + created_at ───────────────────────────────────────────────────────

def test_plan_state_used_matches_input():
    e = ReasoningEngine()
    state = {"x": "y", "n": 42}
    plan = e.plan("anything", state)
    assert plan.state_used == state


def test_plan_created_at_is_recent():
    e = ReasoningEngine()
    plan = e.plan("anything", {})
    assert abs(plan.created_at - time.time()) < 2.0


# ── status ────────────────────────────────────────────────────────────────────

def test_status_has_rule_count_key():
    e = ReasoningEngine()
    e.add_rule(_rule())
    s = e.status()
    assert "rule_count" in s
    assert s["rule_count"] == 1


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_add_rules():
    e = ReasoningEngine()
    errors: list[Exception] = []

    def worker(i: int):
        try:
            e.add_rule(_rule(trigger=f"t{i}", action=f"a{i}"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert e.rule_count() == 20
