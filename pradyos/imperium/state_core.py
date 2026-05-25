"""IMPERIUM — StateCore (Phase 1).

StateCore owns ALL state-machine transitions for TaskRecords.  No other
layer may mutate ``rec.state`` directly — it must call StateCore methods.
This gives us a single audit chokepoint for every state change.

Responsibilities:
    - Authoritative state-machine transitions (QUEUED→RUNNING→SUCCEEDED/FAILED/ESCALATED)
    - Persist every transition via CheckpointStore
    - Publish bus events for each transition
    - Provide consistent to_dict serialisation for Throne consumption
"""

from __future__ import annotations

import time
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.types import TaskState
from pradyos.imperium.checkpoint import CheckpointStore
from pradyos.imperium.task import ImperiumTask, TaskRecord


class StateCore:
    """Owns all TaskRecord state transitions."""

    AGENT_ID = "imperium.state"

    def __init__(
        self,
        checkpoint: CheckpointStore | None = None,
        audit: AuditLog | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.checkpoint = checkpoint or CheckpointStore()
        self.audit = audit or get_audit_log()
        self.bus = bus or get_bus()

    # ---------- transitions ----------

    def mark_queued(self, rec: TaskRecord, reason: str = "") -> None:
        rec.state = TaskState.QUEUED
        rec.queued_at = time.time()
        self._commit(rec, f"queued: {rec.spec.intent or rec.spec.kind}"
                    + (f" ({reason})" if reason else ""), "imperium.task_queued")

    def mark_running(self, rec: TaskRecord) -> None:
        rec.state = TaskState.RUNNING
        rec.started_at = time.time()
        rec.attempts += 1
        self._commit(rec, f"running: {rec.spec.intent or rec.spec.kind}", "imperium.task_running")

    def mark_succeeded(self, rec: TaskRecord, result: dict[str, Any] | None = None) -> None:
        rec.state = TaskState.SUCCEEDED
        rec.finished_at = time.time()
        rec.last_error = None
        if result is not None:
            rec.last_result = result
        self._commit(rec, f"succeeded: {rec.spec.intent or rec.spec.kind}", "imperium.task_succeeded")

    def mark_failed(self, rec: TaskRecord, error: str) -> None:
        rec.state = TaskState.FAILED
        rec.last_error = error
        rec.finished_at = time.time()
        self._commit(rec, f"failed: {rec.spec.intent or rec.spec.kind}", "imperium.task_failed")

    def mark_escalated(self, rec: TaskRecord, reason: str, rule: str | None) -> None:
        rec.state = TaskState.ESCALATED
        rec.escalation_reason = reason
        rec.escalation_rule = rule
        self._commit(
            rec,
            f"AWAITING SOVEREIGN APPROVAL: {rec.spec.intent or rec.spec.kind}",
            "imperium.task_escalated",
        )

    def mark_approved(self, rec: TaskRecord, approver: str) -> None:
        rec.state = TaskState.QUEUED
        rec.escalation_reason = None
        rec.queued_at = time.time()
        self._commit(rec, f"APPROVED by {approver}: {rec.spec.intent or rec.spec.kind}",
                     "imperium.task_approved")

    def mark_rejected(self, rec: TaskRecord, approver: str, reason: str) -> None:
        rec.state = TaskState.CANCELLED
        rec.finished_at = time.time()
        self._commit(rec, f"REJECTED by {approver}: {reason}", "imperium.task_rejected")

    def mark_cancelled(self, rec: TaskRecord, reason: str = "") -> None:
        rec.state = TaskState.CANCELLED
        rec.finished_at = time.time()
        self._commit(rec, f"cancelled: {reason or rec.spec.intent or rec.spec.kind}",
                     "imperium.task_cancelled")

    # ---------- resume ----------

    def resume_non_terminal(self) -> list[TaskRecord]:
        """Load and return all non-terminal records from the checkpoint store."""
        return self.checkpoint.resume_non_terminal()

    def write(self, rec: TaskRecord) -> None:
        self.checkpoint.write(rec)

    # ---------- internal ----------

    def _commit(self, rec: TaskRecord, summary: str, event: str) -> None:
        self.checkpoint.write(rec)
        self.audit.record(
            agent_id=self.AGENT_ID,
            kind="state",
            summary=summary,
            detail=rec.to_dict(),
            correlation_id=rec.spec.task_id,
        )
        self.bus.publish(event, rec.to_dict())
