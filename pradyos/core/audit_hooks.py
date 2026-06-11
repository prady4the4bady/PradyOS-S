"""Cross-cutting audit hooks — Phase 7A.

Wires AuditEvent emission into every significant action across the four
major subsystems without monkey-patching stdlib or using fragile
setattr tricks on unrelated objects.

Strategy: composition via method wrapping on each subsystem's own
instances. We keep a reference to the original method and replace the
instance attribute with a closure that (a) calls the original, then
(b) emits an AuditEvent into the provided EventAuditLog.

Windows-safe: no signals, no AF_UNIX, no fork.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from pradyos.core.audit import AuditCategory, AuditEvent, EventAuditLog

log = logging.getLogger("pradyos.core.audit_hooks")

__all__ = ["wire_audit"]


# ---------------------------------------------------------------------------
# Internal wrapping helpers
# ---------------------------------------------------------------------------


def _wrap(obj: Any, method_name: str, before: Callable | None, after: Callable) -> None:
    """Replace obj.<method_name> with a closure that calls *after* post-call.

    *before* is called with (args, kwargs) before the call (optional).
    *after* is called with (result, args, kwargs) after a successful call.

    Exceptions from the original method propagate unchanged; after() is still
    called if the original raises (result will be None, exc will be set).
    """
    original = getattr(obj, method_name)

    @functools.wraps(original)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if before is not None:
            try:
                before(args, kwargs)
            except Exception as e:  # noqa: BLE001
                log.debug("audit hook before() failed: %s", e)
        exc: Exception | None = None
        result: Any = None
        try:
            result = original(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            exc = e
        try:
            after(result, args, kwargs, exc)
        except Exception as e:  # noqa: BLE001
            log.debug("audit hook after() failed: %s", e)
        if exc is not None:
            raise exc
        return result

    # Bind as instance attribute (shadows the class method for this instance)
    setattr(obj, method_name, _wrapper)


def _emit(
    audit_log: EventAuditLog,
    category: AuditCategory,
    actor: str,
    action: str,
    payload: dict[str, Any],
) -> None:
    """Create and append an AuditEvent to *audit_log*.

    Payload values are coerced to JSON-safe primitives so that
    ``AuditEvent.to_json()`` never raises TypeError, even when hooks
    receive mock objects or un-serializable domain types.
    """
    safe_payload: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str | int | float | bool | type(None)):
            safe_payload[k] = v
        else:
            safe_payload[k] = str(v)

    event = AuditEvent(
        timestamp=time.time(),
        category=category,
        actor=actor,
        action=action,
        payload=safe_payload,
    )
    audit_log.append(event)


# ---------------------------------------------------------------------------
# Public wiring function
# ---------------------------------------------------------------------------


def wire_audit(
    imperium_kernel: Any | None = None,
    campaign_engine: Any | None = None,
    titan_executor: Any | None = None,
    oracle_planner: Any | None = None,
    audit_log: EventAuditLog | None = None,
) -> EventAuditLog:
    """Attach audit hooks to each subsystem.

    Parameters
    ----------
    imperium_kernel:
        ``pradyos.imperium.kernel.Imperium`` instance. Hooks: submit, approve,
        reject, _run_record (task state transitions).
    campaign_engine:
        ``pradyos.campaign.engine.CampaignEngine`` instance. Hooks:
        create_campaign, run_campaign (started / terminal).
    titan_executor:
        ``pradyos.titan_ops.executor.TitanExecutor`` instance. Hooks: execute.
    oracle_planner:
        ``pradyos.oracle.planner.OraclePlanner`` instance. Hooks: plan.
    audit_log:
        EventAuditLog to emit into. Creates a new one if not supplied.

    Returns the EventAuditLog used (useful when caller passes None).
    """
    if audit_log is None:
        audit_log = EventAuditLog()

    _wire_imperium(imperium_kernel, audit_log)
    _wire_campaign(campaign_engine, audit_log)
    _wire_titan(titan_executor, audit_log)
    _wire_oracle(oracle_planner, audit_log)

    log.info("Audit hooks wired to all subsystems")
    return audit_log


# ---------------------------------------------------------------------------
# Per-subsystem wiring
# ---------------------------------------------------------------------------


def _wire_imperium(kernel: Any | None, audit_log: EventAuditLog) -> None:
    if kernel is None:
        return

    # Hook: submit — task queued
    def _after_submit(result: Any, args: tuple, kwargs: dict, exc: Any) -> None:
        task = args[0] if args else kwargs.get("task")
        task_id = getattr(getattr(task, "task_id", None), "__str__", lambda: "?")()
        intent = getattr(task, "intent", None) or getattr(task, "kind", "?")
        _emit(
            audit_log,
            AuditCategory.SOVEREIGN,
            actor="imperium",
            action="task_queued",
            payload={
                "task_id": task_id,
                "intent": intent,
                "ok": exc is None,
                "error": str(exc) if exc else None,
            },
        )

    _wrap(kernel, "submit", None, _after_submit)

    # Hook: approve
    def _after_approve(result: Any, args: tuple, kwargs: dict, exc: Any) -> None:
        task_id = args[0] if args else kwargs.get("task_id", "?")
        approver = args[1] if len(args) > 1 else kwargs.get("approver", "sovereign")
        _emit(
            audit_log,
            AuditCategory.SOVEREIGN,
            actor=str(approver),
            action="task_approved",
            payload={
                "task_id": task_id,
                "approved": bool(result),
                "error": str(exc) if exc else None,
            },
        )

    _wrap(kernel, "approve", None, _after_approve)

    # Hook: reject
    def _after_reject(result: Any, args: tuple, kwargs: dict, exc: Any) -> None:
        task_id = args[0] if args else kwargs.get("task_id", "?")
        approver = args[1] if len(args) > 1 else kwargs.get("approver", "sovereign")
        reason = args[2] if len(args) > 2 else kwargs.get("reason", "")
        _emit(
            audit_log,
            AuditCategory.SOVEREIGN,
            actor=str(approver),
            action="task_rejected",
            payload={"task_id": task_id, "reason": reason, "error": str(exc) if exc else None},
        )

    _wrap(kernel, "reject", None, _after_reject)

    # Hook: _run_record — task state transitions (RUNNING / SUCCEEDED / FAILED)
    original_run = getattr(kernel, "_run_record", None)
    if original_run is not None:

        @functools.wraps(original_run)
        def _run_record_hooked(rec: Any) -> None:  # type: ignore[return]
            _emit(
                audit_log,
                AuditCategory.SOVEREIGN,
                actor="imperium",
                action="task_running",
                payload={
                    "task_id": getattr(getattr(rec, "spec", None), "task_id", "?"),
                    "kind": getattr(getattr(rec, "spec", None), "kind", "?"),
                },
            )
            try:
                original_run(rec)
            finally:
                state = str(getattr(rec, "state", "?"))
                _emit(
                    audit_log,
                    AuditCategory.SOVEREIGN,
                    actor="imperium",
                    action=f"task_{state.lower()}",
                    payload={
                        "task_id": getattr(getattr(rec, "spec", None), "task_id", "?"),
                        "state": state,
                        "error": getattr(rec, "last_error", None),
                    },
                )

        kernel._run_record = _run_record_hooked


def _wire_campaign(engine: Any | None, audit_log: EventAuditLog) -> None:
    if engine is None:
        return

    # Hook: create_campaign
    def _after_create(result: Any, args: tuple, kwargs: dict, exc: Any) -> None:
        name = args[0] if args else kwargs.get("name", "?")
        intent = args[1] if len(args) > 1 else kwargs.get("intent", "?")
        campaign_id = getattr(result, "campaign_id", "?") if result is not None else "?"
        _emit(
            audit_log,
            AuditCategory.CAMPAIGN,
            actor="campaign_engine",
            action="campaign_created",
            payload={
                "campaign_id": campaign_id,
                "name": name,
                "intent": intent,
                "ok": exc is None,
                "error": str(exc) if exc else None,
            },
        )

    _wrap(engine, "create_campaign", None, _after_create)

    # Hook: run_campaign (async — we wrap the coroutine factory)
    original_run = getattr(engine, "run_campaign", None)
    if original_run is not None:

        @functools.wraps(original_run)
        async def _run_campaign_hooked(campaign: Any) -> Any:
            campaign_id = getattr(campaign, "campaign_id", "?")
            name = getattr(campaign, "name", "?")
            _emit(
                audit_log,
                AuditCategory.CAMPAIGN,
                actor="campaign_engine",
                action="campaign_started",
                payload={"campaign_id": campaign_id, "name": name},
            )
            exc: Exception | None = None
            result: Any = None
            try:
                result = await original_run(campaign)
            except Exception as e:  # noqa: BLE001
                exc = e
            status = str(getattr(result, "status", getattr(campaign, "status", "?")))
            action = (
                "campaign_succeeded"
                if "succeed" in status.lower()
                else "campaign_failed"
                if "fail" in status.lower()
                else "campaign_terminal"
            )
            _emit(
                audit_log,
                AuditCategory.CAMPAIGN,
                actor="campaign_engine",
                action=action,
                payload={
                    "campaign_id": campaign_id,
                    "name": name,
                    "status": status,
                    "error": str(exc) if exc else getattr(result, "error", None),
                },
            )
            if exc is not None:
                raise exc
            return result

        engine.run_campaign = _run_campaign_hooked

    # Hook: _execute_node (node succeeded / failed)
    original_node = getattr(engine, "_execute_node", None)
    if original_node is not None:

        @functools.wraps(original_node)
        async def _execute_node_hooked(campaign: Any, node: Any, execution_order: list) -> None:
            exc: Exception | None = None
            try:
                await original_node(campaign, node, execution_order)
            except Exception as e:  # noqa: BLE001
                exc = e
            node_status = str(getattr(node, "status", "?"))
            action = (
                "node_succeeded"
                if "succeed" in node_status.lower()
                else "node_failed"
                if "fail" in node_status.lower()
                else f"node_{node_status.lower()}"
            )
            _emit(
                audit_log,
                AuditCategory.CAMPAIGN,
                actor="campaign_engine",
                action=action,
                payload={
                    "campaign_id": getattr(campaign, "campaign_id", "?"),
                    "node_id": getattr(node, "node_id", "?"),
                    "intent": getattr(getattr(node, "task", None), "intent", "?"),
                    "node_status": node_status,
                    "error": str(exc) if exc else getattr(node, "error", None),
                },
            )
            if exc is not None:
                raise exc

        engine._execute_node = _execute_node_hooked


def _wire_titan(executor: Any | None, audit_log: EventAuditLog) -> None:
    if executor is None:
        return

    def _after_execute(result: Any, args: tuple, kwargs: dict, exc: Any) -> None:
        instr = args[0] if args else kwargs.get("instr")
        instr_id = getattr(instr, "instruction_id", "?") if instr else "?"
        intent = getattr(instr, "intent", None) or getattr(instr, "command", "?")
        succeeded = getattr(result, "succeeded", False) if result is not None else False
        action = "instruction_completed" if succeeded else "instruction_failed"
        _emit(
            audit_log,
            AuditCategory.WARDEN,
            actor="titan_ops",
            action=action,
            payload={
                "instruction_id": instr_id,
                "intent": intent,
                "succeeded": succeeded,
                "exit_code": getattr(result, "exit_code", None) if result else None,
                "timed_out": getattr(result, "timed_out", False) if result else False,
                "escalated": getattr(result, "escalated", False) if result else False,
                "error": str(exc) if exc else getattr(result, "error", None) if result else None,
            },
        )

    # Also emit "dispatched" before execution
    def _before_execute(args: tuple, kwargs: dict) -> None:
        instr = args[0] if args else kwargs.get("instr")
        instr_id = getattr(instr, "instruction_id", "?") if instr else "?"
        intent = getattr(instr, "intent", None) or getattr(instr, "command", "?")
        _emit(
            audit_log,
            AuditCategory.WARDEN,
            actor="titan_ops",
            action="instruction_dispatched",
            payload={"instruction_id": instr_id, "intent": intent},
        )

    _wrap(executor, "execute", _before_execute, _after_execute)


def _wire_oracle(planner: Any | None, audit_log: EventAuditLog) -> None:
    if planner is None:
        return

    # plan() is async
    original_plan = getattr(planner, "plan", None)
    if original_plan is None:
        return

    @functools.wraps(original_plan)
    async def _plan_hooked(task: Any) -> Any:
        exc: Exception | None = None
        result: Any = None
        try:
            result = await original_plan(task)
        except Exception as e:  # noqa: BLE001
            exc = e

        ok = result is not None and getattr(result, "ok", True) and exc is None
        action = "plan_produced" if ok else "plan_errored"
        _emit(
            audit_log,
            AuditCategory.ORACLE,
            actor="oracle_planner",
            action=action,
            payload={
                "task_id": getattr(task, "task_id", "?"),
                "intent": getattr(task, "intent", "?"),
                "requires_approval": getattr(result, "requires_approval", False)
                if result
                else False,
                "step_count": len(getattr(result, "steps", [])) if result else 0,
                "error": str(exc) if exc else getattr(result, "error", None) if result else None,
                "ok": ok,
            },
        )
        if exc is not None:
            raise exc
        return result

    planner.plan = _plan_hooked
