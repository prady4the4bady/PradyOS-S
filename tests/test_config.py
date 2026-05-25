"""Tests for Phase 6 SovereignConfig / load_config() / get_config().

Covers: defaults, env override, toml override, singleton caching.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from pradyos.core.config import (
    SovereignConfig,
    get_config,
    load_config,
    reset_config_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure singleton is cleared before and after each test."""
    reset_config_for_tests()
    yield
    reset_config_for_tests()


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_config_defaults(monkeypatch):
    # Strip all PRADYOS_ env vars to see pure defaults
    for key in list(os.environ):
        if key.startswith("PRADYOS_") or key == "SOVEREIGN_RETRY_MAX":
            monkeypatch.delenv(key, raising=False)
    cfg = load_config()
    assert isinstance(cfg, SovereignConfig)
    assert cfg.titan_port == 7331
    assert cfg.log_level == "INFO"
    assert cfg.max_campaign_workers == 4
    assert cfg.retry_max_attempts == 3
    assert "localhost" in cfg.oracle_url or "127.0.0.1" in cfg.oracle_url


# ---------------------------------------------------------------------------
# Env override
# ---------------------------------------------------------------------------


def test_config_env_override_titan_port(monkeypatch):
    monkeypatch.setenv("PRADYOS_TITAN_PORT", "9000")
    cfg = load_config()
    assert cfg.titan_port == 9000


def test_config_env_override_log_level(monkeypatch):
    monkeypatch.setenv("PRADYOS_LOG_LEVEL", "DEBUG")
    cfg = load_config()
    assert cfg.log_level == "DEBUG"


def test_config_env_override_max_workers(monkeypatch):
    monkeypatch.setenv("PRADYOS_MAX_CAMPAIGN_WORKERS", "8")
    cfg = load_config()
    assert cfg.max_campaign_workers == 8


def test_config_env_override_oracle_url(monkeypatch):
    monkeypatch.setenv("PRADYOS_ORACLE_URL", "http://llm.internal:4000")
    cfg = load_config()
    assert cfg.oracle_url == "http://llm.internal:4000"


def test_config_sovereign_retry_max_env(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_RETRY_MAX", "10")
    cfg = load_config()
    assert cfg.retry_max_attempts == 10


def test_config_state_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PRADYOS_STATE_PATH", str(tmp_path / "mystate"))
    cfg = load_config()
    assert "mystate" in cfg.state_dir


# ---------------------------------------------------------------------------
# TOML override
# ---------------------------------------------------------------------------


def test_config_toml_override(tmp_path, monkeypatch):
    # Strip env vars so TOML is the effective layer
    for key in list(os.environ):
        if key.startswith("PRADYOS_") or key == "SOVEREIGN_RETRY_MAX":
            monkeypatch.delenv(key, raising=False)

    toml_file = tmp_path / "pradyos.toml"
    toml_file.write_text(textwrap.dedent("""\
        [sovereign]
        titan_port = 8888
        log_level = "WARNING"
        max_campaign_workers = 16
        retry_max_attempts = 5
    """), encoding="utf-8")

    cfg = load_config(toml_path=toml_file)
    assert cfg.titan_port == 8888
    assert cfg.log_level == "WARNING"
    assert cfg.max_campaign_workers == 16
    assert cfg.retry_max_attempts == 5


def test_config_env_wins_over_toml(tmp_path, monkeypatch):
    toml_file = tmp_path / "pradyos.toml"
    toml_file.write_text("[sovereign]\ntitan_port = 8888\n", encoding="utf-8")
    monkeypatch.setenv("PRADYOS_TITAN_PORT", "9999")
    cfg = load_config(toml_path=toml_file)
    assert cfg.titan_port == 9999


def test_config_missing_toml_uses_defaults(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("PRADYOS_") or key == "SOVEREIGN_RETRY_MAX":
            monkeypatch.delenv(key, raising=False)
    cfg = load_config(toml_path=tmp_path / "nonexistent.toml")
    assert cfg.titan_port == 7331


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_config_returns_singleton(monkeypatch):
    monkeypatch.delenv("PRADYOS_TITAN_PORT", raising=False)
    c1 = get_config()
    c2 = get_config()
    assert c1 is c2


def test_load_config_replaces_singleton(monkeypatch):
    monkeypatch.setenv("PRADYOS_TITAN_PORT", "1111")
    c1 = load_config()
    monkeypatch.setenv("PRADYOS_TITAN_PORT", "2222")
    reset_config_for_tests()
    c2 = load_config()
    assert c1 is not c2
    assert c2.titan_port == 2222


def test_reset_config_clears_singleton():
    get_config()   # prime singleton
    reset_config_for_tests()
    # Importing module-level _config_singleton should be None now
    from pradyos.core import config as cfg_mod
    assert cfg_mod._config_singleton is None
