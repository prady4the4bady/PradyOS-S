"""Tests for pradyos.core.healthcheck — HealthProbe, HealthRegistry, /api/health.

All tests fully self-contained with mocks and TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.healthcheck import (
    HealthProbe,
    HealthRegistry,
    get_health_registry,
    reset_health_registry_for_tests,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Reset the global singleton before each test."""
    reset_health_registry_for_tests()
    yield
    reset_health_registry_for_tests()


def _ok_probe(name: str = "test") -> HealthProbe:
    return HealthProbe(name=name, status="ok", latency_ms=1.0)


def _degraded_probe(name: str = "test") -> HealthProbe:
    return HealthProbe(name=name, status="degraded", latency_ms=5.0, detail="slow")


def _down_probe(name: str = "test") -> HealthProbe:
    return HealthProbe(name=name, status="down", latency_ms=0.0, detail="unreachable")


# ---------------------------------------------------------------------------
# HealthProbe
# ---------------------------------------------------------------------------


def test_health_probe_defaults():
    p = HealthProbe(name="db", status="ok", latency_ms=2.5)
    assert p.detail == ""


def test_health_probe_dict():
    p = HealthProbe(name="cache", status="degraded", latency_ms=12.3, detail="slow")
    d = p.dict()
    assert d["name"] == "cache"
    assert d["status"] == "degraded"
    assert d["latency_ms"] == 12.3
    assert d["detail"] == "slow"


# ---------------------------------------------------------------------------
# HealthRegistry — registration
# ---------------------------------------------------------------------------


def test_register_and_run_all():
    reg = HealthRegistry()
    reg.register("svc_a", lambda: _ok_probe("svc_a"))
    reg.register("svc_b", lambda: _ok_probe("svc_b"))

    results = reg.run_all()
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"svc_a", "svc_b"}


def test_register_overwrites_existing():
    reg = HealthRegistry()
    reg.register("svc", lambda: _ok_probe("svc"))
    reg.register("svc", lambda: _down_probe("svc"))  # overwrite

    results = reg.run_all()
    assert len(results) == 1
    assert results[0].status == "down"


def test_unregister_removes_probe():
    reg = HealthRegistry()
    reg.register("svc", lambda: _ok_probe("svc"))
    reg.unregister("svc")
    assert reg.run_all() == []


def test_unregister_absent_probe_noop():
    reg = HealthRegistry()
    reg.unregister("nonexistent")  # must not raise


# ---------------------------------------------------------------------------
# HealthRegistry — run_all exception handling
# ---------------------------------------------------------------------------


def test_exception_in_probe_returns_down():
    reg = HealthRegistry()

    def boom() -> HealthProbe:
        raise RuntimeError("kaboom")

    reg.register("exploding", boom)
    results = reg.run_all()
    assert len(results) == 1
    p = results[0]
    assert p.name == "exploding"
    assert p.status == "down"
    assert "kaboom" in p.detail


def test_run_all_continues_after_exception():
    reg = HealthRegistry()

    def boom() -> HealthProbe:
        raise ValueError("bad")

    reg.register("fails", boom)
    reg.register("ok", lambda: _ok_probe("ok"))

    results = reg.run_all()
    assert len(results) == 2
    statuses = {r.name: r.status for r in results}
    assert statuses["fails"] == "down"
    assert statuses["ok"] == "ok"


def test_run_all_empty_registry():
    reg = HealthRegistry()
    assert reg.run_all() == []


# ---------------------------------------------------------------------------
# HealthRegistry — overall()
# ---------------------------------------------------------------------------


def test_overall_all_ok():
    reg = HealthRegistry()
    reg.register("a", lambda: _ok_probe("a"))
    reg.register("b", lambda: _ok_probe("b"))
    assert reg.overall() == "ok"


def test_overall_degraded_when_any_degraded():
    reg = HealthRegistry()
    reg.register("a", lambda: _ok_probe("a"))
    reg.register("b", lambda: _degraded_probe("b"))
    assert reg.overall() == "degraded"


def test_overall_down_when_any_down():
    reg = HealthRegistry()
    reg.register("a", lambda: _ok_probe("a"))
    reg.register("b", lambda: _degraded_probe("b"))
    reg.register("c", lambda: _down_probe("c"))
    assert reg.overall() == "down"


def test_overall_down_beats_degraded():
    reg = HealthRegistry()
    reg.register("a", lambda: _degraded_probe("a"))
    reg.register("b", lambda: _down_probe("b"))
    assert reg.overall() == "down"


def test_overall_empty_registry_is_ok():
    reg = HealthRegistry()
    assert reg.overall() == "ok"


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


def test_get_health_registry_returns_singleton():
    r1 = get_health_registry()
    r2 = get_health_registry()
    assert r1 is r2


def test_reset_creates_fresh_registry():
    reg1 = get_health_registry()
    reg1.register("probe", lambda: _ok_probe())
    assert len(reg1.run_all()) == 1

    reg2 = reset_health_registry_for_tests()
    assert len(reg2.run_all()) == 0
    assert reg2 is not reg1


# ---------------------------------------------------------------------------
# /api/health endpoint via TestClient
# ---------------------------------------------------------------------------


def _make_test_app(health_reg=None):
    from pradyos.sovereign_web import create_app
    return create_app(health_registry=health_reg)


def test_api_health_empty_registry():
    reg = HealthRegistry()
    app = _make_test_app(health_reg=reg)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["probes"] == []


def test_api_health_with_ok_probe():
    reg = HealthRegistry()
    reg.register("web", lambda: HealthProbe(name="web", status="ok", latency_ms=2.0))
    app = _make_test_app(health_reg=reg)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["probes"]) == 1
    assert data["probes"][0]["name"] == "web"
    assert data["probes"][0]["status"] == "ok"


def test_api_health_reflects_down_status():
    reg = HealthRegistry()
    reg.register("db", lambda: HealthProbe(name="db", status="down", latency_ms=0.0))
    app = _make_test_app(health_reg=reg)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "down"


def test_api_health_graceful_when_registry_missing():
    """No health_registry passed — falls back to global singleton gracefully."""
    app = _make_test_app(health_reg=None)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "probes" in data
