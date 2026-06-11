"""SovereignConfig — typed configuration for PRADY OS (Phase 6).

Resolution order (highest to lowest priority):
  1. Environment variables  (PRADYOS_* prefixed)
  2. pradyos.toml [sovereign] section (if file exists next to project root)
  3. Compiled-in defaults

get_config() returns a cached singleton after the first call.
load_config() re-reads everything and replaces the singleton.

Windows-safe: all paths via pathlib; no platform-specific calls.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]  # project root


# ---------------------------------------------------------------------------
# SovereignConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class SovereignConfig:
    """Typed, flat configuration object for the entire PradyOS sovereign."""

    # Oracle / LLM gateway
    oracle_url: str = "http://localhost:11434"

    # Titan execution host
    titan_host: str = "127.0.0.1"
    titan_port: int = 7331

    # Persistent state directory
    state_dir: str = str(_ROOT / "var" / "state")

    # Logging
    log_level: str = "INFO"

    # Campaign concurrency
    max_campaign_workers: int = 4

    # Retry
    retry_max_attempts: int = 3


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _read_toml_section(toml_path: Path, section: str) -> dict[str, Any]:
    """Parse a single TOML section without third-party libs (Python 3.11+).

    Falls back to an empty dict on any error or if the section is absent.
    """
    if not toml_path.exists():
        return {}
    try:
        import tomllib  # Python 3.11+

        with toml_path.open("rb") as f:
            data = tomllib.load(f)
        return dict(data.get(section, {}))
    except (ImportError, ModuleNotFoundError):
        # Python < 3.11 — try tomli (optional dep)
        try:
            import tomli  # type: ignore[import]

            with toml_path.open("rb") as f:
                data = tomli.load(f)
            return dict(data.get(section, {}))
        except (ImportError, ModuleNotFoundError):
            pass
    except Exception:  # noqa: BLE001
        pass
    return {}


def _coerce(value: str, target_type: type) -> Any:
    """Coerce a string env-var value to the target Python type."""
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is bool:
        return value.lower() in ("1", "true", "yes", "on")
    return value  # str


_ENV_MAP: dict[str, str] = {
    "PRADYOS_ORACLE_URL": "oracle_url",
    "PRADYOS_TITAN_HOST": "titan_host",
    "PRADYOS_TITAN_PORT": "titan_port",
    "PRADYOS_STATE_PATH": "state_dir",
    "PRADYOS_LOG_LEVEL": "log_level",
    "PRADYOS_MAX_CAMPAIGN_WORKERS": "max_campaign_workers",
    "PRADYOS_RETRY_MAX_ATTEMPTS": "retry_max_attempts",
    # Also honour SOVEREIGN_RETRY_MAX (Phase 6 spec)
    "SOVEREIGN_RETRY_MAX": "retry_max_attempts",
}


def load_config(toml_path: Path | None = None) -> SovereignConfig:
    """Build a SovereignConfig from env → TOML → defaults (in priority order).

    Also resets and returns the global singleton.
    """
    toml_path = toml_path or (_ROOT / "pradyos.toml")

    # Start with defaults
    cfg = SovereignConfig()

    # Layer 1: TOML overrides
    toml_data = _read_toml_section(toml_path, "sovereign")
    field_types = {f.name: f.type for f in cfg.__dataclass_fields__.values()}  # type: ignore[union-attr]  # noqa: F841

    for key, raw_val in toml_data.items():
        if hasattr(cfg, key):
            try:
                # TOML already parses types; just set directly
                setattr(cfg, key, raw_val)
            except Exception:  # noqa: BLE001
                pass

    # Layer 2: Env var overrides (highest priority)
    for env_key, attr in _ENV_MAP.items():
        raw = os.environ.get(env_key)
        if raw is not None and hasattr(cfg, attr):
            try:
                target_type = type(getattr(cfg, attr))
                setattr(cfg, attr, _coerce(raw, target_type))
            except (ValueError, TypeError):
                pass

    # Cache as singleton — no lock here; callers that need thread safety
    # (i.e. get_config) hold _config_lock around the entire load.
    global _config_singleton
    _config_singleton = cfg

    return cfg


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_config_singleton: SovereignConfig | None = None
_config_lock = threading.Lock()


def _build_config_unlocked(toml_path: Path | None = None) -> SovereignConfig:
    """Build a SovereignConfig without touching the singleton lock."""
    toml_path = toml_path or (_ROOT / "pradyos.toml")
    cfg = SovereignConfig()
    toml_data = _read_toml_section(toml_path, "sovereign")
    for key, raw_val in toml_data.items():
        if hasattr(cfg, key):
            try:
                setattr(cfg, key, raw_val)
            except Exception:
                pass
    for env_key, attr in _ENV_MAP.items():
        raw = os.environ.get(env_key)
        if raw is not None and hasattr(cfg, attr):
            try:
                target_type = type(getattr(cfg, attr))
                setattr(cfg, attr, _coerce(raw, target_type))
            except (ValueError, TypeError):
                pass
    return cfg


def get_config() -> SovereignConfig:
    """Return the cached SovereignConfig singleton, loading if needed."""
    global _config_singleton
    if _config_singleton is None:
        # Build config outside the lock to avoid re-entry deadlock
        # (load_config also sets _config_singleton directly)
        with _config_lock:
            if _config_singleton is None:
                # Temporarily clear so load_config can set it uncontested
                cfg = _build_config_unlocked()
                _config_singleton = cfg
    return _config_singleton  # type: ignore[return-value]


def reset_config_for_tests() -> None:
    """Clear singleton — tests only."""
    global _config_singleton
    with _config_lock:
        _config_singleton = None
