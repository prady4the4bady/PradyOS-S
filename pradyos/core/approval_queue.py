from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalEntry:
    id: str
    action: str
    risk_level: str
    payload: dict
    reason: str | None
    status: ApprovalStatus
    requested_at: float
    resolved_at: float | None = None
    resolver_note: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "risk_level": self.risk_level,
            "payload": dict(self.payload),
            "reason": self.reason,
            "status": self.status.value,
            "requested_at": self.requested_at,
            "resolved_at": self.resolved_at,
            "resolver_note": self.resolver_note,
        }


def _risk_str(risk_level: Any) -> str:
    """Coerce risk_level to its string .value form (accepts enum or str)."""
    if hasattr(risk_level, "value"):
        return risk_level.value
    return str(risk_level)


class ApprovalQueue:
    def __init__(self, default_timeout: float = 300.0) -> None:
        self._default_timeout = default_timeout
        self._entries: dict[str, ApprovalEntry] = {}
        self._lock = threading.Lock()

    def add(self, request) -> ApprovalEntry:
        entry = ApprovalEntry(
            id=request.id,
            action=request.action,
            risk_level=_risk_str(request.risk_level),
            payload=dict(request.payload),
            reason=request.reason,
            status=ApprovalStatus.PENDING,
            requested_at=request.requested_at,
        )
        with self._lock:
            self._entries[entry.id] = entry
        return entry

    def approve(self, entry_id: str, resolver_note: str | None = None) -> ApprovalEntry | None:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            if entry.status != ApprovalStatus.PENDING:
                return entry
            entry.status = ApprovalStatus.APPROVED
            entry.resolved_at = time.time()
            entry.resolver_note = resolver_note
            return entry

    def reject(self, entry_id: str, resolver_note: str | None = None) -> ApprovalEntry | None:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            if entry.status != ApprovalStatus.PENDING:
                return entry
            entry.status = ApprovalStatus.REJECTED
            entry.resolved_at = time.time()
            entry.resolver_note = resolver_note
            return entry

    def expire_stale(self) -> list[ApprovalEntry]:
        now = time.time()
        expired: list[ApprovalEntry] = []
        with self._lock:
            for entry in self._entries.values():
                if entry.status != ApprovalStatus.PENDING:
                    continue
                if now - entry.requested_at > self._default_timeout:
                    entry.status = ApprovalStatus.EXPIRED
                    entry.resolved_at = now
                    expired.append(entry)
        return expired

    def get(self, entry_id: str) -> ApprovalEntry | None:
        with self._lock:
            return self._entries.get(entry_id)

    def list_by_status(self, status: ApprovalStatus | None = None) -> list[ApprovalEntry]:
        with self._lock:
            entries = list(self._entries.values())
        if status is not None:
            entries = [e for e in entries if e.status == status]
        return sorted(entries, key=lambda e: e.requested_at)

    def count(self, status: ApprovalStatus | str | None = None) -> int:
        with self._lock:
            if status is None:
                return len(self._entries)
            if isinstance(status, str):
                return sum(1 for e in self._entries.values() if e.status.value == status)
            return sum(1 for e in self._entries.values() if e.status == status)
