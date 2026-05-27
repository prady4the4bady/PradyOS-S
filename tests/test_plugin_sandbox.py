"""
tests/test_plugin_sandbox.py
Phase 26 — 20 tests for PluginSandbox / PluginManifest / LoadedPlugin.
Uses tmp_path fixture for isolated, hermetic file-system operations.
"""
from __future__ import annotations

import concurrent.futures
import textwrap
import time
from pathlib import Path

import pytest

from pradyos.core.plugin_sandbox import (
    LoadedPlugin,
    PluginManifest,
    PluginSandbox,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PLUGIN_SRC = textwrap.dedent("""\
    PLUGIN_MANIFEST = {"name": "test_plugin", "version": "1.0", "hooks": ["on_start"]}

    def on_start():
        pass
""")


def _write_plugin(directory: Path, name: str = "plugin_a.py", src: str = VALID_PLUGIN_SRC) -> Path:
    p = directory / name
    p.write_text(src, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_sandbox_initialises_with_empty_plugins(tmp_path: Path) -> None:
    sb = PluginSandbox(tmp_path)
    assert sb.plugins == {}


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------

def test_discover_returns_empty_when_dir_missing() -> None:
    sb = PluginSandbox("/this/path/does/not/exist/ever")
    assert sb.discover() == []


def test_discover_finds_py_files(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "alpha.py")
    _write_plugin(tmp_path, "beta.py")
    sb = PluginSandbox(tmp_path)
    found = sb.discover()
    assert len(found) == 2
    assert all(f.endswith(".py") for f in found)


def test_discover_returns_sorted(tmp_path: Path) -> None:
    for name in ("zebra.py", "alpha.py", "mango.py"):
        _write_plugin(tmp_path, name)
    sb = PluginSandbox(tmp_path)
    found = sb.discover()
    assert found == sorted(found)


# ---------------------------------------------------------------------------
# load() — success path
# ---------------------------------------------------------------------------

def test_load_valid_plugin_status_active(tmp_path: Path) -> None:
    p = _write_plugin(tmp_path)
    sb = PluginSandbox(tmp_path)
    result = sb.load(p)
    assert result.status == "active"


def test_load_valid_plugin_manifest_is_dataclass(tmp_path: Path) -> None:
    p = _write_plugin(tmp_path)
    sb = PluginSandbox(tmp_path)
    result = sb.load(p)
    assert isinstance(result.manifest, PluginManifest)


def test_load_stores_plugin_in_self_plugins(tmp_path: Path) -> None:
    p = _write_plugin(tmp_path)
    sb = PluginSandbox(tmp_path)
    result = sb.load(p)
    assert result.manifest.name in sb.plugins


# ---------------------------------------------------------------------------
# load() — error paths
# ---------------------------------------------------------------------------

def test_load_invalid_manifest_missing_key_returns_error(tmp_path: Path) -> None:
    # Manifest is missing the "hooks" key
    bad_src = textwrap.dedent("""\
        PLUGIN_MANIFEST = {"name": "bad_plugin", "version": "0.1"}
    """)
    p = _write_plugin(tmp_path, "bad.py", bad_src)
    sb = PluginSandbox(tmp_path)
    result = sb.load(p)
    assert result.status == "error"
    assert result.error is not None


def test_load_syntax_error_file_returns_error(tmp_path: Path) -> None:
    broken_src = "def broken(: pass\n"
    p = _write_plugin(tmp_path, "broken.py", broken_src)
    sb = PluginSandbox(tmp_path)
    result = sb.load(p)
    assert result.status == "error"
    assert result.error is not None


# ---------------------------------------------------------------------------
# reload_all()
# ---------------------------------------------------------------------------

def test_reload_all_loads_all_discovered_plugins(tmp_path: Path) -> None:
    for i in range(3):
        src = textwrap.dedent(f"""\
            PLUGIN_MANIFEST = {{"name": "plugin_{i}", "version": "1.0", "hooks": []}}
        """)
        (tmp_path / f"plugin_{i}.py").write_text(src, encoding="utf-8")
    sb = PluginSandbox(tmp_path)
    result = sb.reload_all()
    assert len(result) == 3


def test_reload_all_returns_dict_keyed_by_name(tmp_path: Path) -> None:
    src = textwrap.dedent("""\
        PLUGIN_MANIFEST = {"name": "keyed_plugin", "version": "1.0", "hooks": []}
    """)
    (tmp_path / "keyed.py").write_text(src, encoding="utf-8")
    sb = PluginSandbox(tmp_path)
    result = sb.reload_all()
    assert "keyed_plugin" in result
    assert isinstance(result["keyed_plugin"], LoadedPlugin)


# ---------------------------------------------------------------------------
# get_plugins()
# ---------------------------------------------------------------------------

def test_get_plugins_returns_list(tmp_path: Path) -> None:
    sb = PluginSandbox(tmp_path)
    assert isinstance(sb.get_plugins(), list)


def test_get_plugins_returns_copy_mutation_safe(tmp_path: Path) -> None:
    p = _write_plugin(tmp_path)
    sb = PluginSandbox(tmp_path)
    sb.load(p)
    snapshot = sb.get_plugins()
    original_len = len(snapshot)
    snapshot.clear()            # mutate the returned list
    assert len(sb.get_plugins()) == original_len  # sandbox unaffected


# ---------------------------------------------------------------------------
# unload()
# ---------------------------------------------------------------------------

def test_unload_removes_plugin_returns_true(tmp_path: Path) -> None:
    p = _write_plugin(tmp_path)
    sb = PluginSandbox(tmp_path)
    sb.load(p)
    assert sb.unload("test_plugin") is True
    assert "test_plugin" not in sb.plugins


def test_unload_returns_false_for_unknown_name(tmp_path: Path) -> None:
    sb = PluginSandbox(tmp_path)
    assert sb.unload("ghost_plugin") is False


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status_returns_required_keys(tmp_path: Path) -> None:
    sb = PluginSandbox(tmp_path)
    s = sb.status()
    for key in ("total", "active", "errors", "plugin_dir"):
        assert key in s


def test_status_active_count_reflects_only_active_plugins(tmp_path: Path) -> None:
    # One valid, one broken
    _write_plugin(tmp_path, "good.py", VALID_PLUGIN_SRC)
    broken_src = "PLUGIN_MANIFEST = {'name': 'oops'}\n"  # missing version + hooks
    _write_plugin(tmp_path, "bad.py", broken_src)
    sb = PluginSandbox(tmp_path)
    sb.reload_all()
    s = sb.status()
    assert s["active"] == 1
    assert s["errors"] == 1
    assert s["total"] == 2


# ---------------------------------------------------------------------------
# to_dict()
# ---------------------------------------------------------------------------

def test_plugin_manifest_to_dict_has_required_keys() -> None:
    m = PluginManifest(name="x", version="1", hooks=["a"])
    d = m.to_dict()
    assert "name" in d
    assert "version" in d
    assert "hooks" in d


def test_loaded_plugin_to_dict_has_required_keys(tmp_path: Path) -> None:
    p = _write_plugin(tmp_path)
    sb = PluginSandbox(tmp_path)
    lp = sb.load(p)
    d = lp.to_dict()
    for key in ("manifest", "path", "loaded_at", "status", "error"):
        assert key in d


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_thread_safety_20_concurrent_loads_all_register(tmp_path: Path) -> None:
    """20 concurrent load() calls on 20 distinct plugin files all register."""
    files: list[Path] = []
    for i in range(20):
        src = textwrap.dedent(f"""\
            PLUGIN_MANIFEST = {{"name": "thread_plugin_{i}", "version": "1.0",
                                "hooks": ["on_start"]}}
            def on_start(): pass
        """)
        fp = tmp_path / f"thread_plugin_{i}.py"
        fp.write_text(src, encoding="utf-8")
        files.append(fp)

    sb = PluginSandbox(tmp_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(sb.load, f) for f in files]
        concurrent.futures.wait(futures)

    assert len(sb.plugins) == 20
