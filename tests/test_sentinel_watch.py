"""SENTINEL WATCH tests — red-team posture verified against ground truth."""

from __future__ import annotations

import pytest

from pradyos.sentinel_watch import SentinelError, SentinelWatch


def _s() -> SentinelWatch:
    return SentinelWatch()


def test_register_and_secure_posture():
    s = _s()
    s.register_scenario("escape-kernel", "kernel-boundary")
    p = s.posture()
    assert p["scenarios"] == 1 and p["open_breaches"] == 0
    assert p["threat_level"] == "secure" and p["response"] == "log"


def test_blocked_run_keeps_secure():
    s = _s()
    s.register_scenario("a2a-inject", "a2a-ingress")
    sc = s.run("a2a-inject", breached=False)
    assert sc["runs"] == 1 and sc["breaches"] == 0 and sc["open_breach"] is False
    assert s.posture()["threat_level"] == "secure"


def test_breach_opens_and_elevates():
    s = _s()
    s.register_scenario("x", "b")
    sc = s.run("x", breached=True, note="leaked via shared mem")
    assert sc["breaches"] == 1 and sc["open_breach"] is True
    p = s.posture()
    assert p["open_breaches"] == 1 and p["threat_level"] == "elevated"
    assert p["response"] == "quarantine"


def test_critical_at_three_open_breaches():
    s = _s()
    for i in range(3):
        s.register_scenario(f"s{i}", "b")
        s.run(f"s{i}", breached=True)
    p = s.posture()
    assert p["open_breaches"] == 3 and p["threat_level"] == "critical"
    assert p["response"] == "safe_stop_escalate"


def test_patch_closes_breach_back_to_secure():
    s = _s()
    s.register_scenario("x", "b")
    s.run("x", breached=True)
    assert s.posture()["threat_level"] == "elevated"
    s.patch("x")
    assert s.posture()["threat_level"] == "secure"
    assert s.scenarios()[0]["open_breach"] is False


def test_patch_without_breach_raises():
    s = _s()
    s.register_scenario("x", "b")
    with pytest.raises(SentinelError):
        s.patch("x")


def test_validation_and_unknown():
    s = _s()
    with pytest.raises(SentinelError):
        s.register_scenario("", "b")
    with pytest.raises(SentinelError):
        s.run("nope", breached=True)
    s.register_scenario("x", "b")
    with pytest.raises(SentinelError):
        s.run("x", breached="yes")  # type: ignore[arg-type]


def test_history_and_exercises_count():
    s = _s()
    s.register_scenario("x", "b")
    s.run("x", breached=False)
    s.run("x", breached=True)
    s.patch("x")
    assert s.posture()["exercises"] == 2
    hist = s.history()
    assert len(hist) == 3 and hist[-1].get("patched") is True


def test_reset():
    s = _s()
    s.register_scenario("x", "b")
    s.run("x", breached=True)
    s.reset()
    assert s.posture()["scenarios"] == 0 and s.history() == []
