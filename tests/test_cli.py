"""Phase 42C — 20 tests for pradyos.cli.

All HTTP calls mocked via unittest.mock.patch on urllib.request.urlopen.
"""
from __future__ import annotations

import io
import json
import urllib.error
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from pradyos import cli


# ── mock helpers ──────────────────────────────────────────────────────────────

@contextmanager
def _mock_urlopen(response_data: dict, status: int = 200):
    """Patches urllib.request.urlopen to return JSON bytes in a CM."""
    body = json.dumps(response_data).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp) as mock:
        yield mock


@contextmanager
def _mock_urlopen_404():
    """Patches urlopen to raise HTTPError 404."""
    err = urllib.error.HTTPError(
        url="http://x", code=404, msg="Not Found",
        hdrs=None, fp=io.BytesIO(b""),
    )
    with patch("urllib.request.urlopen", side_effect=err) as mock:
        yield mock


# ── run_status ────────────────────────────────────────────────────────────────

def test_run_status_prints_os_version(capsys):
    with _mock_urlopen({
        "os_version": "0.42.0", "uptime_seconds": 1.5,
        "modules": {"x": {"present": True, "summary": {"a": 1}}},
    }):
        cli.run_status("http://x")
    out = capsys.readouterr().out
    assert "0.42.0" in out


def test_run_status_prints_uptime(capsys):
    with _mock_urlopen({
        "os_version": "0.42.0", "uptime_seconds": 99.99,
        "modules": {},
    }):
        cli.run_status("http://x")
    assert "99.99" in capsys.readouterr().out


def test_run_status_prints_all_module_names(capsys):
    names = ["health_scorecard", "signal_aggregator", "task_scheduler",
             "memory_store", "healing_monitor", "snapshot_store",
             "reactor_engine", "state_manager", "watchpoint_system",
             "correlation_engine", "integration_bus"]
    modules = {n: {"present": False, "summary": {}} for n in names}
    with _mock_urlopen({"os_version": "0.42.0", "uptime_seconds": 0, "modules": modules}):
        cli.run_status("http://x")
    out = capsys.readouterr().out
    for n in names:
        assert n in out, f"Missing module {n}"


def test_run_status_handles_missing_modules_key(capsys):
    with _mock_urlopen({"os_version": "0.42.0", "uptime_seconds": 0}):
        cli.run_status("http://x")
    # should not crash; no module rows printed
    assert "0.42.0" in capsys.readouterr().out


# ── run_tick ──────────────────────────────────────────────────────────────────

def test_run_tick_prints_ticks_count(capsys):
    with _mock_urlopen({"ticks": [{"a": 1}, {"b": 2}], "healed": [], "reactions": []}):
        cli.run_tick("http://x")
    assert "ticks:     2" in capsys.readouterr().out


def test_run_tick_prints_healed_count(capsys):
    with _mock_urlopen({"ticks": [], "healed": [{"x": 1}], "reactions": []}):
        cli.run_tick("http://x")
    assert "healed:    1" in capsys.readouterr().out


def test_run_tick_prints_reactions_count(capsys):
    with _mock_urlopen({"ticks": [], "healed": [], "reactions": [{"a": 1}, {"b": 2}, {"c": 3}]}):
        cli.run_tick("http://x")
    assert "reactions: 3" in capsys.readouterr().out


# ── run_signals ───────────────────────────────────────────────────────────────

def test_run_signals_prints_signal_name(capsys):
    with _mock_urlopen({"signals": [{"name": "cpu", "count": 5, "latest": 80.0}]}):
        cli.run_signals("http://x")
    assert "cpu" in capsys.readouterr().out


def test_run_signals_empty_list(capsys):
    with _mock_urlopen({"signals": []}):
        cli.run_signals("http://x")
    assert "(no signals)" in capsys.readouterr().out


# ── run_signal_detail ────────────────────────────────────────────────────────

def test_run_signal_detail_prints_count(capsys):
    with _mock_urlopen({
        "name": "cpu", "count": 10,
        "stats": {"min": 1.0, "max": 99.0, "mean": 50.0, "stddev": 10.0},
        "points": [],
    }):
        cli.run_signal_detail("http://x", "cpu")
    assert "count:  10" in capsys.readouterr().out


def test_run_signal_detail_prints_stats(capsys):
    with _mock_urlopen({
        "name": "cpu", "count": 3,
        "stats": {"min": 1.0, "max": 9.0, "mean": 5.0, "stddev": 2.5},
        "points": [],
    }):
        cli.run_signal_detail("http://x", "cpu")
    out = capsys.readouterr().out
    assert "min=1.0" in out
    assert "max=9.0" in out


def test_run_signal_detail_unknown_signal_empty_points(capsys):
    with _mock_urlopen({"name": "missing", "count": 0, "stats": None, "points": []}):
        cli.run_signal_detail("http://x", "missing")
    out = capsys.readouterr().out
    assert "count:  0" in out
    assert "(none)" in out


# ── run_memory_get / set ──────────────────────────────────────────────────────

def test_run_memory_get_prints_value(capsys):
    with _mock_urlopen({"key": "k1", "value": "hello", "tags": [], "ttl": None}):
        cli.run_memory_get("http://x", "k1")
    out = capsys.readouterr().out
    assert "value: hello" in out


def test_run_memory_get_404_prints_not_found(capsys):
    with _mock_urlopen_404():
        cli.run_memory_get("http://x", "phantom")
    assert "not found" in capsys.readouterr().out


def test_run_memory_set_prints_stored_confirmation(capsys):
    with _mock_urlopen({"key": "k1", "value": "v", "tags": [], "ttl": 60}):
        cli.run_memory_set("http://x", "k1", "v", ttl=60)
    out = capsys.readouterr().out
    assert "stored:" in out
    assert "k1" in out


# ── run_heartbeat ─────────────────────────────────────────────────────────────

def test_run_heartbeat_prints_running(capsys):
    with _mock_urlopen({"running": True, "tick_count": 5, "interval_seconds": 1.0}):
        cli.run_heartbeat("http://x")
    assert "running:          True" in capsys.readouterr().out


def test_run_heartbeat_prints_tick_count(capsys):
    with _mock_urlopen({"running": False, "tick_count": 42, "interval_seconds": 5.0}):
        cli.run_heartbeat("http://x")
    assert "tick_count:       42" in capsys.readouterr().out


# ── run_health ────────────────────────────────────────────────────────────────

def test_run_health_prints_score(capsys):
    with _mock_urlopen({"score": 92.5, "components": []}):
        cli.run_health("http://x")
    assert "score: 92.5" in capsys.readouterr().out


# ── _http_get / _http_post ────────────────────────────────────────────────────

def test_http_get_calls_urlopen_with_correct_url():
    with _mock_urlopen({"ok": True}) as mock:
        cli._http_get("http://example/api/x")
    # The first positional arg to urlopen was the Request
    called_req = mock.call_args[0][0]
    assert called_req.full_url == "http://example/api/x"


def test_http_post_sends_content_type_json():
    with _mock_urlopen({"ok": True}) as mock:
        cli._http_post("http://example/api/x", {"a": 1})
    called_req = mock.call_args[0][0]
    # header keys are case-folded to title case by urllib internals
    assert any(h.lower() == "content-type" for h in called_req.headers)
    assert "application/json" in called_req.headers.get("Content-type", "")
