"""Phase 62C — 20 tests for pradyos.core.event_router."""
from __future__ import annotations

import pytest

from pradyos.core.event_router import EventRouter, Route, RouterRegistry


# ── EventRouter init ─────────────────────────────────────────────────────────

def test_init_empty_no_routes():
    r = EventRouter()
    assert r.count() == 0
    assert r.list_routes() == []


# ── add_route ────────────────────────────────────────────────────────────────

def test_add_route_returns_route_object():
    r = EventRouter()
    route = r.add_route("r1", [], "dest1")
    assert isinstance(route, Route)
    assert route.name == "r1"
    assert route.destination == "dest1"


def test_add_route_duplicate_name_raises():
    r = EventRouter()
    r.add_route("r1", [], "dest1")
    with pytest.raises(ValueError, match="already exists"):
        r.add_route("r1", [], "dest2")


def test_add_route_appends_in_order():
    r = EventRouter()
    r.add_route("a", [], "da")
    r.add_route("b", [], "db")
    r.add_route("c", [], "dc")
    names = [route["name"] for route in r.list_routes()]
    assert names == ["a", "b", "c"]


# ── remove_route ─────────────────────────────────────────────────────────────

def test_remove_route_returns_true_removes():
    r = EventRouter()
    r.add_route("r1", [], "d1")
    assert r.remove_route("r1") is True
    assert r.count() == 0


def test_remove_route_unknown_returns_false():
    r = EventRouter()
    assert r.remove_route("phantom") is False


# ── route: predicate matching ────────────────────────────────────────────────

def test_route_empty_predicates_matches_anything():
    r = EventRouter()
    r.add_route("r1", [], "everywhere")
    assert r.route({"any": "thing"}) == ["everywhere"]


def test_route_eq_predicate_matches():
    r = EventRouter()
    r.add_route(
        "r1",
        [{"field": "level", "op": "eq", "value": "error"}],
        "alerts",
    )
    assert r.route({"level": "error"}) == ["alerts"]
    assert r.route({"level": "info"}) == []


def test_route_neq_predicate():
    r = EventRouter()
    r.add_route("r1", [{"field": "status", "op": "neq", "value": "ok"}], "fail")
    assert r.route({"status": "fail"}) == ["fail"]
    assert r.route({"status": "ok"}) == []


def test_route_gt_numeric_predicate():
    r = EventRouter()
    r.add_route("r1", [{"field": "count", "op": "gt", "value": 10}], "high")
    assert r.route({"count": 15}) == ["high"]
    assert r.route({"count": 5}) == []


def test_route_contains_predicate():
    r = EventRouter()
    r.add_route("r1", [{"field": "msg", "op": "contains", "value": "error"}], "err")
    assert r.route({"msg": "fatal error occurred"}) == ["err"]
    assert r.route({"msg": "all good"}) == []


def test_route_startswith_predicate():
    r = EventRouter()
    r.add_route("r1", [{"field": "path", "op": "startswith", "value": "/api"}], "api")
    assert r.route({"path": "/api/v1"}) == ["api"]
    assert r.route({"path": "/static"}) == []


def test_route_endswith_predicate():
    r = EventRouter()
    r.add_route("r1", [{"field": "file", "op": "endswith", "value": ".log"}], "logs")
    assert r.route({"file": "boot.log"}) == ["logs"]
    assert r.route({"file": "boot.txt"}) == []


# ── compound predicates (AND) ────────────────────────────────────────────────

def test_route_multiple_predicates_all_must_match():
    r = EventRouter()
    r.add_route(
        "r1",
        [
            {"field": "level", "op": "eq", "value": "error"},
            {"field": "count", "op": "gt", "value": 5},
        ],
        "alert",
    )
    assert r.route({"level": "error", "count": 10}) == ["alert"]
    assert r.route({"level": "error", "count": 3}) == []
    assert r.route({"level": "info", "count": 10}) == []


# ── multi-route fanout ───────────────────────────────────────────────────────

def test_route_multiple_routes_fan_out():
    r = EventRouter()
    r.add_route("err", [{"field": "level", "op": "eq", "value": "error"}], "errors")
    r.add_route("loud", [{"field": "count", "op": "gt", "value": 10}], "loud_chan")
    # Event matches BOTH routes → both destinations returned, sorted
    assert r.route({"level": "error", "count": 99}) == ["errors", "loud_chan"]


# ── missing field handling ───────────────────────────────────────────────────

def test_route_missing_field_eq_false():
    r = EventRouter()
    r.add_route("r1", [{"field": "absent", "op": "eq", "value": "x"}], "d")
    assert r.route({"other": "x"}) == []


def test_route_missing_field_neq_true():
    r = EventRouter()
    r.add_route("r1", [{"field": "absent", "op": "neq", "value": "x"}], "d")
    assert r.route({"other": "x"}) == ["d"]


# ── default destination ──────────────────────────────────────────────────────

def test_default_destination_when_no_match():
    r = EventRouter(default_destination="default_chan")
    r.add_route("r1", [{"field": "level", "op": "eq", "value": "fatal"}], "fatal_chan")
    assert r.route({"level": "info"}) == ["default_chan"]


def test_default_destination_not_applied_when_a_match_exists():
    r = EventRouter(default_destination="default_chan")
    r.add_route("r1", [{"field": "level", "op": "eq", "value": "error"}], "errors")
    assert r.route({"level": "error"}) == ["errors"]


# ── RouterRegistry ───────────────────────────────────────────────────────────

def test_registry_create_get_delete():
    reg = RouterRegistry()
    reg.create("primary")
    assert isinstance(reg.get("primary"), EventRouter)
    assert reg.list_names() == ["primary"]
    assert reg.delete("primary") is True
    assert reg.get("primary") is None


def test_registry_create_duplicate_raises():
    reg = RouterRegistry()
    reg.create("r1")
    with pytest.raises(ValueError):
        reg.create("r1")
