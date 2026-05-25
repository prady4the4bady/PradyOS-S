"""AURORA THRONE — Sovereign Governance Chamber (blueprint §4.10, §13.1).

The Throne is the **only** surface the Sovereign sees. The raw CLI is
fully hidden. The Throne renders:

    Empire Health View    — live telemetry from WARDEN GRID
    Task Queue Status     — from IMPERIUM
    Pending Approvals     — escalated tasks awaiting Sovereign verdict
    Audit Tail            — last N completed actions

Phase 0 uses Rich for a cinematic but text-only render. Phase 5 swaps
the renderer for a full Textual app with cinematic motion.
"""

from pradyos.aurora_throne.app import Throne

__all__ = ["Throne"]
