"""Structured incident objects + a thread-safe in-memory store.

Each incident has a stable ``signature`` so the same recurring symptom
collapses into one open incident (instead of spamming the audit log).
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from pradyos.core.ids import new_id


class IncidentSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRIT = "CRIT"
    FATAL = "FATAL"


@dataclass(slots=True)
class Incident:
    incident_id: str
    signature: str
    severity: IncidentSeverity
    component: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    occurrences: int = 1
    resolved_at: float | None = None
    rollback_hook: str | None = None

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["is_open"] = self.is_open
        return d


def signature(component: str, kind: str, target: str = "") -> str:
    raw = f"{component}|{kind}|{target}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]  # short, stable


class IncidentStore:
    """Coalesces recurring incidents by signature."""

    def __init__(self) -> None:
        self._by_sig: dict[str, Incident] = {}
        self._lock = threading.Lock()

    def raise_(
        self,
        component: str,
        kind: str,
        severity: IncidentSeverity,
        summary: str,
        target: str = "",
        detail: dict[str, Any] | None = None,
        rollback_hook: str | None = None,
    ) -> tuple[Incident, bool]:
        """Raise or coalesce. Returns ``(incident, was_new)``."""
        sig = signature(component, kind, target)
        now = time.time()
        with self._lock:
            existing = self._by_sig.get(sig)
            if existing and existing.is_open:
                existing.last_seen = now
                existing.occurrences += 1
                if detail:
                    existing.detail.update(detail)
                # severity escalates monotonically while open
                if _sev_rank(severity) > _sev_rank(existing.severity):
                    existing.severity = severity
                return existing, False
            inc = Incident(
                incident_id=new_id("inc"),
                signature=sig,
                severity=severity,
                component=component,
                summary=summary,
                detail=detail or {},
                rollback_hook=rollback_hook,
            )
            self._by_sig[sig] = inc
            return inc, True

    def resolve(self, signature_or_id: str) -> Incident | None:
        with self._lock:
            inc = self._by_sig.get(signature_or_id)
            if inc is None:
                for cand in self._by_sig.values():
                    if cand.incident_id == signature_or_id:
                        inc = cand
                        break
            if inc and inc.is_open:
                inc.resolved_at = time.time()
            return inc

    def open_incidents(self) -> list[Incident]:
        with self._lock:
            return [i for i in self._by_sig.values() if i.is_open]

    def all(self) -> list[Incident]:
        with self._lock:
            return list(self._by_sig.values())


def _sev_rank(s: IncidentSeverity) -> int:
    return {"INFO": 0, "WARN": 1, "CRIT": 2, "FATAL": 3}[s.value]
