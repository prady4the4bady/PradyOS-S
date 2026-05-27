"""
pradyos/core/plugin_sandbox.py
Phase 26 — Sovereign Plugin Sandbox

Lightweight plugin loader with manifest validation and hot-reload.
All methods are thread-safe via a single threading.Lock.
"""
from __future__ import annotations

import importlib.util
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PluginManifest:
    """Validated metadata extracted from a plugin's PLUGIN_MANIFEST dict."""

    name: str
    version: str
    hooks: list[str]

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version, "hooks": list(self.hooks)}


@dataclass
class LoadedPlugin:
    """Represents a plugin file that has been processed by the sandbox."""

    manifest: PluginManifest
    path: str         # absolute path to the .py file
    loaded_at: float  # time.time() when last loaded
    status: str       # "active" | "error"
    error: str | None # error message if status == "error"

    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest.to_dict(),
            "path": self.path,
            "loaded_at": self.loaded_at,
            "status": self.status,
            "error": self.error,
        }


class PluginSandbox:
    """Discover, load, and manage Python plugins from a directory."""

    def __init__(self, plugin_dir: str | Path | None = None) -> None:
        self.plugin_dir: Path = (
            Path(plugin_dir) if plugin_dir is not None else Path("plugins")
        )
        self.plugins: dict[str, LoadedPlugin] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[str]:
        """Scan plugin_dir for *.py files (non-recursive).

        Returns a sorted list of absolute path strings.
        Returns [] if the directory does not exist.
        """
        if not self.plugin_dir.exists():
            return []
        return sorted(str(p.resolve()) for p in self.plugin_dir.glob("*.py"))

    # ------------------------------------------------------------------
    # Load / reload
    # ------------------------------------------------------------------

    def load(self, path: str | Path) -> LoadedPlugin:
        """Load a single plugin from *path*.

        Validates that the module exposes a PLUGIN_MANIFEST dict with the
        required keys ("name" str, "version" str, "hooks" list).

        On success  -> LoadedPlugin(status="active", error=None)
        On any error -> LoadedPlugin(status="error", error=<message>)

        The plugin is stored in self.plugins keyed by manifest.name
        (or by the absolute path string if loading failed).
        """
        abs_path = str(Path(path).resolve())
        ts = time.time()

        try:
            spec = importlib.util.spec_from_file_location(
                f"_pradyos_plugin_{abs_path}", abs_path
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for {abs_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            raw: Any = getattr(module, "PLUGIN_MANIFEST", None)
            if not isinstance(raw, dict):
                raise ValueError("invalid manifest")
            for required_key, required_type in (
                ("name", str),
                ("version", str),
                ("hooks", list),
            ):
                if required_key not in raw:
                    raise ValueError("invalid manifest")
                if not isinstance(raw[required_key], required_type):
                    raise ValueError("invalid manifest")

            manifest = PluginManifest(
                name=raw["name"],
                version=raw["version"],
                hooks=list(raw["hooks"]),
            )
            plugin = LoadedPlugin(
                manifest=manifest,
                path=abs_path,
                loaded_at=ts,
                status="active",
                error=None,
            )
            key = manifest.name

        except Exception as exc:
            err_msg = str(exc) if str(exc) else "invalid manifest"
            manifest = PluginManifest(name=abs_path, version="unknown", hooks=[])
            plugin = LoadedPlugin(
                manifest=manifest,
                path=abs_path,
                loaded_at=ts,
                status="error",
                error=err_msg,
            )
            key = abs_path

        with self._lock:
            self.plugins[key] = plugin

        return plugin

    def reload_all(self) -> dict[str, LoadedPlugin]:
        """Discover all *.py files in plugin_dir and load each one.

        Returns a dict of all currently-loaded plugins (name -> LoadedPlugin).
        """
        for file_path in self.discover():
            self.load(file_path)
        with self._lock:
            return dict(self.plugins)

    # ------------------------------------------------------------------
    # Queries / management
    # ------------------------------------------------------------------

    def get_plugins(self) -> list[LoadedPlugin]:
        """Return a snapshot list of all loaded plugins."""
        with self._lock:
            return list(self.plugins.values())

    def unload(self, name: str) -> bool:
        """Remove a plugin by its manifest name.

        Returns True if found and removed, False if not found.
        """
        with self._lock:
            if name in self.plugins:
                del self.plugins[name]
                return True
            return False

    def status(self) -> dict:
        """Return a summary dict for the sandbox state."""
        with self._lock:
            total = len(self.plugins)
            active = sum(1 for p in self.plugins.values() if p.status == "active")
            errors = sum(1 for p in self.plugins.values() if p.status == "error")
        return {
            "total": total,
            "active": active,
            "errors": errors,
            "plugin_dir": str(self.plugin_dir),
        }
