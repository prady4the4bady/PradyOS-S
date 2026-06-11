"""Tests for CAMPAIGN ENGINE — DAG orchestration (Phase 2).

No live ORACLE or TITAN required. Uses stub oracle and in-memory registry.
"""
from __future__ import annotations

import asyncio
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from pradyos.campaign.model import (
    Campaign, CampaignNode, CampaignStatus, NodeStatus,
)
from pradyos.campaign.registry import CampaignRegistry
from pradyos.campaign.engine import CampaignEngine
from pradyos.core.bus import EventBus
from pradyos.core.types import Priority
from pradyos.imperium.task import ImperiumTask
from pradyos.memory_citadel.inmem import InMemoryCitadel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(intent: str = "do something", kind: str = "shell") -> ImperiumTask:
    return ImperiumTask(kind=kind, intent=intent)


def _engine(bus: EventBus | None = None, tmp_path: Path | None = None) -> CampaignEngine:
    reg = CampaignRegistry(path=tmp_path / "campaigns.jsonl") if tmp_path else CampaignRegistry(
        path=Path(__file__).parent.parent / "var" / "test_campaigns.jsonl"
    )
    return CampaignEngine(
        oracle=None,  # no oracle — stub dispatch used
        memory=InMemoryCitadel(),
        registry=reg,
        bus=bus or EventBus(),
    )


# ---------------------------------------------------------------------------
# CampaignNode tests
# ---------------------------------------------------------------------------

class TestCampaignNode:
    def test_default_status_pending(self):
        node = CampaignNode(task=_task())
        assert node.status == NodeStatus.PENDING
        assert node.node_id.startswith("cn_")

    def test_to_dict_roundtrip(self):
        node = CampaignNode(task=_task("install nginx"), depends_on=["cn_abc"])
        d = node.to_dict()
        node2 = CampaignNode.from_dict(d)
        assert node2.status == NodeStatus.PENDING
        assert "cn_abc" in node2.depends_on

    def test_terminal_statuses(self):
        for s in (NodeStatus.SUCCEEDED, NodeStatus.FAILED, NodeStatus.ROLLED_BACK, NodeStatus.SKIPPED):
            assert s.terminal
        for s in (NodeStatus.PENDING, NodeStatus.RUNNING, NodeStatus.PLANNING):
            assert not s.terminal


# ---------------------------------------------------------------------------
# Campaign model tests
# ---------------------------------------------------------------------------

class TestCampaign:
    def test_add_node_and_get_ready(self):
        c = Campaign(name="test", intent="deploy stack")
        n1 = CampaignNode(task=_task("step 1"))
        n2 = CampaignNode(task=_task("step 2"))
        n2.depends_on.append(n1.node_id)
        c.add_node(n1)
        c.add_node(n2)

        ready = c.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].node_id == n1.node_id

    def test_get_ready_after_first_succeeds(self):
        c = Campaign(name="test", intent="deploy stack")
        n1 = CampaignNode(task=_task("step 1"))
        n2 = CampaignNode(task=_task("step 2"))
        n2.depends_on.append(n1.node_id)
        c.add_node(n1)
        c.add_node(n2)

        n1.status = NodeStatus.SUCCEEDED
        ready = c.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].node_id == n2.node_id

    def test_has_failed_nodes(self):
        c = Campaign(name="test", intent="test")
        n = CampaignNode(task=_task())
        n.status = NodeStatus.FAILED
        c.add_node(n)
        assert c.has_failed_nodes()

    def test_is_complete_all_terminal(self):
        c = Campaign(name="test", intent="test")
        n1 = CampaignNode(task=_task())
        n2 = CampaignNode(task=_task())
        n1.status = NodeStatus.SUCCEEDED
        n2.status = NodeStatus.SKIPPED
        c.add_node(n1)
        c.add_node(n2)
        assert c.is_complete()

    def test_progress_counts(self):
        c = Campaign(name="test", intent="test")
        for _ in range(3):
            n = CampaignNode(task=_task())
            n.status = NodeStatus.SUCCEEDED
            c.add_node(n)
        n_fail = CampaignNode(task=_task())
        n_fail.status = NodeStatus.FAILED
        c.add_node(n_fail)
        p = c.progress()
        assert p.get("succeeded") == 3
        assert p.get("failed") == 1

    def test_to_dict_roundtrip(self):
        c = Campaign(name="roundtrip", intent="test roundtrip")
        c.add_node(CampaignNode(task=_task("node 1")))
        d = c.to_dict()
        c2 = Campaign.from_dict(d)
        assert c2.name == "roundtrip"
        assert len(c2.nodes) == 1


