"""SPECTER — browser / web-action executor (Agent / Plane 9 — SPECTER).

v5.0 blueprint §5.9. SPECTER operates sites that lack robust APIs: navigate, log
in through approved channels, fill forms, click multi-step flows, and extract web
state. Its governing rule is **fallback-first** — when an API exists for a target
it is always preferred over a brittle browser flow. Flows are checkpointed (the
last completed step is recorded) and steps retry up to a bound before failing.

Dependency-free and deterministic (it models the flow control; an executor wires
the actual browser).

Public surface:
    Specter      — plan() + create_flow / step / extract / fail_step / complete
    STEP_KINDS   — recognised step kinds
    SpecterError — typed failures
"""

from __future__ import annotations

from pradyos.specter.specter import STEP_KINDS, Specter, SpecterError

__all__ = ["Specter", "STEP_KINDS", "SpecterError"]
