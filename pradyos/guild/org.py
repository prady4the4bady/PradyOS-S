"""GUILD — a working organization of specialist agents.

Where NEXUS WEAVE *routes* a single task to the one agent best able to handle it,
the GUILD models the other half of how a real team works: an **organization of
specialists who build on each other's work**. Given an objective, a roster of
roles — planner, researcher, engineer, analyst, critic, synthesizer — each
contributes in turn to a shared **blackboard**, every role seeing what the
previous ones produced, and the engine assembles their contributions into one
synthesized result.

Design (mirrors the rest of the constellation):

  * The **orchestration is pure and deterministic** — the roster, the order of
    contribution, the blackboard accumulation, and the synthesis digest are all
    functions of the roles and what each returns. So the engine is unit-tested
    against a *fake* worker with hand-computed ground truth (no LLM in tests).
  * The **actual thinking lives behind a worker interface**. A worker is any
    callable ``(role, objective, context) -> str`` that produces a role's
    contribution; the live wiring uses a LOCAL LLM (Ollama → no API credits), and
    tests inject a fake. ``None`` ⇒ the GUILD forms the charter but produces no
    content (degrades gracefully, never crashes).
  * A failing worker never sinks a project: that role's contribution is recorded
    empty and the remaining roles still contribute (self-healing collaboration).

This is the seed of the "company of expert agents" model: deterministic,
gated-egress-safe, and composable with the rest of the OS (a role's worker can
itself call RESEARCH, EVOLVE, or NEXUS).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("pradyos.guild")


class GuildError(RuntimeError):
    """Base class for GUILD failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Role:
    """A specialist seat in the guild."""

    name: str
    expertise: str
    brief: str  # the standing instruction handed to the worker for this role

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "expertise": self.expertise, "brief": self.brief}


# The default roster — a small cross-functional team that mirrors how a capable
# organization moves from objective to recommendation. Order is the workflow.
DEFAULT_ROLES: tuple[Role, ...] = (
    Role(
        "planner", "decomposition & strategy", "Break the objective into a concrete plan of steps."
    ),
    Role(
        "researcher", "facts & prior art", "Gather the facts, prior art, and unknowns that matter."
    ),
    Role(
        "engineer", "concrete solution", "Propose a concrete technical approach or implementation."
    ),
    Role("analyst", "feasibility & tradeoffs", "Assess feasibility, costs, risks, and tradeoffs."),
    Role(
        "critic", "adversarial review", "Stress-test the plan: find the flaws and how to fix them."
    ),
    Role("synthesizer", "final recommendation", "Merge everything into one clear recommendation."),
)


class Tool:
    """A capability a guild role can use mid-task — the bridge that lets the team
    *act*, not just talk. ``run(objective)`` turns the objective into a text
    result that is placed on the shared blackboard before the role contributes,
    so the role (and everyone after) reasons over real OS output (e.g. live
    research) rather than the model's memory alone."""

    def __init__(self, name: str, description: str, fn: Any) -> None:
        if not _is_str(name):
            raise GuildError("tool name must be a non-empty string")
        self.name = name
        self.description = description
        self._fn = fn

    def run(self, objective: str) -> str:
        out = self._fn(objective)
        return out if isinstance(out, str) else ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


def research_tool(engine: Any, limit: int = 3) -> Tool:
    """A GUILD tool that runs live RESEARCH on the objective and returns a short
    cited digest. ``engine`` is duck-typed (anything with ``.research(objective)``
    returning a brief / ``.to_dict()``-able), so the GUILD stays decoupled."""

    def _run(objective: str) -> str:
        brief = engine.research(objective)
        data = brief.to_dict() if hasattr(brief, "to_dict") else brief
        findings = (data or {}).get("findings", [])[:limit]
        lines = [f"- {f.get('title') or f.get('url', '')}: {f.get('url', '')}" for f in findings]
        return "Live research:\n" + "\n".join(lines) if lines else ""

    return Tool("research", "live web/code/paper research on the objective", _run)


@dataclass(frozen=True)
class Contribution:
    seq: int
    role: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "role": self.role, "content": self.content}


@dataclass(frozen=True)
class Project:
    id: str
    objective: str
    roster: tuple[str, ...]
    status: str  # complete (a role produced content) | charter (no worker/output)
    contributions: tuple[Contribution, ...]
    synthesis: str
    tool_uses: tuple[dict[str, str], ...] = ()  # which role invoked which tool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "objective": self.objective,
            "roster": list(self.roster),
            "status": self.status,
            "contributions": [c.to_dict() for c in self.contributions],
            "synthesis": self.synthesis,
            "tool_uses": [dict(t) for t in self.tool_uses],
        }


