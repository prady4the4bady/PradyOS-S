"""Tests for pradyos.sovereign.repl — SovereignRepl.

All tests are self-contained: CLI functions are mocked, I/O uses StringIO.
"""

from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_repl_with_input(input_text: str):
    """Run the REPL with the given newline-separated commands, return output."""
    from pradyos.sovereign.repl import SovereignRepl

    stdin = io.StringIO(input_text)
    stdout = io.StringIO()

    repl = SovereignRepl(stdin=stdin, stdout=stdout)
    repl.intro = ""  # suppress intro for cleaner output capture
    repl.use_rawinput = False  # use readline() from stdin

    # Suppress rich Console output to stdout during tests
    with patch("pradyos.sovereign.repl._console") as mock_console:
        repl.cmdloop()

    return mock_console, stdout.getvalue()


# ---------------------------------------------------------------------------
# exit / quit / EOF
# ---------------------------------------------------------------------------


def test_exit_command_quits():
    from pradyos.sovereign.repl import SovereignRepl

    stdin = io.StringIO("exit\n")
    repl = SovereignRepl(stdin=stdin, stdout=io.StringIO())
    repl.use_rawinput = False
    repl.intro = ""

    with patch("pradyos.sovereign.repl._console"):
        result = repl.onecmd("exit")

    assert result is True


def test_quit_command_quits():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    repl.use_rawinput = False
    result = repl.do_quit("")
    assert result is True


def test_eof_quits():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    repl.use_rawinput = False
    with patch("pradyos.sovereign.repl._console"):
        result = repl.do_EOF("")
    assert result is True


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_delegates_to_cmd_status():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    repl.use_rawinput = False

    mock_fn = MagicMock()
    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_status", mock_fn):
        repl.do_status("")

    mock_fn.assert_called_once()


def test_status_handles_import_error_gracefully():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())

    def raise_import(*a, **kw):
        raise ImportError("cli unavailable")

    with patch("pradyos.sovereign.repl._console") as mc, \
         patch("pradyos.sovereign.cli.cmd_status", raise_import):
        repl.do_status("")

    mc.print.assert_called()


# ---------------------------------------------------------------------------
# campaigns
# ---------------------------------------------------------------------------


def test_campaigns_delegates_to_cmd_list_campaigns():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_list_campaigns", mock_fn):
        repl.do_campaigns("")

    mock_fn.assert_called_once()
    ns = mock_fn.call_args[0][0]
    assert ns.status is None


def test_campaigns_passes_status_filter():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_list_campaigns", mock_fn):
        repl.do_campaigns("running")

    ns = mock_fn.call_args[0][0]
    assert ns.status == "running"


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


def test_approve_delegates_with_task_id():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_approve", mock_fn):
        repl.do_approve("task-abc-123")

    mock_fn.assert_called_once()
    ns = mock_fn.call_args[0][0]
    assert ns.task_id == "task-abc-123"


def test_approve_empty_arg_shows_usage():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console") as mc, \
         patch("pradyos.sovereign.cli.cmd_approve", mock_fn):
        repl.do_approve("")

    mock_fn.assert_not_called()
    mc.print.assert_called()


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


def test_reject_delegates_with_task_id():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_reject", mock_fn):
        repl.do_reject("task-xyz")

    mock_fn.assert_called_once()
    ns = mock_fn.call_args[0][0]
    assert ns.task_id == "task-xyz"
    assert ns.reason == ""


def test_reject_passes_reason():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_reject", mock_fn):
        repl.do_reject("task-xyz out of scope")

    ns = mock_fn.call_args[0][0]
    assert ns.task_id == "task-xyz"
    assert ns.reason == "out of scope"


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------


def test_schedule_list_delegates():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_schedule", mock_fn):
        repl.do_schedule("list")

    mock_fn.assert_called_once()
    ns = mock_fn.call_args[0][0]
    assert ns.schedule_cmd == "list"


def test_schedule_add_delegates():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_schedule", mock_fn):
        repl.do_schedule("add 0 6 * * * Daily morning sync")

    mock_fn.assert_called_once()
    ns = mock_fn.call_args[0][0]
    assert ns.schedule_cmd == "add"
    assert ns.cron == "0"  # first positional after "add"


def test_schedule_remove_delegates():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console"), \
         patch("pradyos.sovereign.cli.cmd_schedule", mock_fn):
        repl.do_schedule("remove sched-001")

    mock_fn.assert_called_once()
    ns = mock_fn.call_args[0][0]
    assert ns.schedule_cmd == "remove"
    assert ns.schedule_id == "sched-001"


def test_schedule_empty_shows_usage():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console") as mc, \
         patch("pradyos.sovereign.cli.cmd_schedule", mock_fn):
        repl.do_schedule("")

    mock_fn.assert_not_called()
    mc.print.assert_called()


def test_schedule_unknown_subcommand():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())
    mock_fn = MagicMock()

    with patch("pradyos.sovereign.repl._console") as mc, \
         patch("pradyos.sovereign.cli.cmd_schedule", mock_fn):
        repl.do_schedule("frobnicate")

    mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


def test_help_lists_commands():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())

    with patch("pradyos.sovereign.repl._console") as mc:
        repl.do_help("")

    # console.print should be called multiple times listing commands
    assert mc.print.call_count >= 3


# ---------------------------------------------------------------------------
# unknown command
# ---------------------------------------------------------------------------


def test_unknown_command_shows_message():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())

    with patch("pradyos.sovereign.repl._console") as mc:
        repl.default("frobulate")

    mc.print.assert_called()
    printed = str(mc.print.call_args_list)
    assert "frobulate" in printed or "Unknown" in printed


# ---------------------------------------------------------------------------
# empty line
# ---------------------------------------------------------------------------


def test_empty_line_does_nothing():
    from pradyos.sovereign.repl import SovereignRepl

    repl = SovereignRepl(stdin=io.StringIO(), stdout=io.StringIO())

    with patch("pradyos.sovereign.repl._console") as mc:
        repl.emptyline()

    mc.print.assert_not_called()


# ---------------------------------------------------------------------------
# run() via cmdloop with sequence of commands
# ---------------------------------------------------------------------------


def test_full_session_exits_cleanly():
    from pradyos.sovereign.repl import SovereignRepl

    commands = "exit\n"
    stdin = io.StringIO(commands)
    repl = SovereignRepl(stdin=stdin, stdout=io.StringIO())
    repl.use_rawinput = False
    repl.intro = ""

    with patch("pradyos.sovereign.repl._console"):
        repl.cmdloop()  # must not raise
