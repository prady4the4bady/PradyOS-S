#!/usr/bin/env python3
"""Surface the Phase 1 proposal into a running IMPERIUM as an ESCALATED
task — the first item the Sovereign Throne will display in the Approvals
panel.

This is the canonical Phase 0 demonstration of the approval boundary:
ORACLE (here, this script) submits a `project_proposal`; IMPERIUM's
PolicyCore catches it via the `new_project_proposal` constitutional rule;
the Throne renders it; the Sovereign issues approve/reject through the
Throne (or, in scripted demos, programmatically).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pradyos.core.audit import get_audit_log
from pradyos.core.bus import get_bus
from pradyos.core.types import Priority
from pradyos.imperium.checkpoint import CheckpointStore
from pradyos.imperium.kernel import Imperium
from pradyos.imperium.task import ImperiumTask

DOSSIER_PATH = Path(__file__).resolve().parents[1] / "docs" / "PHASE_1_PROPOSAL.md"


def build_proposal_task() -> ImperiumTask:
    dossier = DOSSIER_PATH.read_text(encoding="utf-8") if DOSSIER_PATH.exists() else ""
    return ImperiumTask(
        kind="project_proposal",
        intent="PHASE 1 — Full TITAN OPS + IMPERIUM Hardening + Governance Chamber",
        priority=Priority.SOVEREIGN,
        submitted_by="oracle_seed",
        payload={
            "dossier_path": str(DOSSIER_PATH),
            "dossier_text": dossier,
            "phase": 1,
            "components": ["titan_ops", "imperium", "aurora_throne",
                            "repository_proving_ground"],
            "estimated_sessions": "1-2",
            "rollback_plan": "feature branch + PRADYOS_PHASE=0 flag; Phase 0 stays feature-frozen",
            "risk_summary": "async rewrite, privileged-lane hardening, snapshot dependence",
        },
        metadata={
            "approval_card": {
                "what": "Graduate Phase 0 substrate to production-grade Phase 1.",
                "why": "Hidden-CLI doctrine and constitutional rollback discipline only "
                        "hold when the contracts ship in load-bearing form.",
                "requires": "1–2 Sovereign-time sessions; no new machine spending.",
                "risk": "Medium overall — mitigated by feature-branch isolation and "
                         "preserved Phase 0 fallback.",
                "expected_outcome": "Single-surface governance chamber; autonomous "
                                     "rollback-aware execution; ORACLE-ready substrate.",
                "rollback": "PRADYOS_PHASE=0 reverts; checkpoint format is forward-compatible.",
            }
        },
    )


def main() -> int:
    audit = get_audit_log()
    bus = get_bus()
    kern = Imperium(audit=audit, bus=bus, checkpoint=CheckpointStore())
    # We do NOT start workers — submitting + classifying is enough to surface.
    task = build_proposal_task()
    rec = kern.submit(task)
    # Force the state-machine pass so the task lands in ESCALATED.
    kern.run_one()
    print(json.dumps({
        "task_id": rec.spec.task_id,
        "state": rec.state.value,
        "intent": rec.spec.intent,
        "escalation_reason": rec.escalation_reason,
        "escalation_rule": rec.escalation_rule,
        "next": "Open the Throne (python -m pradyos.aurora_throne.app) "
                "to review and approve.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
