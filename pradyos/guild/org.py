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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "objective": self.objective,
            "roster": list(self.roster),
            "status": self.status,
            "contributions": [c.to_dict() for c in self.contributions],
            "synthesis": self.synthesis,
        }


class GuildOrg:
    """Runs an objective through a roster of specialist roles on a blackboard."""

    def __init__(self, worker: Any | None = None, roles: tuple[Role, ...] | None = None) -> None:
        # worker(role, objective, context) -> str. None ⇒ charter-only (no content).
        self._worker = worker
        roster = roles if roles is not None else DEFAULT_ROLES
        self._roles: tuple[Role, ...] = tuple(roster)
        self._role_map: dict[str, Role] = {r.name: r for r in self._roles}
        self._projects: list[Project] = []
        self._seq = 0
        self._lock = threading.RLock()

    # ── the roster ──────────────────────────────────────────────────────────────

    def roles(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._roles]

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
        for i, role in enumerate(selected, start=1):
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
        status = "complete" if context else "charter"
        with self._lock:
            self._seq += 1
            project = Project(
                id=f"proj-{self._seq}",
                objective=objective,
                roster=tuple(names),
                status=status,
                contributions=tuple(contributions),
                synthesis=synthesis,
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
                "worker_configured": self._worker is not None,
            }

    def reset(self) -> None:
        with self._lock:
            self._projects.clear()
            self._seq = 0


class OllamaGuildWorker:
    """A guild worker backed by a LOCAL Ollama model — zero API credits.

    Constructed lazily and never contacted at import time. If Ollama is not
    running, ``__call__`` raises and :meth:`GuildOrg.run` degrades the role's
    contribution to empty. Used as the live worker in production; tests inject a
    fake callable.
    """

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def __call__(self, role: Role, objective: str, context: list[dict[str, str]]) -> str:
        import json
        import urllib.request

        prior = "\n".join(f"[{c['role']}] {c['content']}" for c in context) or "(you are first)"
        prompt = (
            f"You are the {role.name} of an expert team. Expertise: {role.expertise}. "
            f"{role.brief}\n\n"
            f"OBJECTIVE: {objective}\n\n"
            f"What your teammates have contributed so far:\n{prior}\n\n"
            "Add your contribution as the "
            f"{role.name}. Be concrete and build on the prior work; no preamble."
        )
        payload = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip()
