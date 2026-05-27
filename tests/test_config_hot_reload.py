"""Phase 21C — ConfigHotReloader unit tests (20 tests).

Uses tmp_path fixture for real temp files.
Config files are written as JSON (yaml.safe_load falls back to json.loads).

Coverage:
  1.  ReloadResult.to_dict() has required keys
  2.  ConfigHotReloader.load() returns ReloadResult
  3.  load() returns success=True for valid config file
  4.  load() with intent_rules section calls intent_engine.load_rules
  5.  load() with policy_rules section calls policy_engine.load_rules
  6.  load() with scheduler_jobs section calls scheduler.add_job for each job
  7.  load() skips missing sections gracefully
  8.  load() with missing components (None) skips those sections
  9.  load() returns success=False on file not found
 10.  load() returns error string on file not found
 11.  load() returns success=False on invalid JSON
 12.  status() returns dict with required keys
 13.  status() running=False before start()
 14.  last_result() returns None before any load
 15.  last_result() returns ReloadResult after load()
 16.  start() sets _running=True
 17.  stop() sets _running=False
 18.  start()/stop() cycle completes without error
 19.  load() changes list is a list
 20.  load() changes list contains change descriptions when sections applied
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from pradyos.core.config_hot_reload import ConfigHotReloader, ReloadResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_reloader(tmp_path: Path, **kwargs) -> tuple[ConfigHotReloader, Path]:
    cfg = tmp_path / "config.json"
    _write_json(cfg, {})
    r = ConfigHotReloader(cfg, **kwargs)
    return r, cfg


# ===========================================================================
# Test 1: ReloadResult.to_dict() has required keys
# ===========================================================================

def test_reload_result_to_dict_has_required_keys():
    rr = ReloadResult(success=True, timestamp=1.0)
    d = rr.to_dict()
    for key in ("success", "timestamp", "changes", "error"):
        assert key in d, f"missing key: {key}"


# ===========================================================================
# Test 2: ConfigHotReloader.load() returns ReloadResult
# ===========================================================================

def test_load_returns_reload_result(tmp_path):
    r, _ = _make_reloader(tmp_path)
    result = r.load()
    assert isinstance(result, ReloadResult)


# ===========================================================================
# Test 3: load() returns success=True for valid config file
# ===========================================================================

def test_load_success_true_for_valid_file(tmp_path):
    r, _ = _make_reloader(tmp_path)
    result = r.load()
    assert result.success is True


# ===========================================================================
# Test 4: load() with intent_rules calls intent_engine.load_rules
# ===========================================================================

def test_load_intent_rules_calls_load_rules(tmp_path):
    engine = MagicMock()
    r, cfg = _make_reloader(tmp_path, intent_engine=engine)
    rules = [{"action": "open_app", "priority": 5}]
    _write_json(cfg, {"intent_rules": rules})
    r.load()
    engine.load_rules.assert_called_once_with(rules)


# ===========================================================================
# Test 5: load() with policy_rules calls policy_engine.load_rules
# ===========================================================================

def test_load_policy_rules_calls_load_rules(tmp_path):
    engine = MagicMock()
    r, cfg = _make_reloader(tmp_path, policy_engine=engine)
    rules = [{"type": "constitutional_guard", "reason": "deny all"}]
    _write_json(cfg, {"policy_rules": rules})
    r.load()
    engine.load_rules.assert_called_once_with(rules)


# ===========================================================================
# Test 6: load() with scheduler_jobs calls scheduler.add_job for each job
# ===========================================================================

def test_load_scheduler_jobs_calls_add_job_for_each(tmp_path):
    sched = MagicMock()
    r, cfg = _make_reloader(tmp_path, scheduler=sched)
    jobs = [
        {"job_id": "j1", "cron_expr": "* * * * *"},
        {"job_id": "j2", "cron_expr": "0 * * * *"},
    ]
    _write_json(cfg, {"scheduler_jobs": jobs})
    r.load()
    assert sched.add_job.call_count == 2
    sched.add_job.assert_any_call(**jobs[0])
    sched.add_job.assert_any_call(**jobs[1])


# ===========================================================================
# Test 7: load() skips missing sections gracefully
# ===========================================================================

def test_load_skips_missing_sections(tmp_path):
    engine = MagicMock()
    r, cfg = _make_reloader(tmp_path, intent_engine=engine, policy_engine=engine)
    # Config has no intent_rules, policy_rules, or scheduler_jobs
    _write_json(cfg, {"other_key": "value"})
    result = r.load()
    assert result.success is True
    engine.load_rules.assert_not_called()


# ===========================================================================
# Test 8: load() with missing components (None) skips those sections
# ===========================================================================

def test_load_skips_sections_when_component_is_none(tmp_path):
    # All components are None (default)
    r, cfg = _make_reloader(tmp_path)
    _write_json(cfg, {
        "intent_rules": [{"action": "x"}],
        "scheduler_jobs": [{"job_id": "j1"}],
        "policy_rules": [{"type": "rate_limit"}],
    })
    result = r.load()
    # Should complete without error even though components are None
    assert result.success is True


# ===========================================================================
# Test 9: load() returns success=False on file not found
# ===========================================================================

def test_load_failure_on_missing_file(tmp_path):
    r = ConfigHotReloader(tmp_path / "nonexistent.json")
    result = r.load()
    assert result.success is False


# ===========================================================================
# Test 10: load() returns error string on file not found
# ===========================================================================

def test_load_error_string_on_missing_file(tmp_path):
    r = ConfigHotReloader(tmp_path / "nonexistent.json")
    result = r.load()
    assert isinstance(result.error, str)
    assert len(result.error) > 0


# ===========================================================================
# Test 11: load() returns success=False on invalid JSON
# ===========================================================================

def test_load_failure_on_invalid_json(tmp_path):
    cfg = tmp_path / "bad.json"
    cfg.write_text("{ this is not valid json !!!", encoding="utf-8")
    r = ConfigHotReloader(cfg)
    result = r.load()
    assert result.success is False


# ===========================================================================
# Test 12: status() returns dict with required keys
# ===========================================================================

def test_status_returns_dict_with_required_keys(tmp_path):
    r, _ = _make_reloader(tmp_path)
    s = r.status()
    for key in ("running", "config_path", "last_reload", "poll_interval"):
        assert key in s, f"missing key: {key}"


# ===========================================================================
# Test 13: status() running=False before start()
# ===========================================================================

def test_status_running_false_before_start(tmp_path):
    r, _ = _make_reloader(tmp_path)
    assert r.status()["running"] is False


# ===========================================================================
# Test 14: last_result() returns None before any load
# ===========================================================================

def test_last_result_none_before_load(tmp_path):
    r, _ = _make_reloader(tmp_path)
    assert r.last_result() is None


# ===========================================================================
# Test 15: last_result() returns ReloadResult after load()
# ===========================================================================

def test_last_result_returns_reload_result_after_load(tmp_path):
    r, _ = _make_reloader(tmp_path)
    r.load()
    lr = r.last_result()
    assert isinstance(lr, ReloadResult)


# ===========================================================================
# Test 16: start() sets _running=True
# ===========================================================================

def test_start_sets_running_true(tmp_path):
    r, _ = _make_reloader(tmp_path)
    r.start()
    try:
        assert r._running is True
    finally:
        r.stop()


# ===========================================================================
# Test 17: stop() sets _running=False
# ===========================================================================

def test_stop_sets_running_false(tmp_path):
    r, _ = _make_reloader(tmp_path)
    r.start()
    r.stop()
    assert r._running is False


# ===========================================================================
# Test 18: start()/stop() cycle completes without error
# ===========================================================================

def test_start_stop_cycle_no_error(tmp_path):
    r, _ = _make_reloader(tmp_path)
    r.start()
    time.sleep(0.05)
    r.stop()  # must not raise


# ===========================================================================
# Test 19: load() changes list is a list
# ===========================================================================

def test_load_changes_is_list(tmp_path):
    r, _ = _make_reloader(tmp_path)
    result = r.load()
    assert isinstance(result.changes, list)


# ===========================================================================
# Test 20: load() changes list contains descriptions when sections applied
# ===========================================================================

def test_load_changes_contains_descriptions(tmp_path):
    engine = MagicMock()
    sched = MagicMock()
    r, cfg = _make_reloader(tmp_path, intent_engine=engine, scheduler=sched)
    _write_json(cfg, {
        "intent_rules": [{"action": "x"}],
        "scheduler_jobs": [{"job_id": "j1"}],
    })
    result = r.load()
    assert result.success is True
    assert len(result.changes) >= 2
    # Each change description should be a non-empty string
    for ch in result.changes:
        assert isinstance(ch, str)
        assert len(ch) > 0
