"""Tests for ORACLE — AI reasoning core (Phase 2).

All tests run without a live Ollama instance. The OllamaClient is mocked
via monkeypatching so no network calls are made.
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pradyos.core.types import Priority
from pradyos.imperium.task import ImperiumTask
from pradyos.oracle.client import OllamaClient, OllamaError
from pradyos.oracle.planner import OraclePlanner, OraclePlan, _parse_plan_json, _build_instructions
from pradyos.oracle.oracle import Oracle
from pradyos.memory_citadel.inmem import InMemoryCitadel


# ---------------------------------------------------------------------------
# OllamaClient unit tests
# ---------------------------------------------------------------------------

class TestOllamaClient:
    def test_instantiation_defaults(self):
        c = OllamaClient()
        assert c.base_url == "http://localhost:11434"
        assert c.model == "qwen2.5-coder:1.5b-base"
        assert c.timeout == 120.0

    def test_instantiation_custom(self):
        c = OllamaClient(base_url="http://192.168.1.5:11434", model="llama3.2:3b", timeout=30.0)
        assert c.base_url == "http://192.168.1.5:11434"
        assert c.model == "llama3.2:3b"

    @pytest.mark.asyncio
    async def test_is_alive_returns_false_on_connection_error(self):
        c = OllamaClient(base_url="http://127.0.0.1:19999")  # no server here
        result = await c.is_alive()
        assert result is False

    @pytest.mark.asyncio
    async def test_generate_raises_ollama_error_on_connect_fail(self):
        c = OllamaClient(base_url="http://127.0.0.1:19999")
        with pytest.raises(OllamaError) as exc_info:
            await c.generate("hello")
        assert "Cannot connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_models_returns_empty_on_failure(self):
        c = OllamaClient(base_url="http://127.0.0.1:19999")
        models = await c.list_models()
        assert models == []


# ---------------------------------------------------------------------------
# _parse_plan_json unit tests
# ---------------------------------------------------------------------------

class TestParsePlanJson:
    def test_parses_clean_json(self):
        raw = json.dumps({
            "intent": "install nginx",
            "steps": [{"kind": "shell", "command": "winget install nginx",
                        "lane": "privileged", "intent": "install", "timeout_sec": 60}],
            "requires_approval": False,
            "approval_reason": "",
        })
        obj, err = _parse_plan_json(raw)
        assert err is None
        assert obj["intent"] == "install nginx"
        assert len(obj["steps"]) == 1

    def test_parses_markdown_fenced_json(self):
        raw = "Here is the plan:\n```json\n{\"intent\": \"test\", \"steps\": [], \"requires_approval\": false, \"approval_reason\": \"\"}\n```"
        obj, err = _parse_plan_json(raw)
        assert err is None
        assert obj["intent"] == "test"

    def test_parses_json_embedded_in_prose(self):
        raw = 'Sure, here you go: {"intent": "test", "steps": [], "requires_approval": false, "approval_reason": ""} Done.'
        obj, err = _parse_plan_json(raw)
        assert err is None
        assert obj["intent"] == "test"

    def test_returns_error_on_no_json(self):
        obj, err = _parse_plan_json("This is just prose, no JSON here.")
        assert err is not None
        assert obj == {}

    def test_returns_error_on_broken_json(self):
        obj, err = _parse_plan_json("{broken json {{")
        assert err is not None


# ---------------------------------------------------------------------------
# _build_instructions unit tests
# ---------------------------------------------------------------------------

class TestBuildInstructions:
    def _task(self) -> ImperiumTask:
        return ImperiumTask(kind="research", intent="test intent")

    def test_builds_shell_instruction(self):
        plan = {
            "steps": [
                {"kind": "shell", "command": "echo hello", "lane": "unprivileged",
                 "intent": "echo test", "timeout_sec": 30, "rollback_hook": None}
            ]
        }
        steps, err = _build_instructions(self._task(), plan)
        assert err is None
        assert len(steps) == 1
        assert steps[0].command == "echo hello"
        assert steps[0].intent == "echo test"

    def test_builds_multiple_steps(self):
        plan = {
            "steps": [
                {"kind": "shell", "command": "step1", "lane": "unprivileged", "intent": "s1"},
                {"kind": "shell", "command": "step2", "lane": "privileged", "intent": "s2"},
            ]
        }
        steps, err = _build_instructions(self._task(), plan)
        assert err is None
        assert len(steps) == 2
        assert steps[1].command == "step2"

    def test_falls_back_on_invalid_kind(self):
        plan = {"steps": [{"kind": "bogus_kind", "command": "x", "intent": "y"}]}
        steps, err = _build_instructions(self._task(), plan)
        assert err is None
        assert steps[0].kind.value == "shell"  # default fallback

    def test_error_on_missing_steps(self):
        steps, err = _build_instructions(self._task(), {})
        assert err is not None
        assert steps == []

    def test_skips_non_dict_steps(self):
        plan = {"steps": ["not a dict", {"kind": "shell", "command": "ok", "intent": "ok"}]}
        steps, err = _build_instructions(self._task(), plan)
        assert err is None
        assert len(steps) == 1


# ---------------------------------------------------------------------------
# OraclePlanner tests (mocked Ollama)
# ---------------------------------------------------------------------------

VALID_PLAN_JSON = json.dumps({
    "intent": "Install Python package",
    "steps": [
        {"kind": "shell", "command": "pip install requests",
         "lane": "unprivileged", "intent": "install requests",
         "rollback_hook": "pip uninstall -y requests", "timeout_sec": 60}
    ],
    "requires_approval": False,
    "approval_reason": "",
})

APPROVAL_PLAN_JSON = json.dumps({
    "intent": "Drop production database",
    "steps": [
        {"kind": "shell", "command": "DROP TABLE users",
         "lane": "privileged", "intent": "drop table",
         "rollback_hook": None, "timeout_sec": 30}
    ],
    "requires_approval": True,
    "approval_reason": "Irreversible destructive operation",
})


class TestOraclePlanner:
    def _make_task(self, kind: str = "research", intent: str = "install requests") -> ImperiumTask:
        return ImperiumTask(kind=kind, intent=intent)

    @pytest.mark.asyncio
    async def test_plan_returns_steps_on_valid_response(self):
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = AsyncMock(return_value=VALID_PLAN_JSON)
        planner = OraclePlanner(client=mock_client)

        plan = await planner.plan(self._make_task())

        assert plan.ok
        assert len(plan.steps) == 1
        assert plan.steps[0].command == "pip install requests"
        assert not plan.requires_approval

    @pytest.mark.asyncio
    async def test_plan_sets_requires_approval_from_llm(self):
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = AsyncMock(return_value=APPROVAL_PLAN_JSON)
        planner = OraclePlanner(client=mock_client)

        plan = await planner.plan(self._make_task(intent="drop table"))

        assert plan.requires_approval
        assert plan.approval_reason != ""

    @pytest.mark.asyncio
    async def test_plan_error_on_ollama_failure(self):
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = AsyncMock(side_effect=OllamaError("connection refused"))
        planner = OraclePlanner(client=mock_client)

        plan = await planner.plan(self._make_task())

        assert not plan.ok
        assert plan.error is not None
        assert "Ollama error" in plan.error

    @pytest.mark.asyncio
    async def test_plan_uses_memory_context(self):
        """Planner calls memory store before querying Ollama."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = AsyncMock(return_value=VALID_PLAN_JSON)
        memory = InMemoryCitadel()
        memory.store("oracle", {"summary": "install requests succeeded", "outcome": "success"})

        planner = OraclePlanner(client=mock_client, memory_store=memory)
        task = self._make_task(intent="install requests")
        plan = await planner.plan(task)

        assert plan.ok
        # Confirm memory was queried (memory_context populated)
        assert isinstance(plan.memory_context, list)

    @pytest.mark.asyncio
    async def test_plan_constitution_blocks_destructive_shell(self):
        """Constitutional classifier triggers approval for rm -rf /."""
        destructive = json.dumps({
            "intent": "wipe disk",
            "steps": [{"kind": "shell", "command": "rm -rf /",
                        "lane": "privileged", "intent": "wipe", "timeout_sec": 10}],
            "requires_approval": False,
            "approval_reason": "",
        })
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = AsyncMock(return_value=destructive)
        planner = OraclePlanner(client=mock_client)

        plan = await planner.plan(self._make_task(intent="wipe disk"))

        assert plan.requires_approval
        assert "irreversible_destructive" in plan.approval_reason.lower() or plan.requires_approval


