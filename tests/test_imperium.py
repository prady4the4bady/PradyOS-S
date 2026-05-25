"""IMPERIUM tests — queue, policy, DAG, checkpoint, kernel."""

from __future__ import annotations

import time
from typing import Any

import pytest

from pradyos.core.types import Priority, TaskState
from pradyos.imperium.checkpoint import CheckpointStore
from pradyos.imperium.dag import CycleDetected, DependencyGraph
from pradyos.imperium.kernel import Imperium
from pradyos.imperium.policy import PolicyCore
from pradyos.imperium.queue import TaskQueue
from pradyos.imperium.task import ImperiumTask


# ---------- queue ----------

def test_queue_priority_order():
    q = TaskQueue()
    background = q.enqueue(ImperiumTask(kind="x", priority=Priority.BACKGROUND, intent="bg"))
    operational = q.enqueue(ImperiumTask(kind="x", priority=Priority.OPERATIONAL, intent="op"))
    sovereign = q.enqueue(ImperiumTask(kind="x", priority=Priority.SOVEREIGN, intent="sv"))
    first = q.pop_runnable(lambda _t: True)
    assert first.spec.task_id == sovereign.spec.task_id
    second = q.pop_runnable(lambda _t: True)
    assert second.spec.task_id == operational.spec.task_id
    third = q.pop_runnable(lambda _t: True)
    assert third.spec.task_id == background.spec.task_id


def test_queue_respects_dependency_satisfaction():
    q = TaskQueue()
    parent = q.enqueue(ImperiumTask(kind="x", intent="parent"))
    child = q.enqueue(ImperiumTask(kind="x", intent="child",
                                    depends_on=[parent.spec.task_id]))
    # parent not done — child must not be runnable
    sat = lambda tid: False
    chosen = q.pop_runnable(sat)
    assert chosen.spec.task_id == parent.spec.task_id  # parent first
    # child still queued; pop again with parent unsatisfied → nothing
    chosen = q.pop_runnable(sat)
    assert chosen is None
    # mark parent satisfied → child becomes runnable
    sat2 = lambda tid: tid == parent.spec.task_id
    chosen = q.pop_runnable(sat2)
    assert chosen.spec.task_id == child.spec.task_id


# ---------- policy ----------

def test_policy_autonomous_path():
    p = PolicyCore()
    t = ImperiumTask(kind="titan.shell", payload={"command": "ls -la"}, intent="list /")
    assert p.is_autonomous(t)


def test_policy_destructive_requires_approval():
    p = PolicyCore()
    t = ImperiumTask(kind="titan.shell", payload={"command": "rm -rf /"},
                      intent="wipe root")
    d = p.classify(t)
    assert d.domain.value == "APPROVAL_REQUIRED"


def test_policy_project_proposal_requires_approval():
    p = PolicyCore()
    t = ImperiumTask(kind="project_proposal", intent="ORACLE proposes new project")
    d = p.classify(t)
    assert d.domain.value == "APPROVAL_REQUIRED"


# ---------- DAG ----------

def test_dag_cycle_detected():
    g = DependencyGraph()
    g.add_task("b", ["a"])
    g.add_task("c", ["b"])
    with pytest.raises(CycleDetected):
        g.add_task("a", ["c"])


def test_dag_topological_order():
    g = DependencyGraph()
    g.add_task("b", ["a"])
    g.add_task("c", ["a"])
    g.add_task("d", ["b", "c"])
    order = g.topological_order()
    assert order.index("a") < order.index("b")
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


# ---------- checkpoint ----------

def test_checkpoint_resume_non_terminal(tmp_path):
    store = CheckpointStore(state_dir=tmp_path)
    from pradyos.imperium.task import TaskRecord
    spec = ImperiumTask(kind="titan.shell", payload={"command": "echo"}, intent="x")
    rec = TaskRecord(spec=spec, state=TaskState.RUNNING)
    store.write(rec)
    # finalize one task to terminal
    spec2 = ImperiumTask(kind="titan.shell", payload={"command": "echo"}, intent="y")
    rec2 = TaskRecord(spec=spec2, state=TaskState.SUCCEEDED, finished_at=time.time())
    store.write(rec2)

    resumed = store.resume_non_terminal()
    assert len(resumed) == 1
    assert resumed[0].spec.intent == "x"


# ---------- kernel ----------

def test_kernel_runs_handler(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))

    calls: list[ImperiumTask] = []

    def h(task: ImperiumTask) -> dict[str, Any]:
        calls.append(task)
        return {"ok": True, "echo": task.payload}

    kern.register_handler("custom", h)
    rec = kern.submit(ImperiumTask(kind="custom", intent="hello", payload={"v": 1}))
    out = kern.run_one()
    assert out is not None
    assert out.state is TaskState.SUCCEEDED
    assert calls and calls[0].payload == {"v": 1}


def test_kernel_escalates_destructive_command(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))
    kern.register_handler("titan.shell", lambda t: {"ok": True})
    rec = kern.submit(ImperiumTask(kind="titan.shell",
                                    payload={"command": "rm -rf /"},
                                    intent="wipe"))
    out = kern.run_one()
    assert out.state is TaskState.ESCALATED
    assert kern.pending_approvals()


def test_kernel_approve_unblocks_escalated(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))

    def h(task: ImperiumTask) -> dict[str, Any]:
        return {"ok": True}

    # Use a kind the constitution catches once via project_proposal handler
    # (which always escalates), then is registered to succeed after approval.
    # After approval, we re-register the handler to bypass the escalation path.
    kern.register_handler("project_proposal", lambda t: {"escalate": True,
                                                          "reason": "needs approval",
                                                          "rule": "new_project_proposal"})
    rec = kern.submit(ImperiumTask(kind="project_proposal",
                                    intent="Phase 1 build"))
    kern.run_one()  # escalates via constitution
    assert rec.state is TaskState.ESCALATED
    assert kern.approve(rec.spec.task_id) is True
    found_approval = any("APPROVED" in r.summary for r in isolated_audit.tail(30))
    assert found_approval
    # Approval moves the record back to QUEUED — verify state transition.
    assert kern.get(rec.spec.task_id).state is TaskState.QUEUED


def test_kernel_reject_marks_cancelled(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))
    kern.register_handler("project_proposal", lambda t: {"ok": True})
    rec = kern.submit(ImperiumTask(kind="project_proposal", intent="new init"))
    kern.run_one()
    assert rec.state is TaskState.ESCALATED
    assert kern.reject(rec.spec.task_id, reason="too speculative")
    assert rec.state is TaskState.CANCELLED


def test_kernel_publishes_events(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))
    seen: list[str] = []
    isolated_bus.subscribe("*", lambda t, p: seen.append(t))
    kern.register_handler("noop", lambda t: {"ok": True})
    kern.submit(ImperiumTask(kind="noop", intent="x"))
    kern.run_one()
    assert "imperium.task_queued" in seen
    assert "imperium.task_running" in seen
    assert "imperium.task_succeeded" in seen


def test_kernel_handler_failure_is_recorded(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))
    kern.register_handler("flaky", lambda t: {"ok": False, "error": "nope"})
    rec = kern.submit(ImperiumTask(kind="flaky", intent="x"))
    kern.run_one()
    assert rec.state is TaskState.FAILED
    assert rec.last_error == "nope"
