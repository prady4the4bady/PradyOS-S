"""NEXUS WEAVE — agent orchestration & A2A routing (Agent 4).

v3.0 blueprint Agent 4. NEXUS WEAVE routes tasks to the agent best able to handle
them: internal agents first, delegating to external A2A agents only when no
internal agent has the capability. It manages a task queue, tracks task status,
and re-routes a task to a fallback agent when its assigned agent fails. It never
*initiates* tasks — it only routes them. Dependency-free and deterministic.

Public surface:
    NexusWeave  — the router: register_agent / submit / route / complete / fail
    NexusError  — typed failures
    NoRouteError — no agent can handle a task
"""

from __future__ import annotations

from pradyos.nexus_weave.weave import NexusError, NexusWeave, NoRouteError

__all__ = ["NexusWeave", "NexusError", "NoRouteError"]
