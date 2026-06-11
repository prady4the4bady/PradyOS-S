"""IMPERIUM — RecoveryCore (Phase 1).

RecoveryCore handles everything that goes wrong after a task starts running:

    - Retry scheduling with exponential backoff (up to task.max_retries)
    - Rollback invocation — fires the TitanRollback hook via TITAN OPS
    - Self-healing: if a task has a ``heal_command`` in its payload, that
      shell command is dispatched to TITAN OPS before the retry
    - Dead-letter handling: tasks that exhaust retries are moved to FAILED
      and a ``DLQ`` entry is recorded so the Sovereign Throne can inspect

RecoveryCore is *stateless* across calls — all durable state lives in the
CheckpointStore (via StateCore) and the RollbackRegistry.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.imperium.state_core import StateCore
from pradyos.imperium.task import TaskRecord
from pradyos.titan_ops.rollback import RollbackRegistry

log = logging.getLogger("pradyos.imperium.recovery")


class DeadLetterEntry:
    """A task that exhausted all retries."""

    def __init__(self, rec: TaskRecord, final_error: str) -> None:
        self.task_id = rec.spec.task_id
        self.intent = rec.spec.intent or rec.spec.kind
        self.attempts = rec.attempts
        self.final_error = final_error
        self.failed_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent": self.intent,
            "attempts": self.attempts,
            "final_error": self.final_error,
            "failed_at": self.failed_at,
        }


class RecoveryCore:
    """Handles retries, rollbacks, self-healing, and dead-letter tracking."""

    def __init__(
        self,
        state: StateCore,
        rollback_registry: RollbackRegistry | None = None,
        audit: AuditLog | None = None,
        bus: EventBus | None = None,
        scheduler: Any | None = None,  # SchedulerCore — avoid circular import
        on_exhausted: Any | None = None,  # callable(rec, error) — Phase 11 self-heal hook
    ) -> None:
        self.state = state
        self.rollback_registry = rollback_registry or RollbackRegistry()
        self.audit = audit or get_audit_log()
        self.bus = bus or get_bus()
        self.scheduler = scheduler  # wired after construction to avoid cycles
        self._on_exhausted = on_exhausted  # Phase 11: called after dead-lettering
        self._dlq: list[DeadLetterEntry] = []

    # ---------- public API ----------

    def handle_failure(self, rec: TaskRecord, error: str) -> None:
        """Decide between retry, rollback, and final failure."""
        rec.last_error = error

        if rec.attempts <= rec.spec.max_retries:
            self._schedule_retry(rec)
        else:
            self._rollback_if_possible(rec)
            self._dead_letter(rec, error)
            # Phase 11: notify self-heal engine after dead-lettering
            if self._on_exhausted is not None:
                try:
                    self._on_exhausted(rec, error)
                except Exception as exc:  # noqa: BLE001
                    log.warning("self-heal hook raised (non-fatal): %s", exc)

    def execute_rollback(self, instruction_id: str) -> dict[str, Any]:
        """Invoke a stored rollback entry by instruction ID."""
        return self.rollback_registry.execute_rollback(instruction_id)

    def dead_letter_queue(self) -> list[DeadLetterEntry]:
        return list(self._dlq)

    def self_heal(self, rec: TaskRecord) -> bool:
        """Attempt autonomous self-healing before a retry.

        If the task payload contains a ``heal_command`` key, dispatch it to
        TITAN OPS immediately (synchronously, best-effort).
        Returns True if the heal command succeeded.
        """
        heal_cmd = rec.spec.payload.get("heal_command")
        if not heal_cmd:
            return False
        try:
            from pradyos.titan_ops.executor import TitanExecutor
            from pradyos.titan_ops.instruction import InstructionKind, TitanInstruction

            ex = TitanExecutor(audit=self.audit, bus=self.bus)
            heal_instr = TitanInstruction(
                agent_id="imperium.recovery",
                kind=InstructionKind.SHELL,
                command=heal_cmd,
                intent=f"self-heal for {rec.spec.task_id}",
                timeout_sec=30,
            )
            result = ex.execute(heal_instr)
            if result.succeeded:
                self.audit.record(
                    agent_id="imperium.recovery",
                    kind="recovery",
                    summary=f"self-heal succeeded for {rec.spec.task_id}",
                    detail={"heal_command": heal_cmd, "stdout_tail": result.stdout[-500:]},
                    correlation_id=rec.spec.task_id,
                )
                return True
        except Exception as e:  # noqa: BLE001
            log.warning("self-heal error for %s: %s", rec.spec.task_id, e)
        return False

    # ---------- internals ----------

    def _schedule_retry(self, rec: TaskRecord) -> None:
        backoff = min(rec.spec.retry_backoff_sec * (2 ** max(0, rec.attempts - 1)), 30.0)
        log.info(
            "retry %d/%d for %s in %.1fs",
            rec.attempts,
            rec.spec.max_retries,
            rec.spec.task_id,
            backoff,
        )
        if backoff > 0:
            time.sleep(backoff)
        self.state.mark_queued(rec, reason=f"retry {rec.attempts}/{rec.spec.max_retries}")
        if self.scheduler is not None:
            self.scheduler.requeue(rec.spec)
        self.audit.record(
            agent_id="imperium.recovery",
            kind="recovery",
            summary=f"retry {rec.attempts}/{rec.spec.max_retries}: {rec.last_error}",
            detail=rec.to_dict(),
            correlation_id=rec.spec.task_id,
        )

    def _rollback_if_possible(self, rec: TaskRecord) -> None:
        rollback_hook = rec.spec.payload.get("rollback_hook")
        if not rollback_hook:
            return
        self.audit.record(
            agent_id="imperium.recovery",
            kind="recovery",
            summary=f"invoking rollback for {rec.spec.task_id}",
            detail={"rollback_hook": rollback_hook},
            correlation_id=rec.spec.task_id,
        )
        try:
            from pradyos.titan_ops.executor import TitanExecutor
            from pradyos.titan_ops.instruction import InstructionKind, TitanInstruction

            ex = TitanExecutor(audit=self.audit, bus=self.bus)
            rb_instr = TitanInstruction(
                agent_id="imperium.recovery",
                kind=InstructionKind.SHELL,
                command=rollback_hook,
                intent=f"rollback for {rec.spec.task_id}",
                timeout_sec=60,
            )
            result = ex.execute(rb_instr)
            log.info("rollback for %s: succeeded=%s", rec.spec.task_id, result.succeeded)
        except Exception as e:  # noqa: BLE001
            log.warning("rollback error for %s: %s", rec.spec.task_id, e)

    def _dead_letter(self, rec: TaskRecord, error: str) -> None:
        entry = DeadLetterEntry(rec, error)
        self._dlq.append(entry)
        self.state.mark_failed(rec, error)
        self.audit.record(
            agent_id="imperium.recovery",
            kind="recovery",
            summary=f"dead-lettered: {rec.spec.intent or rec.spec.kind}",
            detail=entry.to_dict(),
            correlation_id=rec.spec.task_id,
        )
        self.bus.publish("imperium.task_dead_lettered", entry.to_dict())