class GuildOrg:
    """Runs an objective through a roster of specialist roles on a blackboard."""

    def __init__(
        self,
        worker: Any | None = None,
        roles: tuple[Role, ...] | None = None,
        toolbox: list[Tool] | dict[str, Tool] | None = None,
        role_tools: dict[str, list[str]] | None = None,
    ) -> None:
        # worker(role, objective, context) -> str. None ⇒ charter-only (no content).
        self._worker = worker
        roster = roles if roles is not None else DEFAULT_ROLES
        self._roles: tuple[Role, ...] = tuple(roster)
        self._role_map: dict[str, Role] = {r.name: r for r in self._roles}
        # Tools a role may use mid-task, and the role→tool-names mapping.
        if isinstance(toolbox, dict):
            self._toolbox: dict[str, Tool] = dict(toolbox)
        else:
            self._toolbox = {t.name: t for t in (toolbox or [])}
        self._role_tools: dict[str, list[str]] = {k: list(v) for k, v in (role_tools or {}).items()}
        self._projects: list[Project] = []
        self._seq = 0
        self._lock = threading.RLock()

    # ── the roster + toolbox ──────────────────────────────────────────────────────

    def roles(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._roles]

    def tools(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._toolbox.values()]

    # ── run an objective through the guild ───────────────────────────────────────

    def run(
        self, objective: str, roster: list[str] | tuple[str, ...] | None = None
    ) -> dict[str, Any]:
        """Have each role contribute to ``objective`` in turn; return the project.

        ``roster`` optionally selects/orders a subset of registered role names
        (default: the full roster in declaration order). Each role's worker sees
        the objective plus all prior contributions (the blackboard).
        """
        if not _is_str(objective):
            raise GuildError("objective must be a non-empty string")
        # None ⇒ the full default roster; an explicit empty list is an error.
        names = [r.name for r in self._roles] if roster is None else list(roster)
        if not names:
            raise GuildError("roster must name at least one role")
        selected: list[Role] = []
        for n in names:
            role = self._role_map.get(n)
            if role is None:
                raise GuildError(f"unknown role {n!r}")
            selected.append(role)

        contributions: list[Contribution] = []
        context: list[dict[str, str]] = []  # the blackboard handed to each worker
        tool_uses: list[dict[str, str]] = []
        for i, role in enumerate(selected, start=1):
            # This role's tools act on the objective and post their output to the
            # blackboard BEFORE the role speaks, so it reasons over real OS output.
            for tname in self._role_tools.get(role.name, []):
                tool = self._toolbox.get(tname)
                if tool is None:
                    continue
                try:
                    out = tool.run(objective)
                except Exception as exc:  # noqa: BLE001 — a dead tool must not sink the project
                    log.warning("guild tool %s failed: %s", tname, exc)
                    out = ""
                if isinstance(out, str) and out.strip():
                    context.append({"role": f"tool:{tname}", "content": out})
                    tool_uses.append({"role": role.name, "tool": tname})
            content = ""
            if self._worker is not None:
                try:
                    content = self._worker(role, objective, list(context)) or ""
                except Exception as exc:  # noqa: BLE001 — a dead worker must not sink the project
                    log.warning("guild worker failed for role %s: %s", role.name, exc)
                    content = ""
                if not isinstance(content, str):
                    content = ""
            contributions.append(Contribution(seq=i, role=role.name, content=content))
            if content.strip():
                context.append({"role": role.name, "content": content})

        synthesis = self._synthesize(contributions)
        # Status reflects whether a ROLE produced content (tool output alone is not
        # a completed project).
        status = "complete" if any(c.content.strip() for c in contributions) else "charter"
        with self._lock:
            self._seq += 1
            project = Project(
                id=f"proj-{self._seq}",
                objective=objective,
                roster=tuple(names),
                status=status,
                contributions=tuple(contributions),
                synthesis=synthesis,
                tool_uses=tuple(tool_uses),
            )
            self._projects.append(project)
        return project.to_dict()

    @staticmethod
    def _synthesize(contributions: list[Contribution]) -> str:
        """A deterministic digest of the contributions (role → its takeaway)."""
        lines = [
            f"[{c.role}] {c.content.strip()[:200]}" for c in contributions if c.content.strip()
        ]
        return "\n".join(lines)

    # ── introspection ────────────────────────────────────────────────────────────

    def project(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            for p in self._projects:
                if p.id == project_id:
                    return p.to_dict()
        raise GuildError(f"unknown project {project_id!r}")

    def projects(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise GuildError("limit must be a positive integer")
        with self._lock:
            return [p.to_dict() for p in self._projects[-limit:]]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total_contribs = sum(
                1 for p in self._projects for c in p.contributions if c.content.strip()
            )
            return {
                "projects": len(self._projects),
                "contributions": total_contribs,
                "roles": len(self._roles),
                "tools": len(self._toolbox),
                "worker_configured": self._worker is not None,
            }

    def reset(self) -> None:
        with self._lock:
            self._projects.clear()
            self._seq = 0


class LLMGuildWorker:
    """A guild worker backed by any LLM provider (see :mod:`pradyos.core.llm`).

    The model is a configuration choice — local Ollama by default, a stronger
    model when the Sovereign opts in. Never contacted at import time; if the model
    is unreachable, ``__call__`` raises and :meth:`GuildOrg.run` degrades the
    role's contribution to empty. Tests inject a fake provider (or worker).
    """

    name = "llm"

    def __init__(self, provider: Any | None = None) -> None:
        if provider is None:
            from pradyos.core.llm import OllamaProvider

            provider = OllamaProvider()
        self._provider = provider

    def __call__(self, role: Role, objective: str, context: list[dict[str, str]]) -> str:
        prior = "\n".join(f"[{c['role']}] {c['content']}" for c in context) or "(you are first)"
        prompt = (
            f"You are the {role.name} of an expert team. Expertise: {role.expertise}. "
            f"{role.brief}\n\n"
            f"OBJECTIVE: {objective}\n\n"
            f"What your teammates have contributed so far:\n{prior}\n\n"
            "Add your contribution as the "
            f"{role.name}. Be concrete and build on the prior work; no preamble."
        )
        return self._provider.generate(prompt)


class OllamaGuildWorker(LLMGuildWorker):
    """Back-compatible local-Ollama guild worker (``LLMGuildWorker`` over an
    :class:`~pradyos.core.llm.OllamaProvider`)."""

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
    ) -> None:
        from pradyos.core.llm import OllamaProvider

        super().__init__(OllamaProvider(base_url=base_url, model=model, timeout=timeout))
        # Back-compat surface (these used to live on the worker directly).
        self.base_url = self._provider.base_url
        self.model = self._provider.model
        self.timeout = self._provider.timeout
