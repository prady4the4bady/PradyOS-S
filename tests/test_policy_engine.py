"""Phase 14D — PolicyEngine unit tests (20 tests).

Covers:
 1.  evaluate() returns PolicyVerdict
 2.  allowed=True when no rules loaded
 3.  constitutional_guard blocks matching task (allowed=False)
 4.  constitutional_guard passes non-matching task
 5.  rate_limit blocks when count exceeds max_per_minute
 6.  rate_limit allows when under limit
 7.  approval_required rule: allowed=True (approval enforced at Sovereign layer)
 8.  load() replaces rules (old rules gone after reload)
 9.  get_rules() returns a copy (mutation doesn't affect engine state)
10.  verdict.to_dict() has 'allowed' and 'reason' keys
11.  reason == "ok" when allowed
12.  reason is non-empty string when blocked
13.  multiple rules: first blocking rule wins
14.  match dict with multiple keys: all must match to trigger rule
15.  match dict with no keys: rule applies to all tasks
16.  constitutional_guard with no match key: blocks everything
17.  rate_limit window resets after window_seconds (mock time)
18.  evaluate() is thread-safe (no crash under concurrent calls)
19.  PolicyViolationError raised on blocked dispatch (integration with ImperiumKernel)
20.  empty load([]) clears all rules
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from pradyos.imperium.policy_engine import (
    PolicyEngine,
    PolicyVerdict,
    PolicyViolationError,
)


# ---------------------------------------------------------------------------
# Minimal task stub
# ---------------------------------------------------------------------------

@dataclass
class _Task:
    kind: str = "titan.shell"
    metadata: dict[str, Any] = field(default_factory=dict)
    task_id: str = "test-task-001"


def _task(**meta) -> _Task:
    return _Task(metadata=meta)


# ---------------------------------------------------------------------------
# Test 1: evaluate() returns PolicyVerdict
# ---------------------------------------------------------------------------

def test_evaluate_returns_policy_verdict():
    engine = PolicyEngine()
    result = engine.evaluate(_task())
    assert isinstance(result, PolicyVerdict)


# ---------------------------------------------------------------------------
# Test 2: allowed=True when no rules loaded
# ---------------------------------------------------------------------------

def test_no_rules_allows_everything():
    engine = PolicyEngine()
    verdict = engine.evaluate(_task(action="delete_everything"))
    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Test 3: constitutional_guard blocks matching task (allowed=False)
# ---------------------------------------------------------------------------

def test_constitutional_guard_blocks_matching_task():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {"action": "nuke"},
        "deny_reason": "nuclear actions prohibited",
    }])
    verdict = engine.evaluate(_task(action="nuke_db"))
    assert verdict.allowed is False
    assert "nuclear actions prohibited" in verdict.reason


# ---------------------------------------------------------------------------
# Test 4: constitutional_guard passes non-matching task
# ---------------------------------------------------------------------------

def test_constitutional_guard_passes_non_matching_task():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {"action": "nuke"},
        "deny_reason": "nuclear actions prohibited",
    }])
    verdict = engine.evaluate(_task(action="deploy"))
    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Test 5: rate_limit blocks when count exceeds max_per_minute
# ---------------------------------------------------------------------------

def test_rate_limit_blocks_when_exceeded():
    engine = PolicyEngine()
    engine.load([{
        "type": "rate_limit",
        "match": {},          # matches all tasks
        "max_per_minute": 3,
        "window_seconds": 60,
    }])
    task = _task()
    # First 3 should be allowed
    for _ in range(3):
        v = engine.evaluate(task)
        assert v.allowed is True, "expected allowed before limit"
    # 4th should be blocked
    v = engine.evaluate(task)
    assert v.allowed is False
    assert "rate limit" in v.reason.lower()


# ---------------------------------------------------------------------------
# Test 6: rate_limit allows when under limit
# ---------------------------------------------------------------------------

def test_rate_limit_allows_under_limit():
    engine = PolicyEngine()
    engine.load([{
        "type": "rate_limit",
        "match": {},
        "max_per_minute": 10,
        "window_seconds": 60,
    }])
    for _ in range(9):
        v = engine.evaluate(_task())
        assert v.allowed is True


# ---------------------------------------------------------------------------
# Test 7: approval_required rule: allowed=True (enforcement at Sovereign layer)
# ---------------------------------------------------------------------------

def test_approval_required_returns_allowed_true():
    engine = PolicyEngine()
    engine.load([{
        "type": "approval_required",
        "match": {"sensitivity": "high"},
        "approvers": ["ciso", "cto"],
    }])
    verdict = engine.evaluate(_task(sensitivity="high"))
    # approval_required does NOT block — Sovereign enforces it
    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Test 8: load() replaces rules (old rules gone after reload)
# ---------------------------------------------------------------------------

def test_load_replaces_rules():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {},
        "deny_reason": "old rule",
    }])
    # Verify old rule blocks
    assert engine.evaluate(_task()).allowed is False

    # Replace with empty ruleset
    engine.load([])
    assert engine.evaluate(_task()).allowed is True


# ---------------------------------------------------------------------------
# Test 9: get_rules() returns a copy (mutation doesn't affect engine state)
# ---------------------------------------------------------------------------

def test_get_rules_returns_copy():
    engine = PolicyEngine()
    original = [{"type": "constitutional_guard", "match": {}, "deny_reason": "test"}]
    engine.load(original)

    rules_copy = engine.get_rules()
    rules_copy.clear()   # mutate the returned copy

    # Engine state must be unchanged
    assert len(engine.get_rules()) == 1


# ---------------------------------------------------------------------------
# Test 10: verdict.to_dict() has 'allowed' and 'reason' keys
# ---------------------------------------------------------------------------

def test_verdict_to_dict_has_correct_keys():
    verdict = PolicyVerdict(allowed=True, reason="ok")
    d = verdict.to_dict()
    assert "allowed" in d
    assert "reason" in d


# ---------------------------------------------------------------------------
# Test 11: reason == "ok" when allowed
# ---------------------------------------------------------------------------

def test_reason_is_ok_when_allowed():
    engine = PolicyEngine()
    verdict = engine.evaluate(_task())
    assert verdict.allowed is True
    assert verdict.reason == "ok"


# ---------------------------------------------------------------------------
# Test 12: reason is non-empty string when blocked
# ---------------------------------------------------------------------------

def test_reason_is_non_empty_when_blocked():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {},
        "deny_reason": "blocked for testing",
    }])
    verdict = engine.evaluate(_task())
    assert verdict.allowed is False
    assert isinstance(verdict.reason, str)
    assert len(verdict.reason) > 0


# ---------------------------------------------------------------------------
# Test 13: multiple rules — first blocking rule wins
# ---------------------------------------------------------------------------

def test_first_blocking_rule_wins():
    engine = PolicyEngine()
    engine.load([
        {
            "type": "constitutional_guard",
            "match": {"zone": "red"},
            "deny_reason": "red zone blocked",
        },
        {
            "type": "constitutional_guard",
            "match": {"zone": "red"},
            "deny_reason": "second rule — should not appear",
        },
    ])
    verdict = engine.evaluate(_task(zone="red-zone"))
    assert verdict.allowed is False
    assert "red zone blocked" in verdict.reason
    assert "second rule" not in verdict.reason


# ---------------------------------------------------------------------------
# Test 14: match dict with multiple keys — all must match
# ---------------------------------------------------------------------------

def test_match_requires_all_keys_present():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {"env": "prod", "action": "drop"},
        "deny_reason": "prod drop blocked",
    }])
    # Only env=prod, no action key → should NOT match
    v1 = engine.evaluate(_task(env="prod"))
    assert v1.allowed is True

    # Both keys present → should match
    v2 = engine.evaluate(_task(env="prod", action="drop"))
    assert v2.allowed is False


# ---------------------------------------------------------------------------
# Test 15: match dict with no keys — rule applies to all tasks
# ---------------------------------------------------------------------------

def test_empty_match_applies_to_all_tasks():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {},
        "deny_reason": "blocks everything",
    }])
    assert engine.evaluate(_task()).allowed is False
    assert engine.evaluate(_task(foo="bar", baz=42)).allowed is False


# ---------------------------------------------------------------------------
# Test 16: constitutional_guard with no match key blocks everything
# ---------------------------------------------------------------------------

def test_constitutional_guard_no_match_key_blocks_all():
    engine = PolicyEngine()
    # Rule has no 'match' key at all — defaults to {}
    engine.load([{
        "type": "constitutional_guard",
        "deny_reason": "global block",
    }])
    assert engine.evaluate(_task(anything="goes")).allowed is False


# ---------------------------------------------------------------------------
# Test 17: rate_limit window resets after window_seconds (mock time)
# ---------------------------------------------------------------------------

def test_rate_limit_window_resets_after_window():
    engine = PolicyEngine()
    engine.load([{
        "type": "rate_limit",
        "match": {},
        "max_per_minute": 2,
        "window_seconds": 10,
    }])
    task = _task()

    # Use up the limit
    engine.evaluate(task)  # 1
    engine.evaluate(task)  # 2
    blocked = engine.evaluate(task)  # 3 → blocked
    assert blocked.allowed is False

    # Fast-forward time past the window
    fake_now = time.time() + 11  # 11s > window_seconds=10
    with patch("pradyos.imperium.policy_engine.time") as mock_time:
        mock_time.time.return_value = fake_now
        # After window reset, counter should be empty → allowed
        v = engine.evaluate(task)
    assert v.allowed is True


# ---------------------------------------------------------------------------
# Test 18: evaluate() is thread-safe (no crash under concurrent calls)
# ---------------------------------------------------------------------------

def test_evaluate_thread_safe():
    engine = PolicyEngine()
    engine.load([{
        "type": "rate_limit",
        "match": {},
        "max_per_minute": 1000,
        "window_seconds": 60,
    }])
    errors: list[Exception] = []

    def _worker():
        try:
            for _ in range(50):
                engine.evaluate(_task())
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# Test 19: PolicyViolationError raised on blocked dispatch (integration)
# ---------------------------------------------------------------------------

def test_policy_violation_error_raised_on_blocked_dispatch():
    """Integration: PolicyEngine injected into Imperium kernel raises error."""
    from pradyos.core.bus import EventBus
    from pradyos.core.types import TaskState
    from pradyos.imperium.kernel import Imperium
    from pradyos.imperium.task import ImperiumTask, TaskRecord

    # Build a blocking policy engine
    pe = PolicyEngine()
    pe.load([{
        "type": "constitutional_guard",
        "match": {},
        "deny_reason": "all tasks blocked for test",
    }])

    isolated_bus = EventBus()
    kern = Imperium(bus=isolated_bus, policy_engine=pe, workers=0)

    task = ImperiumTask(kind="titan.shell", payload={"command": "echo hi"})
    rec = TaskRecord(spec=task, state=TaskState.QUEUED)

    with pytest.raises(PolicyViolationError, match="all tasks blocked for test"):
        kern._run_record(rec)


# ---------------------------------------------------------------------------
# Test 20: empty load([]) clears all rules
# ---------------------------------------------------------------------------

def test_empty_load_clears_all_rules():
    engine = PolicyEngine()
    engine.load([{
        "type": "constitutional_guard",
        "match": {},
        "deny_reason": "should be cleared",
    }])
    assert engine.evaluate(_task()).allowed is False

    engine.load([])
    assert engine.get_rules() == []
    assert engine.evaluate(_task()).allowed is True
