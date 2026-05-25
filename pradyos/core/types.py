"""Shared type definitions for PRADY OS.

Kept deliberately small. New types belong in their owning plane unless
they cross plane boundaries.
"""

from __future__ import annotations

from enum import Enum
from typing import NewType

AgentID = NewType("AgentID", str)
"""Stable identifier for an agent or daemon. Examples:
    'titan_ops'      — hidden command runner
    'warden_grid'    — telemetry mesh
    'imperium'       — orchestrator
    'aurora_throne'  — Sovereign terminal
    'oracle'         — opportunity scout (Phase 2+)
"""


class Priority(str, Enum):
    """IMPERIUM task priority classes (blueprint §IV/V)."""

    SOVEREIGN = "SOVEREIGN"      # direct Sovereign directive — preempts everything
    OPERATIONAL = "OPERATIONAL"  # ordinary machine-owned work
    BACKGROUND = "BACKGROUND"    # idle / nightly self-improvement work

    @property
    def rank(self) -> int:
        return {"SOVEREIGN": 0, "OPERATIONAL": 1, "BACKGROUND": 2}[self.value]


class TaskState(str, Enum):
    """IMPERIUM task state machine."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"   # crossed Sovereign approval boundary
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in {
            TaskState.SUCCEEDED,
            TaskState.FAILED,
            TaskState.ESCALATED,
            TaskState.CANCELLED,
        }


class ExecutionLane(str, Enum):
    """TITAN OPS subprocess lanes (blueprint §VIII)."""

    UNPRIVILEGED = "unprivileged"  # default — ordinary exploration
    PRIVILEGED = "privileged"      # constitutional admin (sudo / root)
    SANDBOX = "sandbox"            # NIGHT CITADEL experiment lane
