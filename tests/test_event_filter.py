"""Phase 58C — 20 tests for pradyos.core.event_filter."""
from __future__ import annotations

import pytest

from pradyos.core.event_filter import (
    EventFilter,
    EventFilterRegistry,
    FilterRule,
)


# ── FilterRule ops ────────────────────────────────────────────────────────────

def test_eq_matches_equal_value():
    rule = FilterRule(field="status", op="eq", value="ok")
    assert rule.matches({"status": "ok"}) is True


def test_neq_matches_different_value():
    rule = FilterRule(field="status", op="neq", value="ok")
    assert rule.matches({"status": "fail"}) is True
    assert rule.matches({"status": "ok"}) is False


def test_gt_matches_greater_value():
    rule = FilterRule(field="count", op="gt", value=10)
    assert rule.matches({"count": 15}) is True
    assert rule.matches({"count": 5}) is False


def test_lt_matches_lesser_value():
    rule = FilterRule(field="count", op="lt", value=10)
    assert rule.matches({"count": 5}) is True
    assert rule.matches({"count": 15}) is False


def test_contains_matches_substring():
    rule = FilterRule(field="msg", op="contains", value="error")
    assert rule.matches({"msg": "an error occurred"}) is True
    assert rule.matches({"msg": "all good"}) is False


def test_regex_matches_pattern():
    rule = FilterRule(field="path", op="regex", value=r"^/api/v\d+/")
    assert rule.matches({"path": "/api/v2/users"}) is True
    assert rule.matches({"path": "/health"}) is False


def test_startswith_matches_prefix():
    rule = FilterRule(field="path", op="startswith", value="/api")
    assert rule.matches({"path": "/api/v1"}) is True
    assert rule.matches({"path": "/static"}) is False


def test_endswith_matches_suffix():
    rule = FilterRule(field="file", op="endswith", value=".log")
    assert rule.matches({"file": "system.log"}) is True
    assert rule.matches({"file": "system.txt"}) is False


def test_missing_field_returns_false():
    rule = FilterRule(field="status", op="eq", value="ok")
    assert rule.matches({"other": "ok"}) is False  # no `status` key — no raise


def test_dot_notation_resolves_nested():
    rule = FilterRule(field="meta.source", op="eq", value="api")
    assert rule.matches({"meta": {"source": "api"}}) is True
    assert rule.matches({"meta": {"source": "cli"}}) is False
    assert rule.matches({"meta": {}}) is False  # missing nested key


def test_unknown_op_returns_false():
    rule = FilterRule(field="x", op="bogus", value=1)
    assert rule.matches({"x": 1}) is False


# ── EventFilter compound ──────────────────────────────────────────────────────

def test_and_mode_all_match_true():
    rules = [
        FilterRule("status", "eq", "ok"),
        FilterRule("count", "gt", 5),
    ]
    f = EventFilter(rules, mode="AND")
    assert f.match({"status": "ok", "count": 10}) is True


def test_and_mode_one_miss_false():
    rules = [
        FilterRule("status", "eq", "ok"),
        FilterRule("count", "gt", 5),
    ]
    f = EventFilter(rules, mode="AND")
    assert f.match({"status": "ok", "count": 3}) is False


def test_or_mode_one_match_true():
    rules = [
        FilterRule("status", "eq", "fail"),
        FilterRule("count", "gt", 5),
    ]
    f = EventFilter(rules, mode="OR")
    assert f.match({"status": "ok", "count": 10}) is True


def test_or_mode_all_miss_false():
    rules = [
        FilterRule("status", "eq", "fail"),
        FilterRule("count", "gt", 5),
    ]
    f = EventFilter(rules, mode="OR")
    assert f.match({"status": "ok", "count": 1}) is False


def test_empty_rules_returns_true():
    f = EventFilter([])
    assert f.match({"anything": "goes"}) is True


def test_invalid_mode_raises_value_error():
    with pytest.raises(ValueError, match="AND or OR"):
        EventFilter([], mode="XOR")


# ── EventFilterRegistry ──────────────────────────────────────────────────────

def test_registry_register_get_roundtrip():
    reg = EventFilterRegistry()
    rules = [FilterRule("status", "eq", "ok")]
    reg.register("ok_filter", rules)
    f = reg.get("ok_filter")
    assert f is not None
    assert f.match({"status": "ok"}) is True


def test_registry_apply_returns_only_matching():
    reg = EventFilterRegistry()
    reg.register("errors", [FilterRule("level", "eq", "error")])
    events = [
        {"level": "info"},
        {"level": "error", "msg": "boom"},
        {"level": "warn"},
        {"level": "error", "msg": "kaput"},
    ]
    matched = reg.apply("errors", events)
    assert len(matched) == 2
    assert all(e["level"] == "error" for e in matched)


def test_registry_apply_unknown_raises_key_error():
    reg = EventFilterRegistry()
    with pytest.raises(KeyError):
        reg.apply("phantom", [])


# ── delete + list ────────────────────────────────────────────────────────────

def test_registry_delete_and_list():
    reg = EventFilterRegistry()
    reg.register("a", [FilterRule("x", "eq", 1)])
    reg.register("b", [FilterRule("x", "eq", 2)])
    assert reg.list_names() == ["a", "b"]
    assert reg.delete("a") is True
    assert reg.list_names() == ["b"]
    assert reg.delete("phantom") is False
