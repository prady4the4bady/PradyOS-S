"""TITAN OPS instruction schema.

A TITAN instruction is the *only* sanctioned way to make TITAN OPS act.
Free-form shell strings are not accepted in production paths — they
must be wrapped in a structured ``TitanInstruction``.

Schema (JSON wire format):

    {
        "instruction_id": "ti_…",          # optional, generated if absent
        "agent_id": "imperium",             # required — caller attribution
        "kind": "shell"                     # required — see InstructionKind
                |"package"|"file"|"service"|"process",
        "lane": "unprivileged"              # default; "privileged"|"sandbox"
        "command": "ls -la /etc",           # for kind=shell
        "args": {                           # kind-specific structured args
            "package": "htop",
            "manager": "apt",
            ...
        },
        "cwd": "/tmp",                      # optional working dir
        "env": { "FOO": "bar" },            # optional extra env
        "timeout_sec": 60,                  # default 60
        "rollback_hook": "apt purge htop",  # optional opaque ref
        "correlation_id": "imperium-task-…",# optional, ties to IMPERIUM task
        "intent": "install htop"            # human-readable narration
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pradyos.core.ids import new_id
from pradyos.core.types import ExecutionLane


class InstructionKind(str, Enum):
    SHELL = "shell"
    PACKAGE = "package"
    FILE = "file"
    SERVICE = "service"
    PROCESS = "process"


@dataclass(slots=True)
class TitanInstruction:
    agent_id: str
    kind: InstructionKind
    command: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    lane: ExecutionLane = ExecutionLane.UNPRIVILEGED
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_sec: float = 60.0
    rollback_hook: str | None = None
    correlation_id: str | None = None
    intent: str = ""
    instruction_id: str = field(default_factory=lambda: new_id("ti"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction_id": self.instruction_id,
            "agent_id": self.agent_id,
            "kind": self.kind.value,
            "lane": self.lane.value,
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "env": self.env,
            "timeout_sec": self.timeout_sec,
            "rollback_hook": self.rollback_hook,
            "correlation_id": self.correlation_id,
            "intent": self.intent,
        }


def parse_instruction(payload: dict[str, Any] | str | bytes) -> TitanInstruction:
    """Parse a wire-format instruction. Raises ``ValueError`` on schema breach."""
    if isinstance(payload, str | bytes):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("instruction payload must be a JSON object")

    agent_id = payload.get("agent_id")
    if not agent_id or not isinstance(agent_id, str):
        raise ValueError("instruction.agent_id required (string)")

    raw_kind = payload.get("kind")
    try:
        kind = InstructionKind(raw_kind)
    except ValueError as e:
        raise ValueError(f"instruction.kind invalid: {raw_kind!r}") from e

    raw_lane = payload.get("lane", "unprivileged")
    try:
        lane = ExecutionLane(raw_lane)
    except ValueError as e:
        raise ValueError(f"instruction.lane invalid: {raw_lane!r}") from e

    return TitanInstruction(
        agent_id=agent_id,
        kind=kind,
        command=payload.get("command"),
        args=payload.get("args") or {},
        lane=lane,
        cwd=payload.get("cwd"),
        env=payload.get("env") or {},
        timeout_sec=float(payload.get("timeout_sec", 60.0)),
        rollback_hook=payload.get("rollback_hook"),
        correlation_id=payload.get("correlation_id"),
        intent=payload.get("intent", ""),
        instruction_id=payload.get("instruction_id") or new_id("ti"),
    )
