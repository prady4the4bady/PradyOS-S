"""Phase 35C — 20 tests for pradyos.core.reactor.ReactorEngine."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pytest

from pradyos.core.reactor import ReactorEngine, ReactorRule, ReactionEvent


@dataclass
class _StubEntry:
    """Minimal stand-in for DecisionEntry — only the 3 attrs react() reads."""
    decision_type: str
    rationale: str
    outcome: str


def _entry(decision_type="watchpoint_alert",
           rationale="signal=cpu value=99",
           outcome="alert:cpu_high") -> _StubEntry:
    return _StubEntry(decision_type=decision_type, rationale=rationale, outcome=outcome)


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    r = ReactorEngine()
    assert r._rules == {}
    assert len(r._log) == 0


# ── add_rule ──────────────────────────────────────────────────────────────────

def test_add_rule_returns_rule():
    r = ReactorEngine()
    rule = r.add_rule("watchpoint_alert", "log")
    assert isinstance(rule, ReactorRule)


def test_add_rule_stores_with_correct_fields():
    r = ReactorEngine()
    rule = r.add_rule("watchpoint_alert", "escalate")
    assert rule.decision_type == "watchpoint_alert"
    assert rule.action == "escalate"
    assert rule.rule_id in r._rules


def test_add_rule_default_context_filter_empty():
    r = ReactorEngine()
    rule = r.add_rule("alert", "log")
    assert rule.context_filter == {}


def test_add_rule_unique_ids():
    r = ReactorEngine()
    r1 = r.add_rule("alert", "log")
    r2 = r.add_rule("alert", "log")
    assert r1.rule_id != r2.rule_id


# ── remove_rule ───────────────────────────────────────────────────────────────

def test_remove_rule_returns_true():
    r = ReactorEngine()
    rule = r.add_rule("alert", "log")
    assert r.remove_rule(rule.rule_id) is True


def test_remove_rule_returns_false_unknown():
    r = ReactorEngine()
    assert r.remove_rule("phantom") is False


def test_remove_rule_actually_removes():
    r = ReactorEngine()
    rule = r.add_rule("alert", "log")
    r.remove_rule(rule.rule_id)
    assert rule.rule_id not in r._rules


# ── list_rules ────────────────────────────────────────────────────────────────

def test_list_rules_sorted_by_created_at():
    r = ReactorEngine()
    r1 = r.add_rule("a", "log")
    time.sleep(0.001)
    r2 = r.add_rule("b", "snapshot")
    time.sleep(0.001)
    r3 = r.add_rule("c", "escalate")
    out = r.list_rules()
    assert [x["rule_id"] for x in out] == [r1.rule_id, r2.rule_id, r3.rule_id]


def test_list_rules_entries_are_dicts_with_keys():
    r = ReactorEngine()
    r.add_rule("alert", "log")
    entry = r.list_rules()[0]
    for k in ("rule_id", "decision_type", "action", "context_filter", "created_at"):
        assert k in entry, f"Missing key: {k}"


# ── react ─────────────────────────────────────────────────────────────────────

def test_react_no_rules_empty_list():
    r = ReactorEngine()
    fired = r.react(_entry())
    assert fired == []


def test_react_matching_rule_returns_event():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "log")
    fired = r.react(_entry())
    assert len(fired) == 1
    assert isinstance(fired[0], ReactionEvent)
    assert fired[0].action == "log"


def test_react_filter_by_decision_type():
    r = ReactorEngine()
    r.add_rule("other_type", "log")
    fired = r.react(_entry(decision_type="watchpoint_alert"))
    assert fired == []


def test_react_context_filter_substring_match():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "escalate",
               context_filter={"severity": "critical"})
    fired = r.react(_entry(rationale="severity=critical signal=cpu"))
    assert len(fired) == 1


def test_react_context_filter_empty_matches_all():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "log", context_filter={})
    fired = r.react(_entry())
    assert len(fired) == 1


def test_react_context_filter_no_match():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "log",
               context_filter={"severity": "critical"})
    fired = r.react(_entry(rationale="severity=warn signal=cpu"))
    assert fired == []


def test_react_appends_to_log():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "log")
    r.react(_entry())
    r.react(_entry())
    assert len(r._log) == 2


# ── get_log / count ───────────────────────────────────────────────────────────

def test_get_log_returns_last_n():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "log")
    for _ in range(5):
        r.react(_entry())
    last3 = r.get_log(limit=3)
    assert len(last3) == 3


def test_count_returns_rules_and_reactions():
    r = ReactorEngine()
    r.add_rule("watchpoint_alert", "log")
    r.add_rule("other", "snapshot")
    r.react(_entry())
    c = r.count()
    assert c == {"rules": 2, "reactions": 1}


# ── thread safety ─────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_react():
    r = ReactorEngine(max_log=5000)
    r.add_rule("watchpoint_alert", "log")
    errors: list[Exception] = []

    def worker():
        try:
            r.react(_entry())
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(r._log) == 50
