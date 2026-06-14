"""GUILD plane — a working organization of specialist agents.

A roster of specialist roles collaborate on an objective via a shared blackboard
and produce a synthesized result. See :mod:`pradyos.guild.org`.
"""

from __future__ import annotations

from pradyos.guild.org import (
    DEFAULT_ROLES,
    Contribution,
    GuildError,
    GuildOrg,
    LLMGuildWorker,
    OllamaGuildWorker,
    Project,
    Role,
)

__all__ = [
    "DEFAULT_ROLES",
    "Contribution",
    "GuildError",
    "GuildOrg",
    "LLMGuildWorker",
    "OllamaGuildWorker",
    "Project",
    "Role",
]
