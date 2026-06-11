"""Campaign and CampaignNode data models.

A Campaign is a named, DAG-structured operation. Each node wraps an
ImperiumTask plus execution metadata. The DAG is represented as an
adjacency list: node_id → list[dependency node_ids].
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pradyos.core.ids import new_id
from pradyos.imperium.task import ImperiumTask


class CampaignStatus(str, Enum):
    PENDING = "pending"  # created, not started
    PLANNING = "planning"  # ORACLE is generating the plan
    RUNNING = "running"  # nodes are executing
    SUCCEEDED = "succeeded"  # all nodes completed successfully
    FAILED = "failed"  # one or more nodes failed (rollbacks triggered)
    ROLLED_BACK = "rolled_back"  # rollback completed
    PAUSED = "paused"  # waiting for Sovereign approval
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {
            CampaignStatus.SUCCEEDED,
            CampaignStatus.FAILED,
            CampaignStatus.ROLLED_BACK,
            CampaignStatus.CANCELLED,
        }


class NodeStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    READY = "ready"  # plan produced, waiting for deps
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"  # skipped because upstream failed
    AWAITING_APPROVAL = "awaiting_approval"

    @property
    def terminal(self) -> bool:
        return self in {
            NodeStatus.SUCCEEDED,
            NodeStatus.FAILED,
            NodeStatus.ROLLED_BACK,
            NodeStatus.SKIPPED,
        }


@dataclass
class CampaignNode:
    """One node in the campaign DAG.

    Wraps an ImperiumTask plus node-level metadata:
        node_id       — unique within this campaign
        task          — the underlying ImperiumTask
        depends_on    — list of node_ids that must succeed first
        status        — current NodeStatus
        plan_steps    — TitanInstruction dicts produced by ORACLE
        result        — execution result from TITAN OPS
        error         — error message if failed
        rollback_ids  — instruction_ids registered in RollbackRegistry
    """

    task: ImperiumTask
    depends_on: list[str] = field(default_factory=list)
    node_id: str = field(default_factory=lambda: new_id("cn"))
    status: NodeStatus = NodeStatus.PENDING
    plan_steps: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    rollback_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "task_id": self.task.task_id,
            "task_kind": self.task.kind,
            "task_intent": self.task.intent,
            "depends_on": list(self.depends_on),
            "status": self.status.value,
            "plan_steps": self.plan_steps,
            "result": self.result,
            "error": self.error,
            "rollback_ids": list(self.rollback_ids),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CampaignNode:
        task = ImperiumTask(
            kind=d.get("task_kind", "shell"),
            intent=d.get("task_intent", ""),
            task_id=d.get("task_id", new_id("tk")),
        )
        try:
            status = NodeStatus(d.get("status", "pending"))
        except ValueError:
            status = NodeStatus.PENDING
        return cls(
            task=task,
            depends_on=d.get("depends_on", []),
            node_id=d.get("node_id", new_id("cn")),
            status=status,
            plan_steps=d.get("plan_steps", []),
            result=d.get("result"),
            error=d.get("error"),
            rollback_ids=d.get("rollback_ids", []),
            created_at=d.get("created_at", time.time()),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
        )


@dataclass
class Campaign:
    """A named multi-step operation expressed as a DAG of CampaignNodes.

    The DAG is stored as:
        nodes     — dict[node_id, CampaignNode]
        edges     — adjacency list: node_id → list[node_id] (downstream)
    """

    name: str
    intent: str
    campaign_id: str = field(default_factory=lambda: new_id("camp"))
    status: CampaignStatus = CampaignStatus.PENDING
    nodes: dict[str, CampaignNode] = field(default_factory=dict)
    submitted_by: str = "sovereign"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None

    # ------------------------------------------------------------------
    # DAG helpers
    # ------------------------------------------------------------------

    def add_node(self, node: CampaignNode) -> str:
        """Add a node and return its node_id."""
        self.nodes[node.node_id] = node
        return node.node_id

    def get_ready_nodes(self) -> list[CampaignNode]:
        """Return nodes whose dependencies are all SUCCEEDED and are themselves READY/PENDING."""
        ready: list[CampaignNode] = []
        succeeded = {nid for nid, n in self.nodes.items() if n.status == NodeStatus.SUCCEEDED}
        for node in self.nodes.values():
            if node.status not in (NodeStatus.PENDING, NodeStatus.READY):
                continue
            if all(dep in succeeded for dep in node.depends_on):
                ready.append(node)
        return ready

    def has_failed_nodes(self) -> bool:
        return any(n.status == NodeStatus.FAILED for n in self.nodes.values())

    def is_complete(self) -> bool:
        return all(n.status.terminal for n in self.nodes.values())

    def progress(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for n in self.nodes.values():
            counts[n.status.value] = counts.get(n.status.value, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "name": self.name,
            "intent": self.intent,
            "status": self.status.value,
            "submitted_by": self.submitted_by,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Campaign:
        try:
            status = CampaignStatus(d.get("status", "pending"))
        except ValueError:
            status = CampaignStatus.PENDING

        nodes = {nid: CampaignNode.from_dict(nd) for nid, nd in d.get("nodes", {}).items()}
        return cls(
            name=d.get("name", "unnamed"),
            intent=d.get("intent", ""),
            campaign_id=d.get("campaign_id", new_id("camp")),
            status=status,
            nodes=nodes,
            submitted_by=d.get("submitted_by", "sovereign"),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", time.time()),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            error=d.get("error"),
        )
