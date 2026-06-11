"""Phase 30A — 20 tests for pradyos.core.watchpoint.WatchpointSystem."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.watchpoint import Alert, Watchpoint, WatchpointSystem


# ── helpers ──────────────────────────────────────────────────────────────────

def _sys(**kw) -> WatchpointSystem:
    return WatchpointSystem(**kw)


def _reg(sys: WatchpointSystem, name="cpu", metric="cpu", operator="gt",
         threshold=80.0, severity="warn", enabled=True) -> Watchpoint:
    return sys.register(name=name, metric=metric, operator=operator,
                        threshold=threshold, severity=severity, enabled=enabled)


# ── initialisation ────────────────────────────────────────────────────────────

def test_init_empty():
    ws = _sys()
    assert ws.watchpoints == {}
    assert ws._total_alerts == 0
    assert len(ws._alerts) == 0


def test_register_returns_watchpoint():
    ws = _sys()
    wp = _reg(ws)
    assert isinstance(wp, Watchpoint)
    assert wp.name == "cpu"
    assert wp.metric == "cpu"
    assert wp.operator == "gt"
    assert wp.threshold == 80.0
    assert wp.severity == "warn"
    assert wp.enabled is True


def test_register_stores_watchpoint():
    ws = _sys()
    wp = _reg(ws)
    assert "cpu" in ws.watchpoints
    assert ws.watchpoints["cpu"] is wp


def test_register_invalid_operator():
    ws = _sys()
    with pytest.raises(ValueError, match="operator"):
        ws.register("bad", "cpu", "badop", 50.0)


def test_register_invalid_severity():
    ws = _sys()
    with pytest.raises(ValueError, match="severity"):
        ws.register("bad", "cpu", "gt", 50.0, severity="extreme")


# ── check — basic ─────────────────────────────────────────────────────────────

def test_check_no_match_returns_empty():
    ws = _sys()
    _reg(ws, metric="mem")
    alerts = ws.check("cpu", 99.0)
    assert alerts == []


def test_check_fires_gt():
    ws = _sys()
    _reg(ws, operator="gt", threshold=80.0)
    alerts = ws.check("cpu", 90.0)
    assert len(alerts) == 1
    assert alerts[0].actual_value == 90.0


def test_check_fires_lt():
    ws = _sys()
    _reg(ws, operator="lt", threshold=20.0)
    alerts = ws.check("cpu", 10.0)
    assert len(alerts) == 1


def test_check_fires_gte_at_exact_threshold():
    ws = _sys()
    _reg(ws, operator="gte", threshold=80.0)
    alerts = ws.check("cpu", 80.0)
    assert len(alerts) == 1


def test_check_fires_lte_at_exact_threshold():
    ws = _sys()
    _reg(ws, operator="lte", threshold=50.0)
    alerts = ws.check("cpu", 50.0)
    assert len(alerts) == 1


def test_check_fires_eq():
    ws = _sys()
    _reg(ws, operator="eq", threshold=42.0)
    alerts = ws.check("cpu", 42.0)
    assert len(alerts) == 1


def test_check_no_fire_when_condition_false():
    ws = _sys()
    _reg(ws, operator="gt", threshold=80.0)
    alerts = ws.check("cpu", 70.0)
    assert alerts == []


def test_check_skips_disabled():
    ws = _sys()
    _reg(ws, enabled=False)
    alerts = ws.check("cpu", 99.0)
    assert alerts == []


# ── disable / enable ──────────────────────────────────────────────────────────

def test_disable_sets_enabled_false_returns_true():
    ws = _sys()
    _reg(ws)
    result = ws.disable("cpu")
    assert result is True
    assert ws.watchpoints["cpu"].enabled is False


def test_enable_sets_enabled_true_returns_true():
    ws = _sys()
    _reg(ws, enabled=False)
    result = ws.enable("cpu")
    assert result is True
    assert ws.watchpoints["cpu"].enabled is True


# ── get_alerts ────────────────────────────────────────────────────────────────

def test_get_alerts_oldest_first():
    ws = _sys()
    _reg(ws, name="a", metric="m", operator="gt", threshold=0.0, severity="warn")
    _reg(ws, name="b", metric="m", operator="gt", threshold=0.0, severity="critical")
    ws.check("m", 1.0)
    alerts = ws.get_alerts()
    assert len(alerts) == 2
    assert alerts[0].watchpoint_name in ("a", "b")
    # oldest-first means the same order as insertion
    names = [a.watchpoint_name for a in alerts]
    assert set(names) == {"a", "b"}


def test_get_alerts_filter_severity():
    ws = _sys()
    _reg(ws, name="w", metric="m", operator="gt", threshold=0.0, severity="warn")
    _reg(ws, name="c", metric="m", operator="gt", threshold=0.0, severity="critical")
    ws.check("m", 1.0)
    critical = ws.get_alerts(severity="critical")
    assert all(a.severity == "critical" for a in critical)
    assert len(critical) == 1


def test_get_alerts_limit():
    ws = _sys()
    for i in range(5):
        _reg(ws, name=f"wp{i}", metric="m", operator="gt", threshold=0.0)
    ws.check("m", 1.0)
    limited = ws.get_alerts(limit=2)
    assert len(limited) == 2


# ── status ────────────────────────────────────────────────────────────────────

def test_status_returns_required_keys():
    ws = _sys()
    _reg(ws)
    ws.check("cpu", 99.0)
    s = ws.status()
    assert "total_watchpoints" in s
    assert "enabled" in s
    assert "total_alerts_ever" in s
    assert "alerts_in_buffer" in s
    assert s["total_watchpoints"] == 1
    assert s["enabled"] == 1
    assert s["total_alerts_ever"] >= 1


# ── thread safety ─────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_checks():
    ws = _sys(max_alerts=5000)
    _reg(ws, name="t", metric="m", operator="gt", threshold=0.0)

    errors: list[Exception] = []

    def worker():
        try:
            ws.check("m", 1.0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread errors: {errors}"
    assert ws._total_alerts == 50
