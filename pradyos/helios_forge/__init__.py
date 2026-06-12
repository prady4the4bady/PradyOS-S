"""HELIOS FORGE — the approved-project build engine (Plane / Agent 2).

v5.0 blueprint §5.4. HELIOS FORGE activates *after* a project crosses the
Sovereign approval boundary and drives it from a plan to a staged deliverable:
scaffold → code → test → validate → stage. It tracks milestones and produced
artifacts, and it gates progression — a build cannot be validated until its
tests are green, nor staged until every milestone is complete. It never deploys
(that is TITAN OPS) and never bypasses the test gate.

Dependency-free and deterministic; every transition is testable.

Public surface:
    HeliosForge  — the engine: create / advance / milestones / artifacts / tests
    STAGES       — the ordered build lifecycle
    ForgeError   — typed failures
"""

from __future__ import annotations

from pradyos.helios_forge.forge import STAGES, ForgeError, HeliosForge

__all__ = ["HeliosForge", "STAGES", "ForgeError"]
