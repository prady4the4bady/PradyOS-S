"""Shared pytest fixtures — every test runs against an isolated audit log
and a fresh event bus so cross-test contamination is impossible."""

from __future__ import annotations

import pytest

from pradyos.core import audit as audit_mod
from pradyos.core import bus as bus_mod


@pytest.fixture()
def isolated_audit(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = audit_mod.reset_audit_log_for_tests(path)
    yield log


@pytest.fixture()
def isolated_bus():
    yield bus_mod.reset_bus_for_tests()


@pytest.fixture()
def tmp_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("PRADYOS_STATE_PATH", str(state_dir))
    return state_dir
