"""BASTION — the constitutional security shield (Plane 7).

Plane 7 of PRADY OS (v5.0 blueprint §4.7 / §5.8 / §8). BASTION is constitutional
*containment*, not privilege starvation: it classifies the risk of a proposed
action, decides whether it stays in the autonomous execution domain or must
cross the Sovereign approval boundary, and explains its reasoning (what was
attempted, why, which rule fired, whether rollback exists, what narrower
permission would succeed). It also scans untrusted content for prompt-injection
and maps risk to a response protocol.

Dependency-free and deterministic, so every verdict is testable.

Public surface:
    Action   — a proposed action to assess
    Verdict  — the assessment result (decision, domain, score, reasons, …)
    Bastion  — the shield: assess(), scan_content(), response_for()
    *Error   — typed failures
"""

from __future__ import annotations

from pradyos.bastion.shield import (
    Action,
    Bastion,
    BastionError,
    Verdict,
)

__all__ = [
    "Action",
    "Verdict",
    "Bastion",
    "BastionError",
]
