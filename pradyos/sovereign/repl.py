"""Sovereign REPL — interactive command loop for PRADY OS.

Wraps the sovereign CLI commands behind a ``cmd.Cmd`` loop so the operator
can issue repeated commands without re-invoking the CLI binary.

Entry point: ``pradyos-repl``

Windows-safe: cmd.Cmd uses sys.stdin/stdout, no AF_UNIX, no fork.
"""

from __future__ import annotations

import cmd
import shlex
import types

from rich.console import Console

from pradyos.sovereign.repl_ext import ReplExtMixin

_console = Console()


class SovereignRepl(ReplExtMixin, cmd.Cmd):
    """Interactive REPL for PRADY OS Sovereign.

    Delegates every command to the corresponding function in
    ``pradyos.sovereign.cli``.
    """

    intro = (
        "\n[bold cyan]⚡ PRADY OS — SOVEREIGN REPL[/bold cyan]\n"
        "Type [bold]help[/bold] for available commands, "
        "[bold]exit[/bold] to quit.\n"
    )
    prompt = "sovereign> "

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _print_markup(self, markup: str) -> None:
        _console.print(markup)

    def _cli_args(self, argv: list[str]) -> types.SimpleNamespace:
        """Build a minimal argparse.Namespace from a list of argv strings."""
        import argparse

        ns = argparse.Namespace(
            **{
                k: None
                for k in [
                    "task_id",
                    "reason",
                    "approver",
                    "campaign_id",
                    "status",
                    "schedule_cmd",
                    "name",
                    "cron",
                    "intent",
                    "tasks",
                    "schedule_id",
                ]
            }
        )
        return ns

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def preloop(self) -> None:
        if self.intro:
            _console.print(self.intro)
        self.intro = ""  # suppress cmd.Cmd's default print

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def do_status(self, _arg: str) -> None:
        """Show live PRADY OS system state."""
        try:
            import argparse

            from pradyos.sovereign.cli import cmd_status

            cmd_status(argparse.Namespace())
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]status error: {exc}[/red]")

    def help_status(self) -> None:
        _console.print("  status — display live system state (tasks, warden, campaigns)")

    # ------------------------------------------------------------------ #

    def do_campaigns(self, arg: str) -> None:
        """List campaigns, optionally filtered by status.

        Usage: campaigns [status_filter]
        """
        try:
            import argparse

            from pradyos.sovereign.cli import cmd_list_campaigns

            ns = argparse.Namespace(status=arg.strip() or None)
            cmd_list_campaigns(ns)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]campaigns error: {exc}[/red]")

    def help_campaigns(self) -> None:
        _console.print("  campaigns [status]  — list campaigns (optional status filter)")

    # ------------------------------------------------------------------ #

    def do_approve(self, arg: str) -> None:
        """Approve an escalated task.

        Usage: approve <task_id>
        """
        task_id = arg.strip()
        if not task_id:
            _console.print("[yellow]Usage: approve <task_id>[/yellow]")
            return
        try:
            import argparse

            from pradyos.sovereign.cli import cmd_approve

            ns = argparse.Namespace(task_id=task_id, approver="sovereign")
            cmd_approve(ns)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]approve error: {exc}[/red]")

    def help_approve(self) -> None:
        _console.print("  approve <task_id>  — approve an escalated task")

    # ------------------------------------------------------------------ #

    def do_reject(self, arg: str) -> None:
        """Reject an escalated task.

        Usage: reject <task_id> [reason...]
        """
        parts = arg.strip().split(None, 1)
        if not parts:
            _console.print("[yellow]Usage: reject <task_id> [reason][/yellow]")
            return
        task_id = parts[0]
        reason = parts[1] if len(parts) > 1 else ""
        try:
            import argparse

            from pradyos.sovereign.cli import cmd_reject

            ns = argparse.Namespace(task_id=task_id, reason=reason, approver="sovereign")
            cmd_reject(ns)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]reject error: {exc}[/red]")

    def help_reject(self) -> None:
        _console.print("  reject <task_id> [reason]  — reject an escalated task")

    # ------------------------------------------------------------------ #

    def do_schedule(self, arg: str) -> None:
        """Manage cron schedules.

        Usage:
          schedule list
          schedule add <cron> <intent>
          schedule remove <schedule_id>
        """
        import argparse

        parts = shlex.split(arg) if arg.strip() else []
        if not parts:
            _console.print(
                "[yellow]Usage: schedule list | add <cron> <intent> | remove <id>[/yellow]"
            )
            return

        sub = parts[0]
        try:
            from pradyos.sovereign.cli import cmd_schedule
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]schedule error: {exc}[/red]")
            return

        try:
            if sub == "list":
                ns = argparse.Namespace(schedule_cmd="list")
                cmd_schedule(ns)

            elif sub == "add":
                if len(parts) < 3:
                    _console.print("[yellow]Usage: schedule add <cron> <intent>[/yellow]")
                    return
                # First arg is cron (may be quoted e.g. "0 6 * * *"), rest is intent
                cron = parts[1]
                intent = " ".join(parts[2:])
                ns = argparse.Namespace(
                    schedule_cmd="add",
                    name=f"repl-schedule-{cron}",
                    cron=cron,
                    intent=intent,
                    tasks=None,
                )
                cmd_schedule(ns)

            elif sub == "remove":
                if len(parts) < 2:
                    _console.print("[yellow]Usage: schedule remove <schedule_id>[/yellow]")
                    return
                ns = argparse.Namespace(schedule_cmd="remove", schedule_id=parts[1])
                cmd_schedule(ns)

            else:
                _console.print(f"[yellow]Unknown schedule subcommand: {sub}[/yellow]")

        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]schedule error: {exc}[/red]")

    def help_schedule(self) -> None:
        _console.print(
            "  schedule list                    — list cron schedules\n"
            "  schedule add <cron> <intent>     — add a schedule\n"
            "  schedule remove <schedule_id>    — remove a schedule"
        )

    # ------------------------------------------------------------------ #

    def do_recommend(self, arg: str) -> None:
        """Show Sovereign Advisor recommendations.

        Usage: recommend [N=5]
        """
        try:
            n = int(arg.strip()) if arg.strip() else 5
        except ValueError:
            n = 5
        try:
            from rich.table import Table

            from pradyos.core.audit import get_audit_log
            from pradyos.core.metrics import get_registry
            from pradyos.oracle.advisor import SovereignAdvisor

            advisor = SovereignAdvisor(
                audit_log=get_audit_log(),
                metrics_registry=get_registry(),
            )
            recs = advisor.recommend(n=n)
            if not recs:
                _console.print("[dim]No recommendations available.[/dim]")
                return
            table = Table(title="Sovereign Advisor Recommendations", show_lines=True)
            table.add_column("#", style="cyan", width=3)
            table.add_column("Title", style="bold white")
            table.add_column("Confidence", style="green", width=10)
            table.add_column("Suggested Goal", style="yellow")
            for r in recs:
                table.add_row(
                    str(r.rank),
                    r.title,
                    f"{r.confidence_pct:.0f}%",
                    r.suggested_campaign_goal,
                )
            _console.print(table)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]recommend error: {exc}[/red]")

    def help_recommend(self) -> None:
        _console.print("  recommend [N]  — show top N Sovereign Advisor recommendations")

    # ------------------------------------------------------------------ #

    def do_exit(self, _arg: str) -> bool:
        """Exit the REPL."""
        _console.print("[dim]Goodbye.[/dim]")
        return True

    def do_quit(self, _arg: str) -> bool:
        """Exit the REPL."""
        return self.do_exit(_arg)

    def do_EOF(self, _arg: str) -> bool:  # noqa: N802
        """Exit on Ctrl-D / EOF."""
        _console.print("")
        return self.do_exit(_arg)

    # ------------------------------------------------------------------

    def default(self, line: str) -> None:
        _console.print(
            f"[yellow]Unknown command: '{line.split()[0] if line.split() else line}'. "
            f"Type 'help' for available commands.[/yellow]"
        )

    def emptyline(self) -> None:
        pass  # do nothing on empty input

    def do_help(self, arg: str) -> None:
        if arg:
            super().do_help(arg)
            return
        _console.print("\n[bold]Available commands:[/bold]")
        _console.print("  [cyan]status[/cyan]               \u2014 show live system state")
        _console.print("  [cyan]campaigns[/cyan] [status]   \u2014 list campaigns")
        _console.print("  [cyan]approve[/cyan] <task_id>    \u2014 approve escalated task")
        _console.print("  [cyan]reject[/cyan] <task_id>     \u2014 reject escalated task")
        _console.print("  [cyan]schedule[/cyan] list|add|remove \u2014 manage schedules")
        _console.print("  [cyan]recommend[/cyan] [N]        \u2014 show advisor recommendations")
        _console.print("  [cyan]audit[/cyan] tail [N]       \u2014 show last N audit events")
        _console.print("  [cyan]metrics[/cyan] snapshot     \u2014 show all metrics")
        _console.print("  [cyan]config[/cyan] show|set      \u2014 view or change config")
        _console.print("  [cyan]help[/cyan]                 \u2014 show this message")
        _console.print("  [cyan]exit[/cyan] / [cyan]quit[/cyan]        \u2014 exit REPL\n")

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the interactive REPL loop."""
        try:
            self.cmdloop()
        except KeyboardInterrupt:
            _console.print("\n[dim]Interrupted.[/dim]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: pradyos-repl."""
    repl = SovereignRepl()
    repl.run()


if __name__ == "__main__":
    main()
