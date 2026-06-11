"""NIGHT CITADEL — the self-improvement evolution engine (Plane 9).

v5.0 blueprint §4.9 / §5.10 (and the v3.0 SYNAPTIC nightly loop). NIGHT CITADEL
runs the safeguarded self-improvement cycle: audit recent performance, generate
improvement candidates, then pass three safety gates before anything is staged:

  * **drift gate** — a SAHOO-style Goal Drift Index (GDI) must stay at or below
    threshold, else the cycle HALTS;
  * **constraint gate** — all constitutional rules must still hold;
  * **regression gate** — measured regression must stay within tolerance.

A failed gate halts the cycle safely (no promotion) rather than shipping a risky
self-modification. Dependency-free and deterministic.

Public surface:
    NightCitadel  — the cycle orchestrator
    PHASES        — the ordered cycle lifecycle
    GDI_THRESHOLD, REGRESSION_THRESHOLD
    CitadelError  — typed failures
"""

from __future__ import annotations

from pradyos.night_citadel.citadel import (
    GDI_THRESHOLD,
    PHASES,
    REGRESSION_THRESHOLD,
    CitadelError,
    NightCitadel,
)

__all__ = [
    "NightCitadel",
    "PHASES",
    "GDI_THRESHOLD",
    "REGRESSION_THRESHOLD",
    "CitadelError",
]
