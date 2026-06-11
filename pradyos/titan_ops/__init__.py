"""TITAN OPS — hidden command runner (blueprint §4.2, §5.2).

TITAN OPS is the hidden machine hand. It accepts structured JSON task
instructions and executes shell commands in isolated subprocess lanes
with full stdout/stderr capture and audit attribution.

It must feel like root-level competence with constitutional discipline.
"""

from pradyos.titan_ops.executor import ExecutionResult, TitanExecutor
from pradyos.titan_ops.instruction import (
    InstructionKind,
    TitanInstruction,
    parse_instruction,
)

__all__ = [
    "ExecutionResult",
    "InstructionKind",
    "TitanExecutor",
    "TitanInstruction",
    "parse_instruction",
]
