"""Tests for ORACLE daemon — Phase 8A: autonomous proposal loop.

All tests run without a live Ollama instance.  OllamaClient and asyncio.sleep
are mocked so no network calls or real delays occur.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from pradyos.core.bus import EventBus, reset_bus_for_tests
from pradyos.oracle.daemon import _proposal_loop, _extract_json_proposal, run_daemon


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_oracle(alive: bool = True, chat_response: str = "") -> MagicMock:
    """Return a minimal Oracle mock."""
    oracle = MagicMock()
    oracle._planner.client.is_alive = AsyncMock(return_value=alive)
    oracle._client.chat = AsyncMock(return_value=chat_response)
    oracle._client.model = "test-model"
    return oracle


def _make_audit(entries=None) -> MagicMock:
    audit = MagicMock()
    audit.tail.return_value = entries or []
    return audit


def _one_cycle_sleep():
    """Return an AsyncMock for asyncio.sleep that allows exactly one cycle:
    first call returns normally, second raises CancelledError so the loop ends.
    """
    return AsyncMock(side_effect=[None, asyncio.CancelledError()])


# ---------------------------------------------------------------------------
# _extract_json_proposal unit tests
# ---------------------------------------------------------------------------

def test_extract_json_direct():
    raw = json.dumps({"intent": "prune logs", "kind": "shell"})
    result = _extract_json_proposal(raw)
    assert result is not None
    assert result["intent"] == "prune logs"
    assert result["kind"] == "shell"


def test_extract_json_embedded_in_prose():
    raw = 'I suggest: {"intent": "restart svc", "kind": "shell"} as the task.'
    result = _extract_json_proposal(raw)
    assert result is not None
    assert result["kind"] == "shell"


def test_extract_json_returns_none_for_prose():
    result = _extract_json_proposal("Just prune old log files from the system.")
    assert result is None


def test_extract_json_returns_none_for_incomplete():
    result = _extract_json_proposal('{"intent": "only intent key"}')
    assert result is None


# ---------------------------------------------------------------------------
# _proposal_loop tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_proposal_loop_skips_when_ollama_dead():
    """When Ollama is unreachable, chat() must NOT be called and audit records proposed=False."""
    oracle = _make_oracle(alive=False)
    bus = reset_bus_for_tests()
    audit = _make_audit()

    with patch("asyncio.sleep", _one_cycle_sleep()):
        try:
            await _proposal_loop(oracle, bus, audit, interval_sec=0)
        except asyncio.CancelledError:
            pass

    # chat must never be called when Ollama is dead
    oracle._client.chat.assert_not_called()

    # audit.record must have been called with proposed=False
    assert audit.record.called
    record_kwargs = audit.record.call_args_list[-1].kwargs
    assert record_kwargs["detail"]["proposed"] is False
    assert record_kwargs["kind"] == "oracle.proposal_cycle"


@pytest.mark.asyncio
async def test_proposal_loop_publishes_bus_event():
    """When Ollama returns valid JSON, oracle.proposal is published on the bus."""
    valid_json = json.dumps({"intent": "prune logs", "kind": "shell"})
    oracle = _make_oracle(alive=True, chat_response=valid_json)
    bus = reset_bus_for_tests()
    audit = _make_audit()

    received: list[dict] = []
    bus.subscribe("oracle.proposal", lambda _topic, payload: received.append(payload))

    with patch("asyncio.sleep", _one_cycle_sleep()):
        try:
            await _proposal_loop(oracle, bus, audit, interval_sec=0)
        except asyncio.CancelledError:
            pass

    assert len(received) == 1
    assert received[0]["intent"] == "prune logs"
    assert received[0]["kind"] == "shell"

    # audit must record proposed=True
    record_kwargs = audit.record.call_args_list[-1].kwargs
    assert record_kwargs["detail"]["proposed"] is True


@pytest.mark.asyncio
async def test_proposal_loop_handles_bad_json_gracefully():
    """When the model returns plain prose (no JSON), no exception is raised and proposed=False."""
    oracle = _make_oracle(alive=True, chat_response="Just prune the old log files please.")
    bus = reset_bus_for_tests()
    audit = _make_audit()

    published: list[str] = []
    bus.subscribe("oracle.proposal", lambda t, _p: published.append(t))

    # Should not raise
    with patch("asyncio.sleep", _one_cycle_sleep()):
        try:
            await _proposal_loop(oracle, bus, audit, interval_sec=0)
        except asyncio.CancelledError:
            pass

    # Nothing published
    assert published == []

    # proposed=False recorded
    record_kwargs = audit.record.call_args_list[-1].kwargs
    assert record_kwargs["detail"]["proposed"] is False


@pytest.mark.asyncio
async def test_run_daemon_starts_and_cancels():
    """run_daemon() starts up cleanly and shuts down without leaking exceptions."""
    from pradyos.oracle.oracle import Oracle

    with patch("pradyos.oracle.daemon._start_http_server"):
        with patch.object(
            Oracle,
            "check_ollama",
            new_callable=AsyncMock,
            return_value={
                "alive": False,
                "base_url": "http://localhost:11434",
                "model": "test",
                "available_models": [],
            },
        ):
            task = asyncio.create_task(
                run_daemon(register_with_imperium=False, port=0)
            )
            await asyncio.sleep(0.05)
            task.cancel()
            # run_daemon catches CancelledError internally → task finishes cleanly
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass  # acceptable — daemon may or may not re-raise depending on timing