# ---------------------------------------------------------------------------
# CampaignRegistry tests
# ---------------------------------------------------------------------------

class TestCampaignRegistry:
    def test_save_and_get(self, tmp_path):
        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        c = Campaign(name="test", intent="test")
        reg.save(c)
        found = reg.get(c.campaign_id)
        assert found is not None
        assert found.name == "test"

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "c.jsonl"
        c = Campaign(name="persisted", intent="test")
        CampaignRegistry(path=path).save(c)

        reg2 = CampaignRegistry(path=path)
        assert reg2.get(c.campaign_id) is not None

    def test_stats(self, tmp_path):
        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        c1 = Campaign(name="a", intent="a", status=CampaignStatus.RUNNING)
        c2 = Campaign(name="b", intent="b", status=CampaignStatus.SUCCEEDED)
        reg.save(c1)
        reg.save(c2)
        s = reg.stats()
        assert s["total"] == 2
        assert s.get("status.running") == 1
        assert s.get("status.succeeded") == 1

    def test_active_excludes_terminal(self, tmp_path):
        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        c_run = Campaign(name="running", intent="r", status=CampaignStatus.RUNNING)
        c_done = Campaign(name="done", intent="d", status=CampaignStatus.SUCCEEDED)
        reg.save(c_run)
        reg.save(c_done)
        active = reg.active()
        assert len(active) == 1
        assert active[0].name == "running"

    def test_delete(self, tmp_path):
        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        c = Campaign(name="to delete", intent="del")
        reg.save(c)
        assert reg.delete(c.campaign_id) is True
        assert reg.get(c.campaign_id) is None

    def test_recent_ordering(self, tmp_path):
        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        for i in range(5):
            c = Campaign(name=f"camp-{i}", intent="x")
            c.created_at = time.time() + i
            reg.save(c)
        recent = reg.recent(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0].name == "camp-4"


# ---------------------------------------------------------------------------
# CampaignEngine tests
# ---------------------------------------------------------------------------

