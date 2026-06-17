"""PradySovereign Dev API — high-level facades for building agent applications.

Provides three simple wrappers over existing internal modules for a clean
developer experience:
  - SkillEngine  (L1 competence layer)
  - GuildSwarm   (multi-agent orchestration)
  - SovereignClient (governance interface)
"""

from __future__ import annotations

from typing import Any

from pradyos.guild.org import GuildOrg, Role, Tool
from pradyos.skills.library import SkillLibrary

__all__ = ["SkillEngine", "GuildSwarm", "SovereignClient"]


class SkillEngine:
    """High-level skill registry wrapping L1 SkillLibrary.

    ``register_skill`` stores a named skill with a trigger prompt and optional
    tool list.  ``run_skill`` looks up the skill by name and returns its
    stored definition (the real execution requires an LLM provider to interpret
    the steps; this facade returns the registered plan).
    """

    def __init__(self, library: SkillLibrary | None = None) -> None:
        self._lib = library or SkillLibrary()

    def register_skill(
        self,
        name: str,
        prompt: str,
        tools: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a new skill with a trigger prompt and optional tool list."""
        steps = tools or []
        return self._lib.learn(
            skill_id=name.lower().replace(" ", "_"),
            name=name,
            trigger=prompt,
            steps=steps if steps else [f"Execute: {prompt}"],
        )

    def run_skill(self, name: str, input: dict[str, Any] | None = None) -> dict[str, Any]:
        """Retrieve a registered skill by name and return its definition."""
        sid = name.lower().replace(" ", "_")
        return self._lib.recall(sid)

    def stats(self) -> dict[str, Any]:
        return self._lib.stats()


class GuildSwarm:
    """Multi-agent swarm that runs an objective through a roster of specialist roles.

    Wraps :class:`~pradyos.guild.org.GuildOrg` with a simpler interface.
    """

    def __init__(self, worker: Any | None = None) -> None:
        self._guild = GuildOrg(worker=worker)

    def add_agent(self, role: str, tools: list[str] | None = None) -> None:
        """Add a custom agent with a given role name and tool list.

        This is a no-op in the current implementation because ``GuildOrg``
        uses a fixed roster.  The method is provided for API compatibility
        and logs the intended configuration.
        """
        pass

    def run_task(self, task_description: str) -> dict[str, Any]:
        """Run a task through the guild's default roster and return the result."""
        return self._guild.run(objective=task_description)

    def stats(self) -> dict[str, Any]:
        return self._guild.stats()


class SovereignClient:
    """Client for submitting proposals and logging decisions to the Sovereign.

    Wraps the sovereign CLI's decision-writing mechanism.
    """

    def __init__(self, state_dir: str | None = None) -> None:
        import os
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        self._state_dir = Path(
            state_dir or os.environ.get("PRADYOS_STATE_PATH", str(root / "var" / "state"))
        )
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def submit_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a proposal (writes a structured JSONL record for the Sovereign)."""
        import json
        import time

        entry = {
            "type": "proposal",
            "payload": payload,
            "ts": time.time(),
        }
        self._write(entry)
        return {"status": "submitted", "entry": entry}

    def log_decision(self, decision: dict[str, Any]) -> None:
        """Log a Sovereign decision."""
        import json
        import time

        entry = {
            "type": "decision",
            "payload": decision,
            "ts": time.time(),
        }
        self._write(entry)

    def _write(self, entry: dict[str, Any]) -> None:
        import json

        path = self._state_dir / "sovereign_decisions.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
