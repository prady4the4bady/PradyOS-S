"""TITAN OPS tests — instruction schema, executor, lanes, daemon."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

import pytest

from pradyos.core.types import ExecutionLane
from pradyos.titan_ops.daemon import TitanClient, TitanDaemon, _use_unix_socket
from pradyos.titan_ops.executor import TitanExecutor
from pradyos.titan_ops.instruction import (
    InstructionKind,
    TitanInstruction,
    parse_instruction,
)


# ---------- instruction schema ----------

def test_parse_minimum_instruction():
    instr = parse_instruction({"agent_id": "imperium", "kind": "shell",
                                "command": "echo hi"})
    assert instr.agent_id == "imperium"
    assert instr.kind is InstructionKind.SHELL
    assert instr.lane is ExecutionLane.UNPRIVILEGED


def test_parse_rejects_missing_agent():
    with pytest.raises(ValueError):
        parse_instruction({"kind": "shell", "command": "echo"})


def test_parse_rejects_unknown_kind():
    with pytest.raises(ValueError):
        parse_instruction({"agent_id": "imperium", "kind": "nope", "command": "echo"})


def test_parse_round_trip():
    instr = TitanInstruction(agent_id="oracle", kind=InstructionKind.SHELL,
                              command="echo hello", intent="echo greeting")
    again = parse_instruction(instr.to_dict())
    assert again.command == "echo hello"
    assert again.kind is InstructionKind.SHELL


# ---------- executor ----------

def test_executor_runs_echo(isolated_audit, isolated_bus):
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL,
                              command=f"{sys.executable} -c \"print('phase0')\"",
                              intent="smoke test")
    result = ex.execute(instr)
    assert result.succeeded
    assert "phase0" in result.stdout


def test_executor_escalates_destructive(isolated_audit, isolated_bus):
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL,
                              command="rm -rf /etc")
    result = ex.execute(instr)
    assert result.escalated
    assert not result.succeeded
    assert result.exit_code is None
    audit_lines = isolated_audit.tail(10)
    assert any("ESCALATED" in r.summary for r in audit_lines)


def test_executor_handles_timeout(isolated_audit, isolated_bus):
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL,
                              command=f"{sys.executable} -c \"import time; time.sleep(5)\"",
                              timeout_sec=0.5)
    result = ex.execute(instr)
    assert result.timed_out
    assert not result.succeeded


def test_executor_records_rollback_hook(isolated_audit, isolated_bus):
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL,
                              command=f"{sys.executable} -c \"print(1)\"",
                              rollback_hook="rm -f /tmp/test")
    result = ex.execute(instr)
    assert result.succeeded
    entry = ex.rollback.get(instr.instruction_id)
    assert entry is not None
    assert entry.hook == "rm -f /tmp/test"


def test_executor_publishes_completion_event(isolated_audit, isolated_bus):
    received = []
    isolated_bus.subscribe("titan.completed", lambda t, p: received.append((t, p)))
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL,
                              command=f"{sys.executable} -c \"print(0)\"")
    ex.execute(instr)
    assert any(p["succeeded"] for _, p in received)


def test_executor_handles_missing_binary(isolated_audit, isolated_bus):
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL,
                              command="/no/such/binary/anywhere --arg")
    result = ex.execute(instr)
    assert not result.succeeded
    assert result.exit_code == 127


def test_executor_builds_package_argv():
    from pradyos.titan_ops.executor import _build_argv
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.PACKAGE,
                              args={"manager": "apt", "op": "install", "package": "htop"})
    argv = _build_argv(instr)
    assert argv == ["apt-get", "install", "-y", "htop"]


def test_executor_rejects_empty_command(isolated_audit, isolated_bus):
    ex = TitanExecutor(audit=isolated_audit, bus=isolated_bus)
    instr = TitanInstruction(agent_id="imperium", kind=InstructionKind.SHELL, command="")
    result = ex.execute(instr)
    assert not result.succeeded
    assert result.exit_code == -2


# ---------- daemon round-trip ----------

def test_daemon_serves_one_instruction(isolated_audit, isolated_bus):
    sock_dir = tempfile.mkdtemp(prefix="prd-")
    sock = os.path.join(sock_dir, "t.sock")
    daemon = TitanDaemon(
        socket_path=sock,
        executor=TitanExecutor(audit=isolated_audit, bus=isolated_bus),
    )
    t = threading.Thread(target=daemon.serve_forever, daemon=True)
    t.start()
    client = TitanClient(socket_path=sock,
                         tcp_host=daemon.tcp_host, tcp_port=daemon.tcp_port)
    assert client.wait_ready(timeout=3.0), "daemon did not become ready in time"
    try:
        resp = client.send({
            "agent_id": "test", "kind": "shell",
            "command": f"{sys.executable} -c \"print('roundtrip')\"",
            "intent": "round trip test",
        })
        assert resp["ok"] is True
        assert resp["result"]["succeeded"] is True
        assert "roundtrip" in resp["result"]["stdout"]
    finally:
        daemon.shutdown()
        t.join(timeout=2)
        shutil.rmtree(sock_dir, ignore_errors=True)
