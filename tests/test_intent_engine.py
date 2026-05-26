"""Phase 19C — IntentEngine unit tests (20 tests).

Covers:
  1.  IntentEngine() initialises with empty rules
  2.  load_rules() sets rules; get_rules() returns them
  3.  get_rules() returns independent copy (mutation-safe)
  4.  suggest() returns empty list with no rules
  5.  suggest() returns empty list when condition not met
  6.  graph_nodes_gt fires when nodes > threshold
  7.  graph_nodes_gt does NOT fire when nodes == threshold
  8.  error_span_rate_gt fires when error fraction > threshold
  9.  error_span_rate_gt does NOT fire when no spans
 10.  active_campaigns_lt fires when count < threshold
 11.  active_campaigns_lt does NOT fire when count >= threshold
 12.  ledger_events_gt fires when count > threshold
 13.  ledger_events_gt does NOT fire when count == threshold
 14.  suggest() returns IntentSuggestion with correct fields
 15.  suggest() returns multiple suggestions when multiple rules fire
 16.  IntentSuggestion has non-empty suggestion_id (uuid hex)
 17.  IntentSuggestion ts is approximately now
 18.  to_dict() has all required keys
 19.  unknown condition silently skipped (no crash)
 20.  load_rules() with empty list clears all rules
"""
from __future__ import annotations

import time

import pytest

from pradyos.core.intent_engine import IntentEngine, IntentSuggestion


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _rule(condition: str, threshold: float = 0.0, **kwargs) -> dict:
    base = {
        "id": "r1",
        "condition": condition,
        "threshold": threshold,
        "action": "do_something",
        "target": "system",
        "reason": "test reason",
        "confidence": 0.8,
    }
    base.update(kwargs)
    return base


# ===========================================================================
# Test 1: IntentEngine initialises with empty rules
# ===========================================================================

def test_engine_init_empty_rules():
    engine = IntentEngine()
    assert engine.get_rules() == []


# ===========================================================================
# Test 2: load_rules() sets rules; get_rules() returns them
# ===========================================================================

def test_load_and_get_rules():
    engine = IntentEngine()
    rules = [_rule("graph_nodes_gt", 10)]
    engine.load_rules(rules)
    result = engine.get_rules()
    assert len(result) == 1
    assert result[0]["condition"] == "graph_nodes_gt"


# ===========================================================================
# Test 3: get_rules() returns independent copy (mutation-safe)
# ===========================================================================

def test_get_rules_returns_copy():
    engine = IntentEngine()
    rules = [_rule("graph_nodes_gt", 5)]
    engine.load_rules(rules)
    copy1 = engine.get_rules()
    copy1.append({"id": "extra"})          # mutate the returned list
    copy2 = engine.get_rules()
    assert len(copy2) == 1                 # internal state unchanged


# ===========================================================================
# Test 4: suggest() returns empty list with no rules
# ===========================================================================

def test_suggest_empty_with_no_rules():
    engine = IntentEngine()
    result = engine.suggest(graph_stats={"nodes": 100})
    assert result == []


# ===========================================================================
# Test 5: suggest() returns empty list when condition not met
# ===========================================================================

def test_suggest_no_match_returns_empty():
    engine = IntentEngine(rules=[_rule("graph_nodes_gt", threshold=50.0)])
    result = engine.suggest(graph_stats={"nodes": 10})
    assert result == []


# ===========================================================================
# Test 6: graph_nodes_gt fires when nodes > threshold
# ===========================================================================

def test_graph_nodes_gt_fires():
    engine = IntentEngine(rules=[_rule("graph_nodes_gt", threshold=5.0)])
    result = engine.suggest(graph_stats={"nodes": 6})
    assert len(result) == 1


# ===========================================================================
# Test 7: graph_nodes_gt does NOT fire when nodes == threshold
# ===========================================================================

def test_graph_nodes_gt_no_fire_on_equal():
    engine = IntentEngine(rules=[_rule("graph_nodes_gt", threshold=5.0)])
    result = engine.suggest(graph_stats={"nodes": 5})
    assert result == []


# ===========================================================================
# Test 8: error_span_rate_gt fires when error fraction > threshold
# ===========================================================================

def test_error_span_rate_gt_fires():
    spans = [
        {"status": "error"},
        {"status": "error"},
        {"status": "ok"},
        {"status": "ok"},
    ]  # error rate = 0.5
    engine = IntentEngine(rules=[_rule("error_span_rate_gt", threshold=0.4)])
    result = engine.suggest(recent_spans=spans)
    assert len(result) == 1


# ===========================================================================
# Test 9: error_span_rate_gt does NOT fire when no spans
# ===========================================================================

