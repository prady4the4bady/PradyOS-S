"""Tests for the OS shell's real-system endpoints (system_web).

These power the console's System Overview, PRISM neofetch, System Monitor, and
File Manager. They must always answer (psutil present or not) and the file
listing must never escape its configured root.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_metrics_always_answers_with_core_gauges():
    data = _client().get("/api/v1/system/metrics").json()
    for k in ("cpu", "gpu", "ram", "disk"):
        assert k in data
        assert 0 <= data[k] <= 100


def test_info_has_neofetch_fields():
    data = _client().get("/api/v1/system/info").json()
    assert data["os"] == "PRADYOS Sovereign Edition"
    for k in ("kernel", "host", "shell", "mem_total", "uptime"):
        assert k in data


def test_processes_returns_a_list():
    data = _client().get("/api/v1/system/processes").json()
    assert isinstance(data["processes"], list)
    assert data["processes"], "expected at least one process row"
    assert "name" in data["processes"][0]


def test_files_lists_home_root():
    data = _client().get("/api/v1/files?path=~").json()
    assert "entries" in data and isinstance(data["entries"], list)
    assert data["root"]


def test_files_refuses_traversal_escape():
    # Asking for the filesystem root must clamp back to the scoped root, never
    # leak the parent tree.
    data = _client().get("/api/v1/files?path=/").json()
    root = Path(data["root"]).resolve()
    served = Path(data["path"]).resolve()
    assert served == root or root in served.parents or served == root


def test_files_scoped_root_via_env(monkeypatch, tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    monkeypatch.setenv("PRADYOS_FILES_ROOT", str(tmp_path))
    data = _client().get("/api/v1/files?path=~").json()
    names = {e["name"] for e in data["entries"]}
    assert "alpha" in names and "note.txt" in names
    # an attempt to climb above the root is clamped to the root
    up = _client().get(f"/api/v1/files?path={tmp_path.parent}").json()
    assert Path(up["path"]).resolve() == tmp_path.resolve()
