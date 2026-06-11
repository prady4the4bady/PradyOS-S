"""IMPERIUM task model.

A task is the unit of orchestration. It declares:
    - what to do (kind + payload, e.g. a TITAN OPS instruction)
    - priority class
    - dependencies (other task IDs)
    - retry policy
    - intent narration (for audit + Throne)

The kernel is responsible for transitioning the task through the
QUEUED → RUNNING → SUCCEEDED / FAILED / ESCALATED state machine.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from pradyos.core.ids import new_id
from pradyos.core.types import Priority, TaskState


@dataclass(slots=True)
class ImperiumTask:
    """Specification of work to do. Submitted by an agent or the Throne."""

    kind: str  # e.g. 'titan.shell', 'research', 'project_proposal'
    payload: dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    priority: Priority = Priority.OPERATIONAL
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 0
    retry_backoff_sec: float = 1.0
    submitted_by: str = "system"
    task_id: str = field(default_factory=lambda: new_id("tk"))
    parent_id: str | None = None  # for sub-tasks (HELIOS FORGE etc.)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["priority"] = self.priority.value
        return d


@dataclass(slots=True)
class TaskRecord:
    """Live state for a submitted task. Owned by IMPERIUM's StateCore."""

    spec: ImperiumTask
    state: TaskState = TaskState.QUEUED
    attempts: int = 0
    last_error: str | None = None
    last_result: dict[str, Any] | None = None
    escalation_reason: str | None = None
    escalation_rule: str | None = None
    queued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.spec.task_id,
            "kind": self.spec.kind,
            "intent": self.spec.intent,
            "priority": self.spec.priority.value,
            "state": self.state.value,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "last_result": self.last_result,
            "escalation_reason": self.escalation_reason,
            "escalation_rule": self.escalation_rule,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "depends_on": list(self.spec.depends_on),
            "submitted_by": self.spec.submitted_by,
        }

    @property
    def is_terminal(self) -> bool:
        return self.state.terminal