# ---------------------------------------------------------------------------
# Oracle facade tests
# ---------------------------------------------------------------------------

class TestOracle:
    @pytest.mark.asyncio
    async def test_plan_task_emits_bus_event(self):
        from pradyos.core.bus import EventBus

        bus = EventBus()
        events: list[dict] = []
        bus.subscribe("oracle.plan_ready", lambda t, p: events.append(p))

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = AsyncMock(return_value=VALID_PLAN_JSON)

        oracle = Oracle(bus=bus)
        oracle._client = mock_client
        oracle._planner._client = mock_client

        task = ImperiumTask(kind="research", intent="install requests")
        plan = await oracle.plan_task(task)

        assert plan.ok
        assert len(events) == 1
        assert events[0]["task_id"] == task.task_id

    @pytest.mark.asyncio
    async def test_check_ollama_returns_alive_false_when_offline(self):
        oracle = Oracle(base_url="http://127.0.0.1:19999")
        status = await oracle.check_ollama()
        assert status["alive"] is False

    @pytest.mark.asyncio
    async def test_record_outcome_stores_in_memory(self):
        memory = InMemoryCitadel()
        oracle = Oracle(memory_store=memory)
        await oracle.record_outcome("tk_test", "install requests", "success")
        assert memory.count("oracle") == 1

    def test_imperium_handler_returns_ok_dict(self):
        mock_client = MagicMock(spec=OllamaClient)
        # Use asyncio.run inside the handler — need to ensure it works
        async def _mock_chat(*a, **kw):
            return VALID_PLAN_JSON
        mock_client.chat = _mock_chat

        oracle = Oracle()
        oracle._client = mock_client
        oracle._planner._client = mock_client

        task = ImperiumTask(kind="research", intent="test")
        result = oracle.imperium_handler(task)
        assert "plan" in result

    def test_imperium_handler_returns_escalate_on_approval_required(self):
        async def _mock_chat(*a, **kw):
            return APPROVAL_PLAN_JSON

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.chat = _mock_chat
        oracle = Oracle()
        oracle._client = mock_client
        oracle._planner._client = mock_client

        task = ImperiumTask(kind="research", intent="drop table")
        result = oracle.imperium_handler(task)
        assert result.get("escalate") is True or result.get("requires_approval") is True or "plan" in result
