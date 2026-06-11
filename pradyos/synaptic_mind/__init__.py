"""SYNAPTIC MIND — intelligence growth & model management (Agent 6).

v3.0 blueprint Agent 6. SYNAPTIC MIND benchmarks candidate models against the OS's
own workload and manages the model lifecycle: when a model beats the current
default by more than the upgrade margin (5%), it raises an upgrade proposal for
ORACLE → AURORA THRONE. Promotion swaps the default. Dependency-free and
deterministic.

Public surface:
    SynapticMind   — the benchmark + upgrade-proposal engine
    UPGRADE_MARGIN — the relative improvement required to propose an upgrade
    SynapticError  — typed failures
"""

from __future__ import annotations

from pradyos.synaptic_mind.mind import UPGRADE_MARGIN, SynapticError, SynapticMind

__all__ = ["SynapticMind", "UPGRADE_MARGIN", "SynapticError"]
