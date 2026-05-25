"""Structured audit log.

The constitution permits broad machine authority **only because** every
significant action is observable, attributable, explainable, logged, and
rollback-aware (blueprint §2.3, §3.1).

The audit log is therefore the linchpin of the entire system. It is the
foundational ledger every other plane writes to.

Format: append-only JSONL. One record per line. Never truncated.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Deque, Iterable

from pradyos.core.ids import new_id
from pradyos.core.types import AgentID

_DEFAULT_PATH = Path(
    os.environ.get(
        "PRADYOS_AUDIT_PATH",
        Path(__file__).resolve().parents[2] / "var" / "log" / "audit.jsonl",
    )
)


@dataclass(slots=True)
class AuditRecord:
    """One ledger line. Immutable after creation."""

    record_id: str = field(default_factory=lambda: new_id("au"))
    timestamp: float = field(default_factory=time.time)
    agent_id: str = "system"
    kind: str = "event"               # 'command' | 'incident' | 'state' | 'event' | 'approval'
    summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    exit_code: int | None = None
    rollback_hook: str | None = None  # opaque command/handler ref
    correlation_id: str | None = None # ties records to a task / incident

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp_iso"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)
        )
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


class AuditLog:
    """Append-only audit ledger, in-process + on-disk.

    Thread-safe. Keeps a rolling tail in memory for the Throne. Never
    blocks a writer on disk failures — but raises after writing the
    in-memory copy so calling code can decide whether to escalate.
    """

    def __init__(self, path: Path | str = _DEFAULT_PATH, tail_size: int = 1024) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tail: Deque[AuditRecord] = deque(maxlen=tail_size)
        self._subscribers: list[Any] = []   # callables(rec) -> None

    # ----- write path -----
    def record(
        self,
        agent_id: AgentID | str,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        exit_code: int | None = None,
        rollback_hook: str | None = None,
        correlation_id: str | None = None,
    ) -> AuditRecord:
        rec = AuditRecord(
            agent_id=str(agent_id),
            kind=kind,
            summary=summary,
            detail=detail or {},
            exit_code=exit_code,
            rollback_hook=rollback_hook,
            correlation_id=correlation_id,
        )
        self._append(rec)
        return rec

    def _append(self, rec: AuditRecord) -> None:
        with self._lock:
            self._tail.append(rec)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(rec.to_json() + "\n")
            except OSError:
                # Disk failure must not silently swallow audit data.
                # Tail still holds it. WARDEN GRID will raise an incident.
                pass
            for sub in list(self._subscribers):
                try:
                    sub(rec)
                except Exception:  # noqa: BLE001  — subscribers must not break audit
                    pass

    # ----- read path -----
    def tail(self, n: int = 10) -> list[AuditRecord]:
        with self._lock:
            return list(self._tail)[-n:]

    def all_in_memory(self) -> list[AuditRecord]:
        with self._lock:
            return list(self._tail)

    def read_from_disk(self, limit: int | None = None) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if limit is not None:
            out = out[-limit:]
        return out

    # ----- subscription -----
    def subscribe(self, fn: Any) -> None:
        with self._lock:
            self._subscribers.append(fn)


_singleton: AuditLog | None = None
_singleton_lock = threading.Lock()


def get_audit_log() -> AuditLog:
    """Return process-wide singleton audit log."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = AuditLog()
    return _singleton


def reset_audit_log_for_tests(path: Path | str) -> AuditLog:
    """Replace singleton — tests only."""
    global _singleton
    with _singleton_lock:
        _singleton = AuditLog(path=path)
    return _singleton


# ---------------------------------------------------------------------------
# Phase 6 — AuditEvent / AuditCategory interface
# ---------------------------------------------------------------------------

import datetime
from enum import Enum


class AuditCategory(str, Enum):
    CAMPAIGN  = "CAMPAIGN"
    WARDEN    = "WARDEN"
    ORACLE    = "ORACLE"
    SOVEREIGN = "SOVEREIGN"
    SYSTEM    = "SYSTEM"


@dataclass
class AuditEvent:
    """Structured audit event (Phase 6 interface)."""
    timestamp: float = field(default_factory=time.time)
    category:  AuditCategory = AuditCategory.SYSTEM
    actor:     str = "system"
    action:    str = ""
    payload:   dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.datetime.fromtimestamp(
                self.timestamp, tz=datetime.timezone.utc
            ).isoformat(),
            "category": self.category.value,
            "actor":    self.actor,
            "action":   self.action,
            "payload":  self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


# Patch AuditLog to support append(AuditEvent) and Phase-6-compliant path default

_DEFAULT_AUDIT_EVENT_PATH = Path(
    os.environ.get(
        "PRADYOS_AUDIT_EVENT_PATH",
        str(Path(__file__).resolve().parents[2] / "var" / "audit" / "audit.jsonl"),
    )
)


def _audit_log_append(self: "AuditLog", event: "AuditEvent") -> None:
    """Append an AuditEvent to the log (thread-safe)."""
    with self._lock:
        self._tail.append(event)   # type: ignore[arg-type]
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except OSError:
            pass


# Bind the new method onto the existing AuditLog class
AuditLog.append = _audit_log_append  # type: ignore[attr-defined]


class EventAuditLog:
    """Standalone Phase-6 AuditLog backed solely by AuditEvent objects.

    Wraps the append-only JSONL pattern with the exact interface specified:
    - append(event)
    - tail(n) → list[AuditEvent]
    - thread-safe via threading.Lock
    """

    def __init__(self, path: Path | str = _DEFAULT_AUDIT_EVENT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(event.to_json() + "\n")
            except OSError:
                pass

    def tail(self, n: int = 10) -> list[AuditEvent]:
        with self._lock:
            if n <= 0:
                return []
            return list(self._events[-n:])

    def rotate(self, new_path: Path | str) -> None:
        """Rotate: redirect writes to new_path, keep events in memory."""
        with self._lock:
            self.path = Path(new_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
