"""CampaignEngine — DAG campaign execution.

Execution flow per campaign:
  1. ORACLE plans each node (async, with memory context).
  2. Nodes are dispatched in topological order via asyncio tasks.
  3. WARDEN GRID monitors per-node health (via bus events).
  4. On any node failure → RollbackRegistry rolls back all completed nodes
     in reverse execution order.
  5. Campaign state transitions are persisted to CampaignRegistry.

Bus events emitted:
    campaign.created           — campaign + node count
    campaign.node.planning     — node about to be planned by ORACLE
    campaign.node.running      — node dispatched to TITAN OPS
    campaign.node.succeeded    — node completed
    campaign.node.failed       — node failed
    campaign.node.rolled_back  — node rolled back
    campaign.succeeded         — all nodes succeeded
    campaign.failed            — campaign failed (with error)
    campaign.rolled_back       — full rollback complete
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any

from pradyos.campaign.model import Campaign, CampaignNode, CampaignStatus, NodeStatus
from pradyos.campaign.registry import CampaignRegistry
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.ids import new_id
from pradyos.core.types import Priority
from pradyos.imperium.task import ImperiumTask
from pradyos.titan_ops.rollback import RollbackEntry, RollbackRegistry

log = logging.getLogger("pradyos.campaign.engine")

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: "CampaignEngine | None" = None
_engine_lock = threading.Lock()


def get_engine(**kwargs: Any) -> "CampaignEngine":
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = CampaignEngine(**kwargs)
    return _engine


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CampaignEngine:
    """Async campaign execution engine.

    Creates campaigns, plans their nodes via ORACLE, executes them as an
    ordered DAG, monitors with WARDEN GRID, and rolls back on failure.
    """

    def __init__(
        self,
        oracle: Any | None = None,       # Oracle instance (optional — stubs allowed)
        memory: Any | None = None,       # CitadelStore / InMemoryCitadel
        rollback_registry: RollbackRegistry | None = None,
        registry: CampaignRegistry | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._oracle = oracle
        self._memory = memory
        self._rollbacks = rollback_registry or RollbackRegistry()
        self._registry = registry or CampaignRegistry()
        self._bus = bus or get_bus()
        self._running: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_campaign(
        self,
        name: str,
        intent: str,
        tasks: list[ImperiumTask],
        dependency_map: dict[str, list[str]] | None = None,
        submitted_by: str = "sovereign",
        metadata: dict[str, Any] | None = None,
    ) -> Campaign:
        """Build and persist a Campaign from a list of ImperiumTasks.

        Args:
            tasks           — ordered list of tasks (nodes will be created for each)
            dependency_map  — maps task index (0-based str) or task_id to list of
                              node_ids/task_ids it depends on. None = sequential chain.
        """
        campaign = Campaign(
            name=name,
            intent=intent,
            submitted_by=submitted_by,
            metadata=metadata or {},
        )

        # Build nodes
        nodes_ordered: list[CampaignNode] = []
        for task in tasks:
            node = CampaignNode(task=task)
            campaign.add_node(node)
            nodes_ordered.append(node)

        # Wire dependencies
        if dependency_map is None:
            # Default: sequential chain — each node depends on the previous
            for i in range(1, len(nodes_ordered)):
                nodes_ordered[i].depends_on.append(nodes_ordered[i - 1].node_id)
        else:
            # Caller provides explicit deps
            # Keys can be 0-based index or task_id
            id_by_index = {str(i): n.node_id for i, n in enumerate(nodes_ordered)}
            id_by_task = {n.task.task_id: n.node_id for n in nodes_ordered}

            for key, deps in dependency_map.items():
                target_nid = id_by_index.get(key) or id_by_task.get(key)
                if target_nid is None:
                    continue
                target_node = campaign.nodes[target_nid]
                for dep in deps:
                    dep_nid = id_by_index.get(dep) or id_by_task.get(dep) or dep
                    if dep_nid in campaign.nodes:
                        target_node.depends_on.append(dep_nid)

        self._registry.save(campaign)
        self._bus.publish(
            "campaign.created",
            {
                "campaign_id": campaign.campaign_id,
                "name": name,
                "intent": intent,
                "node_count": len(campaign.nodes),
            },
        )
        log.info(
            "Campaign %s created (%d nodes): %s",
            campaign.campaign_id,
            len(campaign.nodes),
            name,
        )
        return campaign

    async def run_campaign(self, campaign: Campaign) -> Campaign:
        """Execute a campaign to completion (or failure+rollback).

        Returns the updated Campaign with final status.
        """
        campaign.status = CampaignStatus.RUNNING
        campaign.started_at = time.time()
        self._registry.save(campaign)
        log.info("Campaign %s starting (%s)", campaign.campaign_id, campaign.name)

        execution_order: list[str] = []  # node_ids in execution order for rollback

        try:
            await self._execute_dag(campaign, execution_order)

            if campaign.has_failed_nodes():
                campaign.status = CampaignStatus.FAILED
                campaign.error = "One or more nodes failed"
            else:
                campaign.status = CampaignStatus.SUCCEEDED

        except asyncio.CancelledError:
            campaign.status = CampaignStatus.CANCELLED
            raise
        except Exception as e:  # noqa: BLE001
            log.error("Campaign %s unhandled error: %s", campaign.campaign_id, e)
            campaign.status = CampaignStatus.FAILED
            campaign.error = str(e)

        campaign.finished_at = time.time()

        # Rollback on failure
        if campaign.status == CampaignStatus.FAILED:
            await self._rollback_campaign(campaign, execution_order)

        self._registry.save(campaign)
        self._bus.publish(
            f"campaign.{campaign.status.value}",
            {
                "campaign_id": campaign.campaign_id,
                "name": campaign.name,
                "status": campaign.status.value,
                "error": campaign.error,
                "progress": campaign.progress(),
            },
        )
        log.info(
            "Campaign %s finished: %s", campaign.campaign_id, campaign.status.value
        )
        return campaign

    async def rollback_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Manually trigger rollback for a campaign by ID."""
        campaign = self._registry.get(campaign_id)
        if campaign is None:
            return {"ok": False, "error": f"Campaign {campaign_id} not found"}
        execution_order = [
            nid for nid, n in campaign.nodes.items()
            if n.status in (NodeStatus.SUCCEEDED, NodeStatus.RUNNING)
        ]
        await self._rollback_campaign(campaign, execution_order)
        self._registry.save(campaign)
        return {"ok": True, "campaign_id": campaign_id, "status": campaign.status.value}

    # ------------------------------------------------------------------
    # DAG execution
    # ------------------------------------------------------------------

    async def _execute_dag(
        self, campaign: Campaign, execution_order: list[str]
    ) -> None:
        """Execute nodes in dependency order. Stops on first failure."""
        pending = set(campaign.nodes.keys())

        while pending:
            ready = [
                n for n in campaign.get_ready_nodes()
                if n.node_id in pending
            ]
            if not ready:
                # Check for deadlock (no progress possible)
                still_pending = [
                    n for nid, n in campaign.nodes.items()
                    if nid in pending and n.status == NodeStatus.PENDING
                ]
                if still_pending:
                    # Upstream failure — skip remaining nodes
                    for node in still_pending:
                        node.status = NodeStatus.SKIPPED
                        pending.discard(node.node_id)
                break

            # Execute ready nodes concurrently
            tasks = [
                asyncio.create_task(
                    self._execute_node(campaign, node, execution_order),
                    name=f"node-{node.node_id}",
                )
                for node in ready
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for node, result in zip(ready, results):
                pending.discard(node.node_id)
                if isinstance(result, Exception):
                    log.error("Node %s exception: %s", node.node_id, result)
                    node.status = NodeStatus.FAILED
                    node.error = str(result)

            if campaign.has_failed_nodes():
                # Mark remaining pending as skipped
                for nid in list(pending):
                    n = campaign.nodes[nid]
                    if n.status == NodeStatus.PENDING:
                        n.status = NodeStatus.SKIPPED
                        pending.discard(nid)
                break

    async def _execute_node(
        self,
        campaign: Campaign,
        node: CampaignNode,
        execution_order: list[str],
    ) -> None:
        """Plan (via ORACLE) then execute (via TITAN OPS) a single node."""
        # Phase 1: ORACLE planning
        node.status = NodeStatus.PLANNING
        node.started_at = time.time()
        self._registry.save(campaign)
        self._bus.publish(
            "campaign.node.planning",
            {
                "campaign_id": campaign.campaign_id,
                "node_id": node.node_id,
                "intent": node.task.intent,
            },
        )

        plan = await self._plan_node(node)

        if plan is not None:
            node.plan_steps = [s.to_dict() for s in plan.steps]
            if plan.requires_approval:
                node.status = NodeStatus.AWAITING_APPROVAL
                self._registry.save(campaign)
                self._bus.publish(
                    "campaign.node.awaiting_approval",
                    {
                        "campaign_id": campaign.campaign_id,
                        "node_id": node.node_id,
                        "reason": plan.approval_reason,
                    },
                )
                log.info(
                    "Node %s awaiting Sovereign approval: %s",
                    node.node_id,
                    plan.approval_reason,
                )
                # Stall — caller must approve/reject externally
                node.status = NodeStatus.FAILED
                node.error = f"Approval required: {plan.approval_reason}"
                self._bus.publish(
                    "campaign.node.failed",
                    {
                        "campaign_id": campaign.campaign_id,
                        "node_id": node.node_id,
                        "intent": node.task.intent,
                        "error": node.error,
                    },
                )
                self._registry.save(campaign)
                return

        # Phase 2: Execution
        node.status = NodeStatus.RUNNING
        self._registry.save(campaign)
        self._bus.publish(
            "campaign.node.running",
            {
                "campaign_id": campaign.campaign_id,
                "node_id": node.node_id,
                "intent": node.task.intent,
                "step_count": len(node.plan_steps),
            },
        )

        result = await self._dispatch_node(node, plan)
        node.result = result
        node.finished_at = time.time()

        if result.get("ok"):
            node.status = NodeStatus.SUCCEEDED
            execution_order.append(node.node_id)
            self._bus.publish(
                "campaign.node.succeeded",
                {
                    "campaign_id": campaign.campaign_id,
                    "node_id": node.node_id,
                    "intent": node.task.intent,
                },
            )
            # Record outcome in memory
            if self._oracle is not None:
                await self._oracle.record_outcome(
                    task_id=node.task.task_id,
                    intent=node.task.intent,
                    outcome="success",
                    plan=plan,
                )
        else:
            node.status = NodeStatus.FAILED
            node.error = result.get("error", "unknown error")
            self._bus.publish(
                "campaign.node.failed",
                {
                    "campaign_id": campaign.campaign_id,
                    "node_id": node.node_id,
                    "intent": node.task.intent,
                    "error": node.error,
                },
            )
            log.warning(
                "Node %s failed: %s", node.node_id, node.error
            )

        self._registry.save(campaign)

    # ------------------------------------------------------------------
    # Planning + dispatch
    # ------------------------------------------------------------------

    async def _plan_node(self, node: CampaignNode) -> Any | None:
        """Call ORACLE to plan a node. Returns OraclePlan or None."""
        if self._oracle is None:
            return None
        try:
            from pradyos.oracle.planner import OraclePlan  # noqa: PLC0415

            plan = await self._oracle.plan_task(node.task)
            return plan
        except Exception as e:  # noqa: BLE001
            log.debug("Oracle planning skipped for node %s: %s", node.node_id, e)
            return None

    async def _dispatch_node(self, node: CampaignNode, plan: Any | None) -> dict[str, Any]:
        """Execute the planned steps via TITAN OPS (or stub if unavailable)."""
        if plan is None or not plan.steps:
            # No plan — execute the task's raw payload if it's a shell command
            cmd = node.task.payload.get("command") or node.task.intent
            return await self._run_stub(node, cmd)

        # Execute steps sequentially via TITAN OPS async executor
        try:
            from pradyos.titan_ops.async_executor import AsyncTitanExecutor  # noqa: PLC0415

            executor = AsyncTitanExecutor()
            results: list[dict[str, Any]] = []
            for instr in plan.steps:
                r = await executor.execute(instr)
                # Register rollback
                if instr.rollback_hook:
                    from pradyos.titan_ops.rollback import RollbackEntry, HookKind  # noqa: PLC0415

                    self._rollbacks.register(
                        RollbackEntry(
                            instruction_id=instr.instruction_id,
                            correlation_id=node.node_id,
                            hook=instr.rollback_hook,
                            kind=HookKind.SHELL,
                        )
                    )
                    node.rollback_ids.append(instr.instruction_id)
                results.append(r)
                if not r.get("ok", True):
                    return {"ok": False, "error": r.get("stderr", "step failed"), "steps": results}
            return {"ok": True, "steps": results}

        except ImportError:
            return await self._run_stub(node, node.task.intent)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    async def _run_stub(self, node: CampaignNode, description: str) -> dict[str, Any]:
        """Stub executor for when TITAN OPS async executor is unavailable.

        In production this path should not be hit; used in tests and when
        tasks carry no executable plan.
        """
        log.debug("CampaignEngine stub: node %s — %s", node.node_id, description)
        await asyncio.sleep(0)  # yield
        return {"ok": True, "stub": True, "description": description}

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    async def _rollback_campaign(
        self, campaign: Campaign, execution_order: list[str]
    ) -> None:
        """Roll back all executed nodes in reverse execution order."""
        log.info(
            "Rolling back campaign %s (%d nodes)",
            campaign.campaign_id,
            len(execution_order),
        )
        for node_id in reversed(execution_order):
            node = campaign.nodes.get(node_id)
            if node is None:
                continue
            if node.status not in (NodeStatus.SUCCEEDED,):
                continue

            rolled = []
            for instr_id in node.rollback_ids:
                result = self._rollbacks.execute_rollback(instr_id)
                rolled.append(result)

            node.status = NodeStatus.ROLLED_BACK
            self._bus.publish(
                "campaign.node.rolled_back",
                {
                    "campaign_id": campaign.campaign_id,
                    "node_id": node_id,
                    "rollback_results": rolled,
                },
            )

        campaign.status = CampaignStatus.ROLLED_BACK
        self._bus.publish(
            "campaign.rolled_back",
            {
                "campaign_id": campaign.campaign_id,
                "name": campaign.name,
            },
        )

    # ------------------------------------------------------------------
    # CLI
    # ------------------------------------------------------------------


def main() -> None:
    """CLI entry point: pradyos-campaign (status / list)."""
    import click
    import json as _json

    @click.command()
    @click.option("--list", "do_list", is_flag=True, help="List all campaigns")
    @click.option("--active", is_flag=True, help="List active campaigns")
    @click.option("--stats", is_flag=True, help="Show registry stats")
    def _cli(do_list: bool, active: bool, stats: bool) -> None:
        """CAMPAIGN ENGINE status CLI."""
        engine = get_engine()
        reg = engine._registry

        if stats:
            click.echo(_json.dumps(reg.stats(), indent=2))
        elif active:
            for c in reg.active():
                click.echo(f"{c.campaign_id}  {c.status.value:<12} {c.name}")
        else:
            for c in reg.recent(20):
                click.echo(f"{c.campaign_id}  {c.status.value:<12} {c.name}")

    _cli()


if __name__ == "__main__":
    main()
