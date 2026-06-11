"""Cross-plane integration test — TITAN OPS + IMPERIUM + audit."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

import pytest

from pradyos.core.types import TaskState
from pradyos.imperium.checkpoint import CheckpointStore
from pradyos.imperium.kernel import Imperium
from pradyos.imperium.task import ImperiumTask
from pradyos.titan_ops.daemon import TitanClient, TitanDaemon, _use_unix_socket


def test_imperium_dispatches_to_titan_via_socket(
    isolated_audit, isolated_bus, tmp_state, monkeypatch
):
    sock_dir = tempfile.mkdtemp(prefix="prdi-")
    sock = os.path.join(sock_dir, "t.sock")
    monkeypatch.setenv("PRADYOS_TITAN_SOCKET", sock)

    daemon = TitanDaemon(socket_path=sock)
    daemon.executor.audit = isolated_audit
    daemon.executor.bus = isolated_bus
    t = threading.Thread(target=daemon.serve_forever, daemon=True)
    t.start()
    client_probe = TitanClient(socket_path=sock,
                               tcp_host=daemon.tcp_host, tcp_port=daemon.tcp_port)
    assert client_probe.wait_ready(timeout=3.0), "titan daemon did not start"

    try:
        kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                        checkpoint=CheckpointStore(state_dir=tmp_state))
        rec = kern.submit(ImperiumTask(
            kind="titan.shell",
            intent="echo via imperium",
            payload={"command": f"{sys.executable} -c \"print('via-imperium')\"",
                     "timeout_sec": 20},
        ))
        kern.run_one()
        assert rec.state is TaskState.SUCCEEDED
        assert rec.last_result is not None
        assert "via-imperium" in (rec.last_result.get("stdout_tail") or "")
    finally:
        daemon.shutdown()
        t.join(timeout=2)
        shutil.rmtree(sock_dir, ignore_errors=True)


def test_audit_ledger_captures_full_lifecycle(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))

    kern.register_handler("noop", lambda t: {"ok": True})
    kern.submit(ImperiumTask(kind="noop", intent="ledger lifecycle"))
    kern.run_one()

    summaries = [r.summary for r in isolated_audit.tail(20)]
    assert any("queued" in s for s in summaries)
    assert any("running" in s for s in summaries)
    assert any("succeeded" in s for s in summaries)
