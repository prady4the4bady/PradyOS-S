"""IMPERIUM PolicyCore — thin adapter over the constitutional classifier.

The classifier itself lives in ``pradyos.core.constitution`` (BASTION
seed). PolicyCore is the kernel-side adapter that decides whether a
task may run autonomously or must be escalated to the Sovereign.
"""

from __future__ import annotations

from pradyos.core.constitution import (
    ApprovalDomain,
    Constitution,
    PolicyDecision,
    default_constitution,
)
from pradyos.imperium.task import ImperiumTask


class PolicyCore:
    def __init__(self, constitution: Constitution | None = None) -> None:
        self.constitution = constitution or default_constitution()

    def classify(self, task: ImperiumTask) -> PolicyDecision:
        detail = {
            "intent": task.intent,
            "command": task.payload.get("command", ""),
            "lane": task.payload.get("lane", ""),
            "priority": task.priority.value,
            **task.payload,
        }
        return self.constitution.classify(
            kind=task.kind,
            summary=task.intent or task.kind,
            detail=detail,
        )

    def is_autonomous(self, task: ImperiumTask) -> bool:
        return self.classify(task).domain is ApprovalDomain.AUTONOMOUS