def test_error_span_rate_gt_no_spans():
    engine = IntentEngine(rules=[_rule("error_span_rate_gt", threshold=0.0)])
    result = engine.suggest(recent_spans=None)
    assert result == []


# ===========================================================================
# Test 10: active_campaigns_lt fires when count < threshold
# ===========================================================================

def test_active_campaigns_lt_fires():
    engine = IntentEngine(rules=[_rule("active_campaigns_lt", threshold=3.0)])
    result = engine.suggest(active_campaigns=[{"id": "c1"}])  # count=1 < 3
    assert len(result) == 1


# ===========================================================================
# Test 11: active_campaigns_lt does NOT fire when count >= threshold
# ===========================================================================

def test_active_campaigns_lt_no_fire():
    engine = IntentEngine(rules=[_rule("active_campaigns_lt", threshold=2.0)])
    result = engine.suggest(active_campaigns=[{"id": "c1"}, {"id": "c2"}])  # count=2
    assert result == []


# ===========================================================================
# Test 12: ledger_events_gt fires when count > threshold
# ===========================================================================

def test_ledger_events_gt_fires():
    engine = IntentEngine(rules=[_rule("ledger_events_gt", threshold=2.0)])
    entries = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]  # count=3 > 2
    result = engine.suggest(recent_entries=entries)
    assert len(result) == 1


# ===========================================================================
# Test 13: ledger_events_gt does NOT fire when count == threshold
# ===========================================================================

def test_ledger_events_gt_no_fire_on_equal():
    engine = IntentEngine(rules=[_rule("ledger_events_gt", threshold=3.0)])
    entries = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]  # count=3 == 3
    result = engine.suggest(recent_entries=entries)
    assert result == []


# ===========================================================================
# Test 14: suggest() returns IntentSuggestion with correct fields
# ===========================================================================

def test_suggestion_fields_correct():
    rule = {
        "id": "r1",
        "condition": "graph_nodes_gt",
        "threshold": 0.0,
        "action": "scale_workers",
        "target": "worker_pool",
        "reason": "graph is large",
        "confidence": 0.9,
    }
    engine = IntentEngine(rules=[rule])
    result = engine.suggest(graph_stats={"nodes": 1})
    assert len(result) == 1
    s = result[0]
    assert s.action == "scale_workers"
    assert s.target == "worker_pool"
    assert s.reason == "graph is large"
    assert s.confidence == pytest.approx(0.9)


# ===========================================================================
# Test 15: suggest() returns multiple suggestions when multiple rules fire
# ===========================================================================

def test_suggest_multiple_rules_fire():
    rules = [
        _rule("graph_nodes_gt", threshold=0.0, id="r1", action="a1"),
        _rule("ledger_events_gt", threshold=0.0, id="r2", action="a2"),
    ]
    engine = IntentEngine(rules=rules)
    result = engine.suggest(
        graph_stats={"nodes": 1},
        recent_entries=[{"id": "e1"}],
    )
    assert len(result) == 2
    actions = {s.action for s in result}
    assert "a1" in actions
    assert "a2" in actions


# ===========================================================================
# Test 16: IntentSuggestion has non-empty suggestion_id (uuid hex)
# ===========================================================================

def test_suggestion_id_nonempty():
    s = IntentSuggestion(action="a", target="t", reason="r", confidence=0.5)
    assert isinstance(s.suggestion_id, str)
    assert len(s.suggestion_id) == 32       # uuid4().hex is always 32 chars
    assert s.suggestion_id != ""


# ===========================================================================
# Test 17: IntentSuggestion ts is approximately now
# ===========================================================================

def test_suggestion_ts_is_now():
    before = time.time()
    s = IntentSuggestion(action="a", target="t", reason="r", confidence=0.5)
    after = time.time()
    assert before <= s.ts <= after


# ===========================================================================
# Test 18: to_dict() has all required keys
# ===========================================================================

def test_to_dict_has_all_keys():
    s = IntentSuggestion(action="run_campaign", target="camp_a", reason="why not", confidence=0.7)
    d = s.to_dict()
    for key in ("suggestion_id", "action", "target", "reason", "confidence", "ts"):
        assert key in d, f"Missing key: {key}"


# ===========================================================================
# Test 19: unknown condition silently skipped (no crash)
# ===========================================================================

def test_unknown_condition_silently_skipped():
    rule = _rule("totally_unknown_condition", threshold=0.0)
    engine = IntentEngine(rules=[rule])
    result = engine.suggest(graph_stats={"nodes": 999})
    assert result == []


# ===========================================================================
# Test 20: load_rules() with empty list clears all rules
# ===========================================================================

def test_load_rules_empty_clears():
    engine = IntentEngine(rules=[_rule("graph_nodes_gt", 1.0)])
    assert len(engine.get_rules()) == 1
    engine.load_rules([])
    assert engine.get_rules() == []
