"""Tests for Phase 6 AuditEvent / EventAuditLog interface.

Covers: write, tail, rotate, thread-safety.
"""

from __future__ import annotations

import datetime
import json
import threading
import time
from pathlib import Path

import pytest

from pradyos.core.audit import AuditCategory, AuditEvent, EventAuditLog


# ---------------------------------------------------------------------------
# AuditEvent dataclass
# ---------------------------------------------------------------------------


def test_audit_event_defaults():
    ev = AuditEvent()
    assert ev.category == AuditCategory.SYSTEM
    assert ev.actor == "system"
    assert ev.action == ""
    assert isinstance(ev.payload, dict)
    assert ev.timestamp > 0


def test_audit_event_all_categories():
    for cat in AuditCategory:
        ev = AuditEvent(category=cat, actor="test", action="ping")
        assert ev.category == cat


def test_audit_event_to_dict_has_iso():
    ev = AuditEvent(
        timestamp=0.0,
        category=AuditCategory.CAMPAIGN,
        actor="engine",
        action="start",
        payload={"id": "c1"},
    )
    d = ev.to_dict()
    assert d["category"] == "CAMPAIGN"
    assert d["actor"] == "engine"
    assert d["action"] == "start"
    assert d["payload"] == {"id": "c1"}
    assert "1970-01-01" in d["timestamp_iso"]


def test_audit_event_to_json_valid():
    ev = AuditEvent(category=AuditCategory.ORACLE, actor="oracle", action="plan")
    raw = ev.to_json()
    parsed = json.loads(raw)
    assert parsed["category"] == "ORACLE"


# ---------------------------------------------------------------------------
# EventAuditLog — write and tail
# ---------------------------------------------------------------------------


def test_event_audit_log_append_and_tail(tmp_path):
    log = EventAuditLog(path=tmp_path / "audit.jsonl")
    for i in range(5):
        log.append(AuditEvent(
            category=AuditCategory.SYSTEM,
            actor="test",
            action=f"action_{i}",
            payload={"i": i},
        ))
    assert len(log) == 5
    tail = log.tail(3)
    assert len(tail) == 3
    assert tail[-1].action == "action_4"
    assert tail[0].action == "action_2"


def test_event_audit_log_tail_larger_than_size(tmp_path):
    log = EventAuditLog(path=tmp_path / "audit.jsonl")
    log.append(AuditEvent(action="only"))
    tail = log.tail(100)
    assert len(tail) == 1
    assert tail[0].action == "only"


def test_event_audit_log_tail_empty(tmp_path):
    log = EventAuditLog(path=tmp_path / "audit.jsonl")
    assert log.tail(5) == []


def test_event_audit_log_writes_jsonl(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = EventAuditLog(path=p)
    log.append(AuditEvent(category=AuditCategory.WARDEN, actor="warden", action="alert"))
    log.append(AuditEvent(category=AuditCategory.SOVEREIGN, actor="sovereign", action="approve"))

    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["category"] == "WARDEN"
    assert first["actor"] == "warden"
    second = json.loads(lines[1])
    assert second["category"] == "SOVEREIGN"


def test_event_audit_log_all_categories_written(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = EventAuditLog(path=p)
    for cat in AuditCategory:
        log.append(AuditEvent(category=cat, actor="x", action="y"))
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(list(AuditCategory))
    cats_written = {json.loads(l)["category"] for l in lines}
    assert cats_written == {c.value for c in AuditCategory}


# ---------------------------------------------------------------------------
# Rotate
# ---------------------------------------------------------------------------


def test_event_audit_log_rotate(tmp_path):
    p1 = tmp_path / "audit1.jsonl"
    p2 = tmp_path / "audit2.jsonl"
    log = EventAuditLog(path=p1)
    log.append(AuditEvent(action="before_rotate"))
    log.rotate(p2)
    log.append(AuditEvent(action="after_rotate"))

    # p1 has 1 line, p2 has 1 line
    assert len(p1.read_text(encoding="utf-8").strip().splitlines()) == 1
    assert len(p2.read_text(encoding="utf-8").strip().splitlines()) == 1
    # In-memory tail has both
    assert len(log) == 2


# ---------------------------------------------------------------------------
# Thread-safety
# ---------------------------------------------------------------------------


def test_event_audit_log_thread_safe(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = EventAuditLog(path=p)
    N = 50
    errors = []

    def writer(actor: str) -> None:
        try:
            for i in range(N):
                log.append(AuditEvent(
                    category=AuditCategory.SYSTEM,
                    actor=actor,
                    action=f"op_{i}",
                ))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"t{j}",)) for j in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    assert len(log) == 4 * N

    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4 * N
    # All lines must be valid JSON
    for line in lines:
        json.loads(line)


def test_event_audit_log_tail_zero(tmp_path):
    log = EventAuditLog(path=tmp_path / "audit.jsonl")
    log.append(AuditEvent(action="x"))
    assert log.tail(0) == []
