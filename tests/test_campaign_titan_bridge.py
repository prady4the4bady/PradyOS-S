"""Tests for Campaign → TITAN Bridge (Phase 4A).

All tests are self-contained with mocks — no live IMPERIUM, no Ollama.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pradyos.campaign_titan_bridge import CampaignTitanBridge
from pradyos.core.bus import EventBus
from pradyos.core.ids import new_id
from pradyos.imperium.task import ImperiumTask
from pradyos.titan_ops.instruction import InstructionKind, TitanInstruction


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class MockKernel:
    """Minimal IMPERIUM kernel stub that records submitted tasks."""

    def __init__(self) -> None:
        self._tasks: list[ImperiumTask] = []

    def submit(self, task: ImperiumTask) -> str:
        self._tasks.append(task)
        return task.task_id

    @property
    def tasks(self) -> list[ImperiumTask]:
        return list(self._tasks)


def _make_instruction(
    command: str = "echo hello",
    kind: InstructionKind = InstructionKind.SHELL,
    lane: str = "unprivileged",
) -> TitanInstruction:
    return TitanInstruction(
        agent_id="test",
        kind=kind,
        command=command,
        intent=f"run {command}",
    )


def _make_plan(steps: list[TitanInstruction], requires_approval: bool = False) -> Any:
    plan = MagicMock()
    plan.steps = steps
    plan.requires_approval = requires_approval
    plan.approval_reason = "needs human sign-off" if requires_approval else ""
    return plan


# ---------------------------------------------------------------------------
# 1. submit_plan — correct number of tasks submitted
# ---------------------------------------------------------------------------


def test_submit_plan_task_count() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    steps = [_make_instruction(f"step {i}") for i in range(3)]
    plan = _make_plan(steps)

    ids = bridge.submit_plan(plan, campaign_id="camp-1", campaign_goal="do things")

    assert len(ids) == 3
    assert len(kernel.tasks) == 3


# ---------------------------------------------------------------------------
# 2. submit_plan — correct sequential DAG dependencies
# ---------------------------------------------------------------------------


def test_submit_plan_sequential_deps() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    steps = [_make_instruction(f"cmd-{i}") for i in range(4)]
    plan = _make_plan(steps)
    ids = bridge.submit_plan(plan, campaign_id="camp-2", campaign_goal="chain")

    tasks = kernel.tasks
    # Step 0 has no deps
    assert tasks[0].depends_on == []
    # Step N depends on step N-1
    for i in range(1, len(tasks)):
        assert tasks[i].depends_on == [ids[i - 1]], (
            f"step {i} depends_on mismatch: {tasks[i].depends_on!r}"
        )


# ---------------------------------------------------------------------------
# 3. submit_plan — task kinds are prefixed with "titan."
# ---------------------------------------------------------------------------


def test_submit_plan_task_kinds() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    steps = [
        _make_instruction("ls", kind=InstructionKind.SHELL),
        _make_instruction("htop", kind=InstructionKind.PACKAGE),
        _make_instruction("touch /tmp/x", kind=InstructionKind.FILE),
    ]
    plan = _make_plan(steps)
    bridge.submit_plan(plan, "camp-3", "mixed kinds")

    kinds = [t.kind for t in kernel.tasks]
    assert kinds == ["titan.shell", "titan.package", "titan.file"]


# ---------------------------------------------------------------------------
# 4. submit_plan — campaign_id propagated in task metadata
# ---------------------------------------------------------------------------


def test_submit_plan_campaign_metadata() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    plan = _make_plan([_make_instruction("echo ok")])
    bridge.submit_plan(plan, campaign_id="camp-99", campaign_goal="meta check")

    assert kernel.tasks[0].metadata["campaign_id"] == "camp-99"
    assert kernel.tasks[0].metadata["step_index"] == 0


# ---------------------------------------------------------------------------
# 5. Fallback path — no plan / empty steps → single titan.shell task
# ---------------------------------------------------------------------------


def test_fallback_no_plan() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    ids = bridge.submit_plan(None, campaign_id="camp-fb", campaign_goal="my raw goal")

    assert len(ids) == 1
    assert len(kernel.tasks) == 1
    task = kernel.tasks[0]
    assert task.kind == "titan.shell"
    assert task.intent == "my raw goal"
    assert task.metadata.get("fallback") is True


def test_fallback_empty_steps() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    plan = _make_plan([])  # plan exists but has no steps
    ids = bridge.submit_plan(plan, campaign_id="camp-fb2", campaign_goal="empty plan goal")

    assert len(ids) == 1
    assert kernel.tasks[0].kind == "titan.shell"
    assert kernel.tasks[0].metadata.get("fallback") is True


# ---------------------------------------------------------------------------
# 6. run() — campaign reaches SUCCEEDED when all tasks complete
# ---------------------------------------------------------------------------


async def test_run_succeeds_when_all_complete() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus, timeout_sec=5.0)

    steps = [_make_instruction("step-a"), _make_instruction("step-b")]
    plan = _make_plan(steps)
    campaign_id = "camp-run-ok"

    # Fire task.completed events after a short delay from a background thread
    async def _fire_completions() -> None:
        await asyncio.sleep(0.05)
        # submit_plan records task_ids on kernel
        for task in kernel.tasks:
            bus.publish("task.completed", {"task_id": task.task_id})

    # Run bridge + fire events concurrently
    fire_task = asyncio.create_task(_fire_completions())
    result = await bridge.run(plan, campaign_id, "run test")
    await fire_task

    assert result["ok"] is True
    assert result["campaign_id"] == campaign_id
    assert len(result["task_ids"]) == 2
    assert all(v == "completed" for v in result["results"].values())
    assert result["error"] is None


# ---------------------------------------------------------------------------
# 7. run() — campaign fails when a task fails
# ---------------------------------------------------------------------------


async def test_run_fails_when_task_fails() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus, timeout_sec=5.0)

    steps = [_make_instruction("fail-step")]
    plan = _make_plan(steps)

    async def _fire_failure() -> None:
        await asyncio.sleep(0.05)
        for task in kernel.tasks:
            bus.publish("task.failed", {"task_id": task.task_id})

    fire_task = asyncio.create_task(_fire_failure())
    result = await bridge.run(plan, "camp-fail", "should fail")
    await fire_task

    assert result["ok"] is False
    assert "failed" in result["error"]
    assert list(result["results"].values()) == ["failed"]


# ---------------------------------------------------------------------------
# 8. Approval-required plan — requires_approval propagated to task metadata
# ---------------------------------------------------------------------------


def test_approval_required_propagated() -> None:
    bus = EventBus()
    kernel = MockKernel()
    bridge = CampaignTitanBridge(kernel=kernel, bus=bus)

    steps = [_make_instruction("rm -rf /")]
    plan = _make_plan(steps, requires_approval=True)
    bridge.submit_plan(plan, "camp-appr", "dangerous op")

    task = kernel.tasks[0]
    assert task.metadata.get("requires_approval") is True
