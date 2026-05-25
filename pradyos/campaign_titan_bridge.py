"""Campaign → TITAN Bridge (Phase 4A).

After ``CampaignEngine`` receives an ``OraclePlan``, this bridge submits
each plan step as a real ``ImperiumTask`` (kind ``titan.*``) into the
IMPERIUM kernel queue with correct DAG dependencies (step N depends on
step N-1).

Key behaviours
--------------
* Steps submitted in order; each depends on the previous via
  ``ImperiumTask.depends_on``.
* If a ``TitanInstruction`` requires Constitution approval the task is
  submitted as-is — IMPERIUM's normal escalation path handles it.
* ``CampaignTitanBridge.run()`` awaits all submitted tasks by listening
  on EventBus ``task.completed`` / ``task.failed`` events.
* If ORACLE is offline (no plan / empty steps) → fall back to submitting
  a **single** ``titan.shell`` task whose command is the raw campaign goal.

Windows safety
--------------
* All paths via ``pathlib.Path``; no ``AF_UNIX``; no ``fork()``
* Standard ``asyncio`` event loop (no uvloop)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from pradyos.core.bus import EventBus, get_bus
from pradyos.core.ids import new_id
from pradyos.imperium.task import ImperiumTask

log = logging.getLogger("pradyos.campaign_titan_bridge")


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class CampaignTitanBridge:
    """Submits OraclePlan steps as ImperiumTasks into the IMPERIUM kernel.

    Parameters
    ----------
    kernel:
        An object with a ``submit(task: ImperiumTask) -> str`` method
        (the IMPERIUM kernel or a compatible mock).
    bus:
        EventBus to listen for ``task.completed`` / ``task.failed``.
    timeout_sec:
        How long (in seconds) to wait for all tasks to finish before
        raising ``asyncio.TimeoutError``.
    """

    def __init__(
        self,
        kernel: Any,
        bus: EventBus | None = None,
        timeout_sec: float = 120.0,
    ) -> None:
        self._kernel = kernel
        self._bus = bus or get_bus()
        self._timeout = timeout_sec

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_plan(
        self,
        plan: Any,  # OraclePlan — avoid hard import for decoupling
        campaign_id: str,
        campaign_goal: str,
        submitted_by: str = "campaign_engine",
    ) -> list[str]:
        """Submit all plan steps as ImperiumTasks.

        Returns a list of ``task_id`` strings in submission order.

        Fallback: if *plan* is ``None`` or has no steps, submits a single
        ``titan.shell`` task whose command is *campaign_goal*.
        """
        steps = getattr(plan, "steps", None) or []

        if not steps:
            # ── FALLBACK path ─────────────────────────────────────────
            task = ImperiumTask(
                kind="titan.shell",
                intent=campaign_goal,
                payload={"command": campaign_goal},
                submitted_by=submitted_by,
                metadata={"campaign_id": campaign_id, "fallback": True},
            )
            task_id = self._kernel.submit(task)
            log.info(
                "Bridge FALLBACK: single titan.shell task %s for campaign %s",
                task_id,
                campaign_id,
            )
            return [task_id]

        # ── Normal path ───────────────────────────────────────────────
        submitted_ids: list[str] = []
        prev_id: str | None = None

        for idx, instr in enumerate(steps):
            # Convert TitanInstruction kind to task kind string
            raw_kind = getattr(instr, "kind", None)
            kind_val = raw_kind.value if hasattr(raw_kind, "value") else str(raw_kind or "shell")
            task_kind = f"titan.{kind_val}"

            depends: list[str] = [prev_id] if prev_id is not None else []

            task = ImperiumTask(
                kind=task_kind,
                intent=getattr(instr, "intent", f"step {idx}"),
                payload={
                    "command": getattr(instr, "command", None) or "",
                    "args": getattr(instr, "args", {}),
                    "lane": (
                        getattr(instr, "lane", None).value
                        if hasattr(getattr(instr, "lane", None), "value")
                        else str(getattr(instr, "lane", "unprivileged"))
                    ),
                    "timeout_sec": getattr(instr, "timeout_sec", 60.0),
                    "cwd": getattr(instr, "cwd", None),
                    "env": getattr(instr, "env", {}),
                    "rollback_hook": getattr(instr, "rollback_hook", None),
                    "instruction_id": getattr(instr, "instruction_id", new_id("ti")),
                },
                depends_on=depends,
                submitted_by=submitted_by,
                metadata={
                    "campaign_id": campaign_id,
                    "step_index": idx,
                    "requires_approval": getattr(plan, "requires_approval", False),
                },
            )

            task_id = self._kernel.submit(task)
            submitted_ids.append(task_id)
            prev_id = task_id

            log.debug(
                "Bridge submitted task %s (step %d/%d) for campaign %s depends=%s",
                task_id,
                idx + 1,
                len(steps),
                campaign_id,
                depends,
            )

        log.info(
            "Bridge submitted %d tasks for campaign %s",
            len(submitted_ids),
            campaign_id,
        )
        return submitted_ids

    async def run(
        self,
        plan: Any,
        campaign_id: str,
        campaign_goal: str,
        submitted_by: str = "campaign_engine",
    ) -> dict[str, Any]:
        """Submit tasks and await their completion via EventBus events.

        Returns a summary dict::

            {
                "ok": bool,
                "campaign_id": str,
                "task_ids": [...],
                "results": {task_id: "completed"|"failed", ...},
                "error": str | None,
            }
        """
        task_ids = self.submit_plan(plan, campaign_id, campaign_goal, submitted_by)
        if not task_ids:
            return {
                "ok": False,
                "campaign_id": campaign_id,
                "task_ids": [],
                "results": {},
                "error": "no tasks submitted",
            }

        # Wait for all tasks to finish via EventBus signals
        remaining = set(task_ids)
        results: dict[str, str] = {}
        done_event = asyncio.Event()
        lock = threading.Lock()

        def _on_task_event(topic: str, payload: dict[str, Any]) -> None:
            tid = payload.get("task_id") or payload.get("id")
            if tid not in remaining:
                return
            with lock:
                if topic.endswith("completed"):
                    results[tid] = "completed"
                elif topic.endswith("failed"):
                    results[tid] = "failed"
                remaining.discard(tid)
                if not remaining:
                    # Wake the waiting coroutine from this thread
                    try:
                        loop = asyncio.get_event_loop()
                        loop.call_soon_threadsafe(done_event.set)
                    except Exception:  # noqa: BLE001
                        done_event.set()

        self._bus.subscribe("task.completed", _on_task_event)
        self._bus.subscribe("task.failed", _on_task_event)

        try:
            await asyncio.wait_for(done_event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            log.warning(
                "Bridge timeout waiting for tasks; remaining=%s", remaining
            )
            # Mark timed-out tasks as failed
            for tid in remaining:
                results[tid] = "failed"
        finally:
            self._bus.unsubscribe("task.completed", _on_task_event)
            self._bus.unsubscribe("task.failed", _on_task_event)

        all_ok = all(v == "completed" for v in results.values())
        return {
            "ok": all_ok,
            "campaign_id": campaign_id,
            "task_ids": task_ids,
            "results": results,
            "error": None if all_ok else "one or more tasks failed",
        }
