"""AETHER SHELL — experiential intelligence layer (Plane 10).

v5.0 blueprint §4.10. AETHER SHELL is the visible face of the OS: it captures
Sovereign intent and routes it to the right surface, and it composes the
governance-chamber experience — a priority-ordered set of cards (governance
approvals, project dossiers, status, alerts) presented calmly, without exposing
the mechanical depth beneath.

Dependency-free and deterministic.

Public surface:
    AetherShell  — capture_intent / push_card / ack_card / experience
    SURFACES, URGENCIES
    AetherError  — typed failures
"""

from __future__ import annotations

from pradyos.aether_shell.shell import SURFACES, URGENCIES, AetherError, AetherShell

__all__ = ["AetherShell", "SURFACES", "URGENCIES", "AetherError"]
