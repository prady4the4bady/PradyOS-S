"""ORACLE planner — ImperiumTask → OraclePlan (TitanInstruction[]).

The planner is the intelligence layer of ORACLE. Given a task, it:
  1. Queries MEMORY CITADEL for relevant prior outcomes.
  2. Constructs a structured system prompt encoding the task + context.
  3. Calls Ollama (qwen2.5:7b) to produce a JSON execution plan.
  4. Parses the response into a list of TitanInstruction objects.
  5. Classifies each instruction against the Constitution.
  6. Returns an OraclePlan — ready for CAMPAIGN ENGINE or direct dispatch.

Plan JSON schema (produced by Ollama):

    {
        "intent":   "Install and configure nginx",
        "steps": [
            {
                "kind":    "shell",
                "command": "winget install nginx",
                "lane":    "privileged",
                "intent":  "Install nginx via winget",
                "rollback_hook": "winget uninstall nginx",
                "timeout_sec": 120
            },
            ...
        ],
        "requires_approval": false,
        "approval_reason":   ""
    }
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pradyos.core.constitution import ApprovalDomain, default_constitution
from pradyos.core.types import ExecutionLane
from pradyos.imperium.task import ImperiumTask
from pradyos.oracle.client import OllamaClient, OllamaError
from pradyos.titan_ops.instruction import InstructionKind, TitanInstruction

log = logging.getLogger("pradyos.oracle.planner")

# ---------------------------------------------------------------------------
# Plan model
# ---------------------------------------------------------------------------

APPROVAL_REQUIRED = ApprovalDomain.APPROVAL_REQUIRED


@dataclass
class OraclePlan:
    """The output of ORACLE planning for one ImperiumTask."""

    task_id: str
    task_intent: str
    steps: list[TitanInstruction] = field(default_factory=list)
    requires_approval: bool = False
    approval_reason: str = ""
    raw_llm_response: str = ""
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_intent": self.task_intent,
            "requires_approval": self.requires_approval,
            "approval_reason": self.approval_reason,
            "steps": [s.to_dict() for s in self.steps],
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are ORACLE, the autonomous execution planner for PRADY OS.
Your job is to translate a task description into a precise, minimal
execution plan as JSON. The machine runs Windows 11.

Rules:
- Prefer winget for package installs; use pip for Python packages.
- Use full pathlib-style Windows paths (C:\\\\Users\\\\... not /home/...).
- Never suggest rm -rf, mkfs, dd, shutdown, or any destructive command
  unless explicitly requested AND it is the only option.
- If a step could corrupt data or is irreversible, set "requires_approval": true.
- Keep steps minimal and idempotent.
- Always provide a "rollback_hook" shell command where meaningful.

Output ONLY valid JSON in this exact schema — no markdown, no prose:
{
  "intent": "<overall intent summary>",
  "steps": [
    {
      "kind": "shell|package|file|service|process",
      "command": "<command string or null>",
      "lane": "unprivileged|privileged|sandbox",
      "intent": "<one-line description>",
      "rollback_hook": "<undo command or null>",
      "timeout_sec": 60,
      "args": {}
    }
  ],
  "requires_approval": false,
  "approval_reason": ""
}
"""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class OraclePlanner:
    """Converts an ImperiumTask into an OraclePlan via Ollama + memory."""

    def __init__(
        self,
        client: OllamaClient | None = None,
        memory_store: Any | None = None,  # CitadelStore — optional to avoid hard dep
    ) -> None:
        self._client = client or OllamaClient()
        self._memory = memory_store
        self._constitution = default_constitution()

    async def plan(self, task: ImperiumTask) -> OraclePlan:
        """Produce an execution plan for *task*. Never raises; errors are in plan.error."""
        # ---- 1. Memory context query ----
        memory_context: list[dict[str, Any]] = []
        if self._memory is not None:
            try:
                results = await _safe_memory_query(self._memory, task.intent or task.kind)
                memory_context = results
            except Exception as e:  # noqa: BLE001
                log.debug("Memory query failed (non-fatal): %s", e)

        # ---- 2. Build user prompt ----
        user_prompt = _build_user_prompt(task, memory_context)

        # ---- 3. Call Ollama ----
        raw_response = ""
        try:
            raw_response = await self._client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
            )
        except OllamaError as e:
            log.warning("Ollama unavailable for task %s: %s", task.task_id, e)
            return OraclePlan(
                task_id=task.task_id,
                task_intent=task.intent,
                error=f"Ollama error: {e}",
                raw_llm_response="",
                memory_context=memory_context,
            )

        # ---- 4. Parse response ----
        plan_dict, parse_error = _parse_plan_json(raw_response)
        if parse_error:
            log.warning("Plan parse error for %s: %s", task.task_id, parse_error)
            return OraclePlan(
                task_id=task.task_id,
                task_intent=task.intent,
                error=parse_error,
                raw_llm_response=raw_response,
                memory_context=memory_context,
            )

        # ---- 5. Build TitanInstructions ----
        steps, build_error = _build_instructions(task, plan_dict)
        if build_error:
            return OraclePlan(
                task_id=task.task_id,
                task_intent=task.intent,
                error=build_error,
                raw_llm_response=raw_response,
                memory_context=memory_context,
            )

        # ---- 6. Constitutional check ----
        requires_approval = bool(plan_dict.get("requires_approval", False))
        approval_reason = plan_dict.get("approval_reason", "")

        if not requires_approval:
            for step in steps:
                decision = self._constitution.classify(
                    kind=step.kind.value,
                    summary=step.intent,
                    detail={"command": step.command or ""},
                )
                if decision.domain is APPROVAL_REQUIRED:
                    requires_approval = True
                    approval_reason = (
                        f"Constitutional rule '{decision.matched_rule}': {decision.reason}"
                    )
                    break

        return OraclePlan(
            task_id=task.task_id,
            task_intent=task.intent,
            steps=steps,
            requires_approval=requires_approval,
            approval_reason=approval_reason,
            raw_llm_response=raw_response,
            memory_context=memory_context,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_prompt(task: ImperiumTask, memory_context: list[dict[str, Any]]) -> str:
    lines = [
        f"Task ID: {task.task_id}",
        f"Kind: {task.kind}",
        f"Intent: {task.intent or '(none)'}",
        f"Priority: {task.priority.value}",
    ]
    if task.payload:
        lines.append(f"Payload: {json.dumps(task.payload, default=str)}")
    if memory_context:
        lines.append("\nRelevant prior outcomes from Memory Citadel:")
        for i, m in enumerate(memory_context[:5], 1):
            lines.append(f"  [{i}] {m.get('summary', '')} — outcome: {m.get('outcome', '?')}")
    lines.append("\nProduce an execution plan as JSON.")
    return "\n".join(lines)


def _parse_plan_json(raw: str) -> tuple[dict[str, Any], str | None]:
    """Extract and parse the JSON plan from the LLM response."""
    # Strip markdown fences if present
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct parse first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, None
    except json.JSONDecodeError:
        pass

    # Try finding the outermost {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj, None
        except json.JSONDecodeError as e:
            return {}, f"JSON parse failed: {e} — raw: {text[:200]}"

    return {}, f"No JSON object found in response: {text[:200]}"


def _build_instructions(
    task: ImperiumTask, plan: dict[str, Any]
) -> tuple[list[TitanInstruction], str | None]:
    """Convert plan dict → list[TitanInstruction]. Returns (steps, error)."""
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list):
        return [], f"plan.steps missing or not a list: {type(raw_steps)}"

    steps: list[TitanInstruction] = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        try:
            kind = InstructionKind(raw.get("kind", "shell"))
        except ValueError:
            kind = InstructionKind.SHELL

        try:
            lane = ExecutionLane(raw.get("lane", "unprivileged"))
        except ValueError:
            lane = ExecutionLane.UNPRIVILEGED

        steps.append(
            TitanInstruction(
                agent_id="oracle",
                kind=kind,
                command=raw.get("command"),
                args=raw.get("args") or {},
                lane=lane,
                intent=raw.get("intent", f"step {i + 1}"),
                timeout_sec=float(raw.get("timeout_sec", 60)),
                rollback_hook=raw.get("rollback_hook"),
                correlation_id=task.task_id,
            )
        )

    return steps, None


async def _safe_memory_query(
    memory_store: Any, query: str
) -> list[dict[str, Any]]:
    """Query memory_store regardless of whether it's sync or async."""
    if hasattr(memory_store, "query_async"):
        return await memory_store.query_async(query, n_results=5)
    elif hasattr(memory_store, "query"):
        return memory_store.query(query, n_results=5)
    return []
