"""Tests for Phase 7F: sovereign/repl_ext.py"""

from __future__ import annotations

import os
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from pradyos.sovereign.repl_ext import ReplExtMixin


# ---------------------------------------------------------------------------
# Minimal concrete REPL that mixes in ReplExtMixin
# ---------------------------------------------------------------------------

import cmd


class _TestRepl(ReplExtMixin, cmd.Cmd):
    """Minimal REPL for testing the mixin without spinning up the full stack."""
    prompt = "> "


def _make_repl() -> _TestRepl:
    return _TestRepl()


# ---------------------------------------------------------------------------
# 1. Mixin is importable and ReplExtMixin exists
# ---------------------------------------------------------------------------

def test_repl_ext_mixin_importable():
    from pradyos.sovereign.repl_ext import ReplExtMixin
    assert ReplExtMixin is not None


# ---------------------------------------------------------------------------
# 2. Mixin commands are present on the mixed class
# ---------------------------------------------------------------------------

def test_mixin_commands_present():
    repl = _make_repl()
    for cmd_name in ("do_audit", "do_metrics", "do_config", "do_archive", "do_recommend"):
        assert hasattr(repl, cmd_name), f"Missing {cmd_name}"


# ---------------------------------------------------------------------------
# 3. do_audit — delegates to get_audit_log().tail(N)
# ---------------------------------------------------------------------------

def test_do_audit_tail_calls_tail():
    mock_log = MagicMock()
    mock_log.tail = MagicMock(return_value=[])

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.audit.get_audit_log", return_value=mock_log):
            repl = _make_repl()
            repl.do_audit("tail 5")

    mock_log.tail.assert_called_once_with(5)


def test_do_audit_default_n():
    mock_log = MagicMock()
    mock_log.tail = MagicMock(return_value=[])

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.audit.get_audit_log", return_value=mock_log):
            repl = _make_repl()
            repl.do_audit("")  # no args → default N=20

    mock_log.tail.assert_called_once_with(20)


# ---------------------------------------------------------------------------
# 4. do_metrics — delegates to get_registry().snapshot()
# ---------------------------------------------------------------------------

def test_do_metrics_calls_snapshot():
    mock_registry = MagicMock()
    mock_registry.snapshot = MagicMock(return_value={})

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.metrics.get_registry", return_value=mock_registry):
            repl = _make_repl()
            repl.do_metrics("snapshot")

    mock_registry.snapshot.assert_called_once()


# ---------------------------------------------------------------------------
# 5. do_config show — calls get_config(), doesn't crash on empty config
# ---------------------------------------------------------------------------

def test_do_config_show_runs():
    import dataclasses

    @dataclasses.dataclass
    class _FakeCfg:
        log_level: str = "INFO"
        max_campaign_workers: int = 4

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.config.get_config", return_value=_FakeCfg()):
            repl = _make_repl()
            repl.do_config("show")  # should not raise


# ---------------------------------------------------------------------------
# 6. do_config set — mutates os.environ with PRADYOS_ prefix
# ---------------------------------------------------------------------------

def test_do_config_set_mutates_env():
    import dataclasses

    @dataclasses.dataclass
    class _FakeCfg:
        log_level: str = "DEBUG"
        max_campaign_workers: int = 4

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.config.get_config", return_value=_FakeCfg()):
            with patch("pradyos.core.config.reset_config_for_tests"):
                repl = _make_repl()
                repl.do_config("set log_level WARNING")

    assert os.environ.get("PRADYOS_LOG_LEVEL") == "WARNING"
    # cleanup
    del os.environ["PRADYOS_LOG_LEVEL"]


# ---------------------------------------------------------------------------
# 7. do_recommend — calls SovereignAdvisor.recommend()
# ---------------------------------------------------------------------------

def test_do_recommend_calls_advisor():
    mock_advisor = MagicMock()
    mock_advisor.recommend = MagicMock(return_value=[])

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.audit.get_audit_log", return_value=MagicMock()):
            with patch("pradyos.core.metrics.get_registry", return_value=MagicMock()):
                with patch("pradyos.oracle.advisor.SovereignAdvisor", return_value=mock_advisor):
                    repl = _make_repl()
                    repl.do_recommend("3")

    mock_advisor.recommend.assert_called_once_with(n=3)


def test_do_recommend_default_n():
    mock_advisor = MagicMock()
    mock_advisor.recommend = MagicMock(return_value=[])

    with patch("pradyos.sovereign.repl_ext._console"):
        with patch("pradyos.core.audit.get_audit_log", return_value=MagicMock()):
            with patch("pradyos.core.metrics.get_registry", return_value=MagicMock()):
                with patch("pradyos.oracle.advisor.SovereignAdvisor", return_value=mock_advisor):
                    repl = _make_repl()
                    repl.do_recommend("")  # default → n=5

    mock_advisor.recommend.assert_called_once_with(n=5)


# ---------------------------------------------------------------------------
# 8. do_archive — gracefully handles missing archive file
# ---------------------------------------------------------------------------

def test_do_archive_missing_file(tmp_path):
    mock_archiver = MagicMock()
    mock_archiver._archive_dir = tmp_path  # empty dir → no archive files

    with patch("pradyos.sovereign.repl_ext._console") as mock_console:
        with patch("pradyos.campaign.archiver.CampaignArchiver", return_value=mock_archiver):
            repl = _make_repl()
            repl.do_archive("list 20991231")  # future date — file won't exist

    # Should print "No archive found" without crashing
    mock_console.print.assert_called()


# ---------------------------------------------------------------------------
# 9. SovereignRepl inherits ReplExtMixin
# ---------------------------------------------------------------------------

def test_sovereign_repl_inherits_mixin():
    from pradyos.sovereign.repl import SovereignRepl
    assert issubclass(SovereignRepl, ReplExtMixin)


# ---------------------------------------------------------------------------
# 10. ReplExtMixin help methods are present
# ---------------------------------------------------------------------------

def test_help_methods_present():
    repl = _make_repl()
    for help_name in ("help_audit", "help_metrics", "help_config", "help_archive", "help_recommend"):
        assert callable(getattr(repl, help_name, None)), f"Missing {help_name}"
