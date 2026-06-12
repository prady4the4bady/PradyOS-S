"""SENTINEL WATCH — threat detection & adversarial defense (Agent 5).

v3.0 blueprint Agent 5. SENTINEL WATCH runs the red-team loop: it registers
adversarial scenarios that probe the OS's own constitutional boundaries, records
each exercise outcome (breached / blocked), opens a finding on every breach, and
tracks findings through to a patch. The count of *unpatched* breaches drives a
security posture (secure / elevated / critical) and the matching response tier.

Dependency-free and deterministic — distinct from BASTION (per-action policy
gate) and core.anomaly_watch (statistical anomaly detection).

Public surface:
    SentinelWatch  — the red-team engine
    SentinelError  — typed failures
"""

from __future__ import annotations

from pradyos.sentinel_watch.watch import SentinelError, SentinelWatch

__all__ = ["SentinelWatch", "SentinelError"]
