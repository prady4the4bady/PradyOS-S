"""IMPERIUM kernel — the orchestrator (Phase 3: ORACLE dispatch loop).

Phase 3 additions on top of the Phase 1 / Phase 2 four-core architecture:

  OracleDispatch   — ORACLE plans every task before TITAN executes it.
                     If ORACLE is offline the kernel falls back to the
                     registered handler transparently (no crash, no hang).
  SovereignPoller  — Daemon thread that reads
                     var/state/sovereign_decisions.jsonl and applies
                     approve / reject decisions written by the
                     ``pradyos-sovereign`` CLI — no Unix sockets, TCP only.

Built-in handlers:
    titan.shell     -> TITAN OPS shell command via TitanClient
    titan.package   -> TITAN OPS package op
    titan.file      -> TITAN OPS file op
    titan.service   -> TITAN OPS service op
    titan.process   -> TITAN OPS process op
    research        -> Phase 3: routed through ORACLE if available
    project_proposal-> always escalates (Sovereign approval)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.constitution import ApprovalDomain
from pradyos.core.types import ExecutionLane, TaskState
from pradyos.imperium.checkpoint import CheckpointStore
from pradyos.imperium.dag import DependencyGraph
from pradyos.imperium.policy import PolicyCore
from pradyos.imperium.policy_engine import PolicyEngine, PolicyViolationError
from pradyos.imperium.queue import TaskQueue
from pradyos.imperium.recovery import RecoveryCore
from pradyos.imperium.scheduler import SchedulerCore
from pradyos.imperium.state_core import StateCore
from pradyos.imperium.task import ImperiumTask, TaskRecord

log = logging.getLogger("pradyos.imperium")

Handler = Callable[[ImperiumTask], dict[str, Any]]

_DEFAULT_STATE_DIR = Path(
    os.environ.get(
        "PRADYOS_STATE_PATH",
        Path(__file__).resolve().parents[2] / "var" / "state",
    )
)
_DECISIONS_FILE = _DEFAULT_STATE_DIR / "sovereign_decisions.jsonl"

# Kinds that bypass the ORACLE intercept (always concrete or always escalate)
_ORACLE_BYPASS_KINDS = frozenset(
    {
        "project_proposal",
    }
)


class Imperium:
    """The orchestration kernel — Phase 3 ORACLE dispatch loop."""

    AGENT_ID = "imperium"

    def __init__(
        self,
        audit: AuditLog | None = None,
        bus: EventBus | None = None,
        policy: PolicyCore | None = None,
        checkpoint: CheckpointStore | None = None,
        workers: int = 4,
        scheduler: SchedulerCore | None = None,
        state_core: StateCore | None = None,
        recovery_core: RecoveryCore | None = None,
        # Phase 3
        oracle: Any | None = None,
        memory: Any | None = None,
        # Phase 11
        self_heal_engine: Any | None = None,
        # Phase 14
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.audit = audit or get_audit_log()
        self.bus = bus or get_bus()

        _checkpoint = checkpoint or CheckpointStore()

        self.scheduler: SchedulerCore = scheduler or SchedulerCore()
        self.policy: PolicyCore = policy or PolicyCore()
        self.state: StateCore = state_core or StateCore(
            checkpoint=_checkpoint, audit=self.audit, bus=self.bus
        )
        # Phase 11: store before building RecoveryCore so the hook can be wired.
        self._self_heal_engine: Any | None = self_heal_engine

        self.recovery: RecoveryCore = recovery_core or RecoveryCore(
            state=self.state,
            audit=self.audit,
            bus=self.bus,
            scheduler=self.scheduler,
            on_exhausted=self._self_heal_hook,
        )

        self.checkpoint: CheckpointStore = _checkpoint
        self.queue: TaskQueue = self.scheduler._queue
        self.dag: DependencyGraph = self.scheduler._dag

        # Phase 3
        self._oracle: Any | None = oracle
        self._memory: Any | None = memory

        # Phase 14: policy engine (falls back to permissive engine if not injected)
        self._policy_engine: PolicyEngine = policy_engine or PolicyEngine()

        self._handlers: dict[str, Handler] = {}
        self._approvals: dict[str, dict[str, Any]] = {}
        self._approvals_lock = threading.Lock()
        self._workers = max(1, workers)
        self._stop = threading.Event()
        self._worker_threads: list[threading.Thread] = []
        self._tick = threading.Event()
        self._register_default_handlers()

        self._decisions_path: Path = _DECISIONS_FILE
        self._decisions_seen: int = 0
        self._decisions_lock = threading.Lock()

    # ---------- public API ----------

    def register_handler(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def wire_oracle(self, oracle: Any, memory: Any | None = None) -> None:
        """Attach (or replace) the ORACLE instance at runtime."""
        self._oracle = oracle
        if memory is not None:
            self._memory = memory
        log.info("ORACLE wired into IMPERIUM dispatch loop")

    def submit(self, task: ImperiumTask) -> TaskRecord:
        from pradyos.imperium.dag import CycleDetected

        try:
            rec = self.scheduler.submit(task)
        except CycleDetected as e:
            rec = TaskRecord(
                spec=task, state=TaskState.FAILED, last_error=str(e), finished_at=time.time()
            )
            self.state.write(rec)
            self.audit.record(
                agent_id=task.submitted_by,
                kind="state",
                summary=f"task rejected: {e}",
                detail=rec.to_dict(),
                correlation_id=task.task_id,
            )
            return rec
        self.state.write(rec)
        self.audit.record(
            agent_id=task.submitted_by,
            kind="state",
            summary=f"queued: {task.intent or task.kind}",
            detail=rec.to_dict(),
            correlation_id=task.task_id,
        )
        self.bus.publish("imperium.task_queued", rec.to_dict())
        self._tick.set()
        return rec

    def approve(self, task_id: str, approver: str = "sovereign") -> bool:
        rec = self.scheduler.get(task_id)
        if rec is None or rec.state != TaskState.ESCALATED:
            return False
        with self._approvals_lock:
            self._approvals[task_id] = {"approved": True, "by": approver, "at": time.time()}
        self.state.mark_approved(rec, approver)
        self.audit.record(
            agent_id=approver,
            kind="approval",
            summary=f"APPROVED: {rec.spec.intent or rec.spec.kind}",
            detail={"task_id": task_id, "by": approver},
            correlation_id=task_id,
        )
        self.bus.publish("imperium.task_approved", rec.to_dict())
        self._tick.set()
        return True

    def reject(self, task_id: str, approver: str = "sovereign", reason: str = "") -> bool:
        rec = self.scheduler.get(task_id)
        if rec is None or rec.state != TaskState.ESCALATED:
            return False
        with self._approvals_lock:
            self._approvals[task_id] = {"approved": False, "by": approver, "at": time.time()}
        self.state.mark_rejected(rec, approver, reason)
        self.audit.record(
            agent_id=approver,
            kind="approval",
            summary=f"REJECTED: {rec.spec.intent or rec.spec.kind}",
            detail={"task_id": task_id, "by": approver, "reason": reason},
            correlation_id=task_id,
        )
        return True

    def pending_approvals(self) -> list[TaskRecord]:
        return self.scheduler.pending_approvals()

    def get(self, task_id: str) -> TaskRecord | None:
        return self.scheduler.get(task_id)

    def stats(self) -> dict[str, Any]:
        s = self.scheduler.stats()
        dlq = self.recovery.dead_letter_queue()
        s["dead_letter_queue"] = len(dlq)
        s["oracle_wired"] = self._oracle is not None
        s["memory_wired"] = self._memory is not None
        return s

    def dead_letter_queue(self) -> list[Any]:
        return self.recovery.dead_letter_queue()

    # ---------- lifecycle ----------

    def start(self) -> None:
        for resumed in self.state.resume_non_terminal():
            self.scheduler.requeue(resumed.spec)
            log.info("resumed %s (%s)", resumed.spec.task_id, resumed.spec.kind)

        oracle_status = "ONLINE" if self._oracle is not None else "offline (direct dispatch)"
        log.info("ORACLE status: %s", oracle_status)

        self._stop.clear()
        for i in range(self._workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"imperium-worker-{i}",
                daemon=True,
            )
            t.start()
            self._worker_threads.append(t)

        poller = threading.Thread(
            target=self._sovereign_poller_loop,
            name="sovereign-decisions-poller",
            daemon=True,
        )
        poller.start()
        self._worker_threads.append(poller)
        log.info("IMPERIUM started (%d workers + sovereign poller)", self._workers)

    def stop(self) -> None:
        self._stop.set()
        self._tick.set()
        for t in self._worker_threads:
            t.join(timeout=2)

    def run_one(self) -> TaskRecord | None:
        return self._step()

    # ---------- ORACLE dispatch (Phase 3) ----------

    def _oracle_intercept(self, rec: TaskRecord) -> bool:
        """Attempt ORACLE-driven planning + TITAN dispatch.

        Returns True  — task fully handled (success / escalation / recovery)
        Returns False — ORACLE unavailable or bypassed; use direct handler
        """
        if self._oracle is None:
            return False

        task = rec.spec

        if task.kind in _ORACLE_BYPASS_KINDS:
            return False

        if task.payload.get("_skip_oracle"):
            return False

        log.debug("ORACLE intercepting %s (%s)", task.task_id[:8], task.kind)

        # 1. Plan
        try:
            plan_result = self._oracle.imperium_handler(task)
        except Exception as e:
            log.warning(
                "ORACLE unavailable for %s: %s — falling back to direct dispatch",
                task.task_id[:8],
                e,
            )
            return False

        # Oracle hard failure (offline / parse error) -> fall through
        if not plan_result.get("ok") and not plan_result.get("escalate"):
            log.info(
                "ORACLE failed for %s: %s — direct dispatch fallback",
                task.task_id[:8],
                plan_result.get("error", "unknown"),
            )
            return False

        # 2. Store plan in Memory Citadel
        plan_dict: dict[str, Any] = plan_result.get("plan") or {}
        if self._memory is not None and plan_dict:
            try:
                self._memory.store(
                    "oracle",
                    {
                        "task_id": task.task_id,
                        "intent": task.intent or task.kind,
                        "summary": f"Plan for: {task.intent or task.kind}",
                        "outcome": "planned",
                    },
                )
            except Exception as e:
                log.debug("Memory Citadel store failed (non-fatal): %s", e)

        self.bus.publish(
            "oracle.plan_stored",
            {
                "task_id": task.task_id,
                "intent": task.intent,
                "step_count": len(plan_dict.get("steps", [])),
            },
        )

        # 3. Escalation
        if plan_result.get("escalate"):
            reason = plan_result.get("escalation_reason") or "ORACLE constitutional block"
            self.state.mark_escalated(rec, reason, "oracle_constitutional")
            self.audit.record(
                agent_id=self.AGENT_ID,
                kind="approval",
                summary=f"ORACLE ESCALATION: {task.intent or task.kind}",
                detail={"task_id": task.task_id, "reason": reason},
                correlation_id=task.task_id,
            )
            self.bus.publish(
                "oracle.task_escalated",
                {
                    "task_id": task.task_id,
                    "intent": task.intent,
                    "reason": reason,
                },
            )
            log.info("ORACLE escalated %s: %s", task.task_id[:8], reason)
            return True

        # 4. Dispatch plan steps to TITAN OPS
        steps = plan_dict.get("steps", [])
        self.state.mark_running(rec)

        if not steps:
            self.state.mark_succeeded(
                rec,
                {
                    "ok": True,
                    "source": "oracle",
                    "note": "ORACLE produced empty plan — treated as success",
                },
            )
            self._tick.set()
            self._store_oracle_outcome(task, "success")
            return True

        last_result: dict[str, Any] = {"ok": True}
        for i, step in enumerate(steps):
            kind = f"titan.{step.get('kind', 'shell')}"
            handler = self._handlers.get(kind)

            if handler is None:
                last_result = {
                    "ok": False,
                    "error": f"No TITAN handler for kind: {step.get('kind')!r}",
                }
                break

            step_task = ImperiumTask(
                kind=kind,
                payload={
                    "command": step.get("command"),
                    "lane": step.get("lane", ExecutionLane.UNPRIVILEGED.value),
                    "args": step.get("args") or {},
                    "rollback_hook": step.get("rollback_hook"),
                    "timeout_sec": step.get("timeout_sec", 60),
                    "_skip_oracle": True,
                },
                intent=step.get("intent", f"Step {i + 1}"),
                submitted_by="oracle",
            )

            try:
                r = handler(step_task)
            except Exception as e:
                r = {"ok": False, "error": f"Step {i + 1} handler raised: {e}"}

            last_result = r
            if not r.get("ok"):
                break

        # 5. Final state transition
        if last_result.get("ok"):
            self.state.mark_succeeded(
                rec,
                {
                    **last_result,
                    "source": "oracle",
                    "step_count": len(steps),
                },
            )
            self._tick.set()
            self._store_oracle_outcome(task, "success")
        else:
            err = last_result.get("error") or "oracle plan step failed"
            self.recovery.handle_failure(rec, err)
            self._store_oracle_outcome(task, "failure")

        return True

    def _store_oracle_outcome(self, task: ImperiumTask, outcome: str) -> None:
        if self._memory is None:
            return
        try:
            self._memory.store(
                "oracle",
                {
                    "task_id": task.task_id,
                    "intent": task.intent or task.kind,
                    "summary": f"Outcome for: {task.intent or task.kind}",
                    "outcome": outcome,
                },
            )
        except Exception as e:
            log.debug("Memory Citadel outcome store failed (non-fatal): %s", e)

    # ---------- Sovereign decisions poller ----------

    def _sovereign_poller_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._process_sovereign_decisions()
            except Exception as e:
                log.debug("Sovereign poller error (non-fatal): %s", e)
            self._stop.wait(timeout=2.0)

    def _process_sovereign_decisions(self) -> None:
        path = self._decisions_path
        if not path.exists():
            return

        with self._decisions_lock:
            try:
                size = path.stat().st_size
            except OSError:
                return

            if size <= self._decisions_seen:
                return

            try:
                with path.open("r", encoding="utf-8") as f:
                    f.seek(self._decisions_seen)
                    new_data = f.read()
                    self._decisions_seen = size
            except OSError as e:
                log.debug("Sovereign decisions read error: %s", e)
                return

        for line in new_data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                decision = json.loads(line)
            except json.JSONDecodeError:
                continue

            action = decision.get("action")
            task_id = decision.get("task_id")
            if not task_id:
                continue

            if action == "approve":
                approver = decision.get("approver", "sovereign")
                if self.approve(task_id, approver):
                    log.info("SOVEREIGN APPROVE applied: %s (by %s)", task_id[:8], approver)
            elif action == "reject":
                approver = decision.get("approver", "sovereign")
                reason = decision.get("reason", "")
                if self.reject(task_id, approver, reason):
                    log.info("SOVEREIGN REJECT applied: %s (by %s)", task_id[:8], approver)

    # ---------- internals ----------

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            rec = self._step()
            if rec is None:
                self._tick.wait(timeout=0.25)
                self._tick.clear()

    def _step(self) -> TaskRecord | None:
        rec = self.scheduler.pop_next()
        if rec is None:
            return None
        self._run_record(rec)
        return rec

    def _run_record(self, rec: TaskRecord) -> None:
        # Phase 14: PolicyEngine gate — evaluated before constitutional gate
        verdict = self._policy_engine.evaluate(rec.spec)
        if not verdict.allowed:
            raise PolicyViolationError(verdict.reason)

        # Constitutional gate
        decision = self.policy.classify(rec.spec)
        if decision.domain is ApprovalDomain.APPROVAL_REQUIRED:
            self.state.mark_escalated(rec, decision.reason, decision.matched_rule)
            self.audit.record(
                agent_id=self.AGENT_ID,
                kind="approval",
                summary=f"AWAITING SOVEREIGN APPROVAL: {rec.spec.intent or rec.spec.kind}",
                detail={
                    "task_id": rec.spec.task_id,
                    "reason": decision.reason,
                    "rule": decision.matched_rule,
                    "spec": rec.spec.to_dict(),
                },
                correlation_id=rec.spec.task_id,
            )
            return

        # Phase 3: ORACLE intercept
        if self._oracle_intercept(rec):
            return

        # Direct handler dispatch (ORACLE offline or bypassed)
        handler = self._handlers.get(rec.spec.kind)
        if handler is None:
            self.recovery.handle_failure(rec, f"no handler registered for kind {rec.spec.kind!r}")
            return

        self.state.mark_running(rec)

        try:
            result = handler(rec.spec)
        except Exception as e:
            log.exception("handler %s raised", rec.spec.kind)
            self.recovery.handle_failure(rec, f"handler raised: {e}")
            return

        rec.last_result = result
        if result.get("escalate"):
            self.state.mark_escalated(
                rec, result.get("reason", "handler escalated"), result.get("rule")
            )
            self.audit.record(
                agent_id=self.AGENT_ID,
                kind="approval",
                summary=f"AWAITING SOVEREIGN APPROVAL: {rec.spec.intent or rec.spec.kind}",
                detail={
                    "task_id": rec.spec.task_id,
                    "reason": result.get("reason"),
                    "rule": result.get("rule"),
                    "spec": rec.spec.to_dict(),
                },
                correlation_id=rec.spec.task_id,
            )
            return
        if result.get("ok") is True:
            self.state.mark_succeeded(rec, result)
            self._tick.set()
        else:
            err = result.get("error") or result.get("reason") or "handler reported failure"
            self.recovery.handle_failure(rec, err)

    # ---------- Phase 11: self-heal ----------

    def rollback(self, task_id: str) -> None:
        """Acknowledge a rollback for *task_id*.

        Called by :class:`~pradyos.imperium.self_heal.SelfHealEngine` as
        part of the autonomous heal cycle.  The task must exist in the
        scheduler registry; raises :exc:`TaskNotFound` otherwise.
        """
        from pradyos.imperium.exceptions import TaskNotFound

        rec = self.scheduler.get(task_id)
        if rec is None:
            raise TaskNotFound(f"task {task_id!r} not found in IMPERIUM registry")
        self.audit.record(
            agent_id=self.AGENT_ID,
            kind="recovery",
            summary=f"rollback acknowledged: {task_id[:8]}",
            detail={"task_id": task_id, "state": rec.state.value},
            correlation_id=task_id,
        )

    def _self_heal_hook(self, rec: TaskRecord, error: str) -> None:
        """Callback wired into RecoveryCore.on_exhausted (Phase 11).

        Fires after a task is dead-lettered (retries exhausted).  Delegates
        to :class:`~pradyos.imperium.self_heal.SelfHealEngine` if wired.
        WARDEN is notified automatically via the ``system.self_heal`` bus
        event published by SelfHealEngine (WARDEN listens on ``system.*``).
        """
        if self._self_heal_engine is not None:
            try:
                self._self_heal_engine.heal(rec.spec.task_id, reason="retry_budget_exhausted")
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "SelfHealEngine.heal raised for %s: %s",
                    rec.spec.task_id[:8],
                    exc,
                )

    # ---------- default handlers ----------
    def _register_default_handlers(self) -> None:
        def _titan_dispatch(kind: str):
            from pradyos.titan_ops.daemon import TitanClient

            def handler(task: ImperiumTask) -> dict[str, Any]:
                payload = {
                    "agent_id": "imperium",
                    "kind": kind.split(".", 1)[1],
                    "lane": task.payload.get("lane", ExecutionLane.UNPRIVILEGED.value),
                    "command": task.payload.get("command"),
                    "args": task.payload.get("args", {}),
                    "intent": task.intent,
                    "rollback_hook": task.payload.get("rollback_hook"),
                    "correlation_id": task.task_id,
                    "timeout_sec": task.payload.get("timeout_sec", 60),
                }
                client = TitanClient(
                    socket_path=os.environ.get(
                        "PRADYOS_TITAN_SOCKET",
                        str(self.checkpoint.state_dir / "titan.sock"),
                    ),
                )
                try:
                    resp = client.send(payload, timeout=task.payload.get("timeout_sec", 90) + 5)
                except OSError as e:
                    return {"ok": False, "error": f"titan unreachable: {e}"}
                if not resp.get("ok"):
                    return {"ok": False, "error": resp.get("error", "titan error")}
                result = resp.get("result", {})
                if result.get("escalated"):
                    return {
                        "escalate": True,
                        "reason": result.get("escalation_reason"),
                        "rule": "titan_constitutional",
                    }
                return {
                    "ok": result.get("succeeded", False),
                    "exit_code": result.get("exit_code"),
                    "stdout_tail": (result.get("stdout") or "")[-1000:],
                    "stderr_tail": (result.get("stderr") or "")[-1000:],
                    "duration_sec": result.get("duration_sec"),
                }

            return handler

        for k in ("titan.shell", "titan.package", "titan.file", "titan.service", "titan.process"):
            self.register_handler(k, _titan_dispatch(k))

        def _research(task: ImperiumTask) -> dict[str, Any]:
            # Fallback when ORACLE is offline
            log.debug("research fallback (ORACLE offline): %s", task.task_id[:8])
            return {
                "ok": True,
                "note": "research fallback — ORACLE offline, direct dispatch",
                "intent": task.intent,
            }

        self.register_handler("research", _research)

        def _proposal(task: ImperiumTask) -> dict[str, Any]:
            return {
                "escalate": True,
                "reason": "project proposals require Sovereign approval",
                "rule": "new_project_proposal",
            }

        self.register_handler("project_proposal", _proposal)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
    kern = Imperium()
    kern.start()
    log.info(
        "IMPERIUM running (ORACLE: %s). Ctrl+C to stop.", "wired" if kern._oracle else "offline"
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log.info("IMPERIUM shutting down")
        kern.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
