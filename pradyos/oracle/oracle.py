"""Oracle — high-level facade wiring client, planner, and bus together.

Usage:
    oracle = Oracle()
    plan = await oracle.plan_task(task)

    # Inject into IMPERIUM as a handler:
    imperium.register_handler("research", oracle.imperium_handler)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pradyos.core.bus import EventBus, get_bus
from pradyos.core.types import TaskState
from pradyos.imperium.task import ImperiumTask
from pradyos.oracle.client import OllamaClient
from pradyos.oracle.planner import OraclePlan, OraclePlanner

log = logging.getLogger("pradyos.oracle")

AGENT_ID = "oracle"


class Oracle:
    """Top-level ORACLE facade.

    Wraps OllamaClient + OraclePlanner, emits bus events, and exposes a
    synchronous ``imperium_handler`` compatible with Imperium.register_handler.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        memory_store: Any | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._client = OllamaClient(base_url=base_url, model=model)
        self._planner = OraclePlanner(client=self._client, memory_store=memory_store)
        self._bus = bus or get_bus()
        self._memory = memory_store

    # ------------------------------------------------------------------
    # Async plan API
    # ------------------------------------------------------------------

    async def plan_task(self, task: ImperiumTask) -> OraclePlan:
        """Produce an execution plan for *task* (async)."""
        log.info("ORACLE planning task %s (%s)", task.task_id, task.intent)
        plan = await self._planner.plan(task)

        # Emit bus event so AURORA THRONE and other listeners can react
        self._bus.publish(
            "oracle.plan_ready",
            {
                "task_id": task.task_id,
                "intent": task.intent,
                "step_count": len(plan.steps),
                "requires_approval": plan.requires_approval,
                "error": plan.error,
            },
        )

        if plan.requires_approval:
            self._bus.publish(
                "oracle.approval_required",
                {
                    "task_id": task.task_id,
                    "intent": task.intent,
                    "reason": plan.approval_reason,
                },
            )
            log.info(
                "ORACLE plan for %s requires Sovereign approval: %s",
                task.task_id,
                plan.approval_reason,
            )

        return plan

    async def record_outcome(
        self,
        task_id: str,
        intent: str,
        outcome: str,
        plan: OraclePlan | None = None,
    ) -> None:
        """Record task outcome in Memory Citadel for future planning."""
        if self._memory is None:
            return
        record = {
            "task_id": task_id,
            "summary": intent,
            "outcome": outcome,
            "step_count": len(plan.steps) if plan else 0,
            "required_approval": plan.requires_approval if plan else False,
        }
        try:
            if hasattr(self._memory, "store_async"):
                await self._memory.store_async("oracle", record)
            elif hasattr(self._memory, "store"):
                self._memory.store("oracle", record)
        except Exception as e:  # noqa: BLE001
            log.debug("Memory store failed (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # IMPERIUM handler (synchronous wrapper)
    # ------------------------------------------------------------------

    def imperium_handler(self, task: ImperiumTask) -> dict[str, Any]:
        """Synchronous handler compatible with Imperium.register_handler.

        Runs the async planner in a new event loop or existing one.
        Returns a result dict that IMPERIUM's StateCore expects.
        """
        try:
            plan = asyncio.run(self.plan_task(task))
        except RuntimeError:
            # Already inside an event loop (e.g. tests) — use a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.plan_task(task))
                plan = future.result(timeout=130)

        if not plan.ok:
            return {
                "ok": False,
                "error": plan.error,
                "plan": plan.to_dict(),
            }

        if plan.requires_approval:
            # Signal IMPERIUM to ESCALATE this task
            return {
                "ok": False,
                "escalate": True,
                "escalation_reason": plan.approval_reason,
                "plan": plan.to_dict(),
            }

        return {
            "ok": True,
            "plan": plan.to_dict(),
            "step_count": len(plan.steps),
        }

    # ------------------------------------------------------------------
    # Connectivity check
    # ------------------------------------------------------------------

    async def check_ollama(self) -> dict[str, Any]:
        """Return Ollama connectivity status and available models."""
        alive = await self._client.is_alive()
        models: list[str] = []
        if alive:
            models = await self._client.list_models()
        return {
            "alive": alive,
            "base_url": self._client.base_url,
            "model": self._client.model,
            "available_models": models,
        }
