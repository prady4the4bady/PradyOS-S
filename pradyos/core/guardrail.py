from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.approval_queue import ApprovalQueue
    from pradyos.core.decision_journal import DecisionJournal


class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ActionRequest:
    id: str
    action: str
    risk_level: RiskLevel
    payload: dict
    requested_at: float
    reason: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "risk_level": self.risk_level.value,
            "payload": dict(self.payload),
            "requested_at": self.requested_at,
            "reason": self.reason,
        }


class GuardrailGate:
    AUTO_APPROVE_LEVELS = {RiskLevel.SAFE, RiskLevel.LOW}

    def __init__(
        self,
        approval_queue: ApprovalQueue | None = None,
        decision_journal: DecisionJournal | None = None,
    ) -> None:
        self._queue = approval_queue
        self._journal = decision_journal
        self._lock = threading.Lock()

    def submit(
        self,
        action: str,
        risk_level: RiskLevel,
        payload: dict,
        reason: str | None = None,
    ) -> ActionRequest:
        if risk_level == RiskLevel.CRITICAL and not reason:
            raise ValueError("reason required for CRITICAL actions")

        request = ActionRequest(
            id=uuid.uuid4().hex,
            action=action,
            risk_level=risk_level,
            payload=dict(payload),
            requested_at=time.time(),
            reason=reason,
        )

        auto_approved = risk_level in self.AUTO_APPROVE_LEVELS

        if auto_approved:
            if self._journal is not None:
                try:
                    self._journal.record(
                        agent_id="guardrail_gate",
                        decision_type="auto_approved",
                        rationale=f"action={action} risk={risk_level.value}",
                        outcome="executed",
                    )
                except Exception:
                    pass
        else:
            if self._queue is not None:
                self._queue.add(request)
            if self._journal is not None:
                try:
                    self._journal.record(
                        agent_id="guardrail_gate",
                        decision_type="pending_approval",
                        rationale=(
                            f"action={action} risk={risk_level.value} " f"reason={reason or '-'}"
                        ),
                        outcome="queued",
                    )
                except Exception:
                    pass

        return request

    def status(self) -> dict:
        queue_size = 0
        if self._queue is not None:
            try:
                queue_size = self._queue.count("pending")
            except Exception:
                queue_size = 0
        return {
            "auto_approve_levels": [lvl.value for lvl in self.AUTO_APPROVE_LEVELS],
            "queue_size": queue_size,
        }
