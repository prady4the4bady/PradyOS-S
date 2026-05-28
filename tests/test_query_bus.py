"""Phase 65C — 20 tests for pradyos.core.query_bus.QueryBus."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.query_bus import QueryBus, QueryResult


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_handlers_empty_history():
    bus = QueryBus()
    assert bus.list_handlers() == []
    assert bus.history() == []


# ── register / unregister ────────────────────────────────────────────────────

def test_register_stores_handler():
    bus = QueryBus()
    bus.register("lookup", lambda p: {"found": p})
    assert "lookup" in bus.list_handlers()


def test_register_overwrites_same_name_no_error():
    bus = QueryBus()
    bus.register("h", lambda p: {"v": 1})
    bus.register("h", lambda p: {"v": 2})
    result = bus.query("h", {})
    assert result.result == {"v": 2}


def test_unregister_returns_true_removes():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    assert bus.unregister("h") is True
    assert "h" not in bus.list_handlers()


def test_unregister_unknown_returns_false():
    bus = QueryBus()
    assert bus.unregister("phantom") is False


def test_list_handlers_sorted():
    bus = QueryBus()
    bus.register("zzz", lambda p: {})
    bus.register("aaa", lambda p: {})
    bus.register("mmm", lambda p: {})
    assert bus.list_handlers() == ["aaa", "mmm", "zzz"]


# ── query ────────────────────────────────────────────────────────────────────

def test_query_unknown_name_returns_success_false_with_error():
    bus = QueryBus()
    result = bus.query("phantom", {})
    assert result.success is False
    assert "phantom" in result.error


def test_query_known_handler_returns_success_true():
    bus = QueryBus()
    bus.register("ping", lambda p: {"pong": True})
    result = bus.query("ping", {})
    assert result.success is True


def test_query_handler_return_value_in_result():
    bus = QueryBus()
    bus.register("lookup", lambda p: {"found": p})
    result = bus.query("lookup", {"id": "x"})
    assert result.result == {"found": {"id": "x"}}


def test_query_duration_ms_non_negative_float():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    result = bus.query("h", {})
    assert isinstance(result.duration_ms, float)
    assert result.duration_ms >= 0.0


def test_query_queried_at_is_recent():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    result = bus.query("h", {})
    assert abs(result.queried_at - time.time()) < 2.0


def test_query_exception_records_failure():
    bus = QueryBus()

    def bad(p):
        raise RuntimeError("kaboom")

    bus.register("bad", bad)
    result = bus.query("bad", {})
    assert result.success is False
    assert "kaboom" in result.error
    assert result.result == {}


def test_query_appends_to_history():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    bus.query("h", {})
    bus.query("h", {})
    assert len(bus.history()) == 2


# ── history ──────────────────────────────────────────────────────────────────

def test_history_newest_first_order():
    bus = QueryBus()
    bus.register("h", lambda p: {"i": p.get("i")})
    bus.query("h", {"i": 1})
    bus.query("h", {"i": 2})
    bus.query("h", {"i": 3})
    hist = bus.history()
    assert hist[0].result["i"] == 3
    assert hist[-1].result["i"] == 1


def test_history_limit_parameter_respected():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    for _ in range(10):
        bus.query("h", {})
    assert len(bus.history(limit=3)) == 3


def test_history_limit_capped_at_500():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    bus.query("h", {})
    hist = bus.history(limit=99999)
    assert len(hist) <= QueryBus.HISTORY_LIMIT


def test_clear_history_returns_count_empties():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    for _ in range(5):
        bus.query("h", {})
    n = bus.clear_history()
    assert n == 5
    assert bus.history() == []


def test_history_ring_buffer_caps_at_500():
    bus = QueryBus()
    bus.register("h", lambda p: {})
    for _ in range(600):
        bus.query("h", {})
    assert len(bus.history(limit=500)) == 500


# ── concurrency ──────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_queries():
    bus = QueryBus()
    bus.register("h", lambda p: {"ok": True})
    errors: list[Exception] = []

    def worker():
        try:
            bus.query("h", {})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(bus.history(limit=100)) == 50


# ── params=None default ──────────────────────────────────────────────────────

def test_query_params_none_defaults_to_empty_dict():
    bus = QueryBus()
    seen = []
    bus.register("h", lambda p: (seen.append(p) or {}))
    bus.query("h", params=None)
    assert seen == [{}]