class TestCampaignEngine:
    def test_create_campaign_sequential_deps(self, tmp_path):
        eng = _engine(tmp_path=tmp_path)
        tasks = [_task(f"step {i}") for i in range(3)]
        c = eng.create_campaign("deploy", "deploy app", tasks)

        nodes = list(c.nodes.values())
        assert len(nodes) == 3
        assert nodes[0].depends_on == []
        assert nodes[1].node_id in nodes[2].depends_on or nodes[1].depends_on == []
        # node 1 depends on node 0, node 2 depends on node 1
        assert nodes[2].depends_on == [nodes[1].node_id]

    def test_create_campaign_custom_deps(self, tmp_path):
        eng = _engine(tmp_path=tmp_path)
        tasks = [_task("a"), _task("b"), _task("c")]
        # c depends on a and b, b depends on a
        dep_map = {"1": ["0"], "2": ["0", "1"]}
        c = eng.create_campaign("parallel", "parallel ops", tasks, dependency_map=dep_map)

        nodes = list(c.nodes.values())
        assert nodes[0].depends_on == []
        assert len(nodes[2].depends_on) == 2  # c depends on a and b

    def test_create_campaign_persisted(self, tmp_path):
        eng = _engine(tmp_path=tmp_path)
        c = eng.create_campaign("persist-test", "check persist", [_task("one")])
        found = eng._registry.get(c.campaign_id)
        assert found is not None

    def test_create_campaign_emits_bus_event(self, tmp_path):
        bus = EventBus()
        events: list[dict] = []
        bus.subscribe("campaign.created", lambda t, p: events.append(p))
        eng = _engine(bus=bus, tmp_path=tmp_path)
        eng.create_campaign("event-test", "emit check", [_task("one")])
        assert len(events) == 1
        assert events[0]["name"] == "event-test"

    @pytest.mark.asyncio
    async def test_run_campaign_succeeds_with_stub(self, tmp_path):
        """All nodes succeed with the stub executor (no plan, no titan)."""
        eng = _engine(tmp_path=tmp_path)
        tasks = [_task("step 1"), _task("step 2")]
        c = eng.create_campaign("run-test", "run to success", tasks)

        result = await eng.run_campaign(c)
        assert result.status == CampaignStatus.SUCCEEDED
        assert all(n.status == NodeStatus.SUCCEEDED for n in result.nodes.values())

    @pytest.mark.asyncio
    async def test_run_campaign_single_node(self, tmp_path):
        eng = _engine(tmp_path=tmp_path)
        c = eng.create_campaign("single", "one node", [_task("only")])
        result = await eng.run_campaign(c)
        assert result.status == CampaignStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_run_campaign_with_failing_oracle_plan(self, tmp_path):
        """Oracle that returns a requires_approval plan causes node failure."""
        from pradyos.oracle.planner import OraclePlan
        from pradyos.oracle.oracle import Oracle

        mock_oracle = MagicMock(spec=Oracle)
        failing_plan = OraclePlan(
            task_id="tk_x", task_intent="destroy",
            requires_approval=True, approval_reason="Constitutional block",
        )
        mock_oracle.plan_task = AsyncMock(return_value=failing_plan)
        mock_oracle.record_outcome = AsyncMock()

        bus = EventBus()
        events: list[str] = []
        bus.subscribe("campaign.node.failed", lambda t, p: events.append(p["node_id"]))

        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        eng = CampaignEngine(oracle=mock_oracle, registry=reg, bus=bus)
        c = eng.create_campaign("blocked", "blocked campaign", [_task("destroy")])
        result = await eng.run_campaign(c)

        assert result.status in (CampaignStatus.FAILED, CampaignStatus.ROLLED_BACK)
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_rollback_campaign_manual(self, tmp_path):
        """Manual rollback of a running campaign succeeds."""
        eng = _engine(tmp_path=tmp_path)
        tasks = [_task("deploy"), _task("configure")]
        c = eng.create_campaign("rollback-test", "test rollback", tasks)
        # Simulate partial execution
        nodes = list(c.nodes.values())
        nodes[0].status = NodeStatus.SUCCEEDED
        c.status = CampaignStatus.RUNNING
        eng._registry.save(c)

        result = await eng.rollback_campaign(c.campaign_id)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_campaign_returns_error(self, tmp_path):
        eng = _engine(tmp_path=tmp_path)
        result = await eng.rollback_campaign("camp_nonexistent")
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_run_campaign_emits_succeeded_event(self, tmp_path):
        bus = EventBus()
        events: list[dict] = []
        bus.subscribe("campaign.succeeded", lambda t, p: events.append(p))

        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        eng = CampaignEngine(registry=reg, bus=bus)
        c = eng.create_campaign("emit-ok", "emit check", [_task("x")])
        await eng.run_campaign(c)

        assert len(events) == 1
        assert events[0]["campaign_id"] == c.campaign_id

    @pytest.mark.asyncio
    async def test_skipped_nodes_when_upstream_fails(self, tmp_path):
        """Nodes downstream of a failing node should be skipped."""
        from pradyos.oracle.planner import OraclePlan
        from pradyos.oracle.oracle import Oracle

        mock_oracle = MagicMock(spec=Oracle)
        fail_plan = OraclePlan(
            task_id="tk_fail", task_intent="fail me",
            requires_approval=True, approval_reason="test block",
        )
        ok_plan = OraclePlan(
            task_id="tk_ok", task_intent="should not run",
            steps=[], requires_approval=False,
        )
        mock_oracle.plan_task = AsyncMock(side_effect=[fail_plan, ok_plan])
        mock_oracle.record_outcome = AsyncMock()

        reg = CampaignRegistry(path=tmp_path / "c.jsonl")
        eng = CampaignEngine(oracle=mock_oracle, registry=reg, bus=EventBus())
        # Sequential: node1 → node2
        c = eng.create_campaign("skip-test", "skip chain", [_task("fail me"), _task("skip me")])
        result = await eng.run_campaign(c)

        statuses = {n.status for n in result.nodes.values()}
        assert NodeStatus.FAILED in statuses
        assert NodeStatus.SKIPPED in statuses
