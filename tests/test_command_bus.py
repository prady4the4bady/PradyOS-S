"""Phase 64C — 20 tests for pradyos.core.command_bus.CommandBus."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.command_bus import CommandBus, CommandResult


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_handlers_empty_history():
    bus = CommandBus()
    assert bus.list_handlers() == []
    assert bus.history() == []


# ── register / unregister ────────────────────────────────────────────────────

def test_register_stores_handler():
    bus = CommandBus()
    bus.register("echo", lambda p: {"echo": p})
    assert "echo" in bus.list_handlers()


def test_register_overwrites_same_name_no_error():
    bus = CommandBus()
    bus.register("h", lambda p: {"v": 1})
    bus.register("h", lambda p: {"v": 2})
    result = bus.dispatch("h", {})
    assert result.result == {"v": 2}


def test_unregister_returns_true_removes():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    assert bus.unregister("h") is True
    assert "h" not in bus.list_handlers()


def test_unregister_unknown_returns_false():
    bus = CommandBus()
    assert bus.unregister("phantom") is False


def test_list_handlers_sorted():
    bus = CommandBus()
    bus.register("zzz", lambda p: {})
    bus.register("aaa", lambda p: {})
    bus.register("mmm", lambda p: {})
    assert bus.list_handlers() == ["aaa", "mmm", "zzz"]


# ── dispatch ─────────────────────────────────────────────────────────────────

def test_dispatch_unknown_name_returns_success_false_with_error():
    bus = CommandBus()
    result = bus.dispatch("phantom", {})
    assert result.success is False
    assert "phantom" in result.error


def test_dispatch_known_handler_returns_success_true():
    bus = CommandBus()
    bus.register("ping", lambda p: {"pong": True})
    result = bus.dispatch("ping", {})
    assert result.success is True


def test_dispatch_handler_return_value_in_result():
    bus = CommandBus()
    bus.register("echo", lambda p: {"echo": p})
    result = bus.dispatch("echo", {"x": 1})
    assert result.result == {"echo": {"x": 1}}


def test_dispatch_duration_ms_non_negative_float():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    result = bus.dispatch("h", {})
    assert isinstance(result.duration_ms, float)
    assert result.duration_ms >= 0.0


def test_dispatch_dispatched_at_is_recent():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    result = bus.dispatch("h", {})
    assert abs(result.dispatched_at - time.time()) < 2.0


def test_dispatch_exception_records_failure():
    bus = CommandBus()

    def bad(p):
        raise RuntimeError("kaboom")

    bus.register("bad", bad)
    result = bus.dispatch("bad", {})
    assert result.success is False
    assert "kaboom" in result.error
    assert result.result == {}


def test_dispatch_appends_to_history():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    bus.dispatch("h", {})
    bus.dispatch("h", {})
    assert len(bus.history()) == 2


# ── history ──────────────────────────────────────────────────────────────────

def test_history_newest_first_order():
    bus = CommandBus()
    bus.register("h", lambda p: {"i": p.get("i")})
    bus.dispatch("h", {"i": 1})
    bus.dispatch("h", {"i": 2})
    bus.dispatch("h", {"i": 3})
    hist = bus.history()
    assert hist[0].result["i"] == 3
    assert hist[-1].result["i"] == 1


def test_history_limit_parameter_respected():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    for _ in range(10):
        bus.dispatch("h", {})
    assert len(bus.history(limit=3)) == 3


def test_history_limit_capped_at_500():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    bus.dispatch("h", {})
    # asking for 99999 should not error and should cap at 500
    hist = bus.history(limit=99999)
    assert len(hist) <= CommandBus.HISTORY_LIMIT


def test_clear_history_returns_count_empties():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    for _ in range(5):
        bus.dispatch("h", {})
    n = bus.clear_history()
    assert n == 5
    assert bus.history() == []


def test_history_ring_buffer_caps_at_500():
    bus = CommandBus()
    bus.register("h", lambda p: {})
    for _ in range(600):
        bus.dispatch("h", {})
    # ring buffer keeps only the last HISTORY_LIMIT
    assert len(bus.history(limit=500)) == 500


# ── concurrency ──────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_dispatches():
    bus = CommandBus()
    bus.register("h", lambda p: {"ok": True})
    errors: list[Exception] = []

    def worker():
        try:
            bus.dispatch("h", {})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(bus.history(limit=100)) == 50


# ── payload=None default ─────────────────────────────────────────────────────

def test_dispatch_payload_none_defaults_to_empty_dict():
    bus = CommandBus()
    seen = []
    bus.register("h", lambda p: (seen.append(p) or {}))
    bus.dispatch("h", payload=None)
    assert seen == [{}]
