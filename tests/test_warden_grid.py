"""WARDEN GRID tests — thresholds, incidents, monitor, HTTP API."""

from __future__ import annotations

import json
import time
import urllib.request

import pytest

from pradyos.warden_grid.incidents import (
    Incident,
    IncidentSeverity,
    IncidentStore,
    signature,
)
from pradyos.warden_grid.monitor import WardenMonitor
from pradyos.warden_grid.thresholds import Thresholds


def test_incident_store_coalesces():
    s = IncidentStore()
    inc1, new1 = s.raise_("cpu", "threshold", IncidentSeverity.WARN, "cpu hot")
    inc2, new2 = s.raise_("cpu", "threshold", IncidentSeverity.WARN, "cpu hot")
    assert new1 is True
    assert new2 is False
    assert inc1.incident_id == inc2.incident_id
    assert inc2.occurrences == 2


def test_incident_severity_escalates_monotonically():
    s = IncidentStore()
    inc, _ = s.raise_("ram", "threshold", IncidentSeverity.WARN, "warn")
    s.raise_("ram", "threshold", IncidentSeverity.CRIT, "crit")
    assert inc.severity is IncidentSeverity.CRIT
    # WARN after CRIT should not de-escalate
    s.raise_("ram", "threshold", IncidentSeverity.WARN, "warn again")
    assert inc.severity is IncidentSeverity.CRIT


def test_incident_resolve_by_signature():
    s = IncidentStore()
    inc, _ = s.raise_("disk", "threshold", IncidentSeverity.WARN, "disk", target="/x")
    sig = signature("disk", "threshold", "/x")
    resolved = s.resolve(sig)
    assert resolved is not None
    assert resolved.is_open is False


def test_thresholds_env_override(monkeypatch):
    monkeypatch.setenv("PRADYOS_THRESHOLD_CPU_WARN", "33")
    t = Thresholds()
    assert t.cpu_warn == 33.0


def test_monitor_collects_snapshot(isolated_audit, isolated_bus):
    mon = WardenMonitor(audit=isolated_audit, bus=isolated_bus, host="127.0.0.1", port=_free_port())
    snap = mon.latest_snapshot()
    assert snap.cpu_count > 0
    assert snap.ram_total_mb > 0
    assert snap.hostname
    # No HTTP started in this lightweight path


def test_monitor_classify_raises_incident(isolated_audit, isolated_bus, monkeypatch):
    t = Thresholds()
    t.cpu_warn = 0.0   # force a warn
    t.cpu_crit = 200.0
    mon = WardenMonitor(thresholds=t, audit=isolated_audit, bus=isolated_bus,
                        host="127.0.0.1", port=_free_port())
    snap = mon._collect()
    mon._classify(snap)
    opens = mon.incidents.open_incidents()
    assert any(i.component == "cpu" for i in opens)


def test_monitor_http_endpoints(isolated_audit, isolated_bus):
    port = _free_port()
    mon = WardenMonitor(audit=isolated_audit, bus=isolated_bus,
                        host="127.0.0.1", port=port)
    mon.start()
    try:
        time.sleep(0.4)  # let poll prime
        # /ping
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=2) as r:
            data = json.loads(r.read())
            assert data["ok"] is True
        # /health
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            health = json.loads(r.read())
            assert "cpu_percent" in health
            assert "ram_percent" in health
        # /incidents
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/incidents", timeout=2) as r:
            inc = json.loads(r.read())
            assert "open" in inc
        # /thresholds
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/thresholds", timeout=2) as r:
            th = json.loads(r.read())
            assert "cpu_warn" in th
    finally:
        mon.stop()


def test_monitor_service_failure_raises(isolated_audit, isolated_bus):
    mon = WardenMonitor(
        watched_services=["__definitely_not_running__xyz"],
        audit=isolated_audit, bus=isolated_bus,
        host="127.0.0.1", port=_free_port(),
    )
    snap = mon._collect()
    mon._classify(snap)
    opens = mon.incidents.open_incidents()
    assert any(i.component == "service" for i in opens)


# ---------- helpers ----------

def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
