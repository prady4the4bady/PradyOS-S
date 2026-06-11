"""REPL Extension Mixin — Phase 7F.

Provides ReplExtMixin, a mixin class that adds five command groups to any
``cmd.Cmd``-derived REPL:

  do_audit    — ``audit tail [N=20]``   print last N audit events
  do_metrics  — ``metrics snapshot``    print all metrics
  do_config   — ``config show | set KEY VALUE``
  do_archive  — ``archive list [DATE]``
  do_recommend — calls SovereignAdvisor (duplicated for mixin completeness)

Update ``SovereignRepl`` to inherit from this mixin by importing and
mixing in at the class definition level (see __init__.py update notes).

Windows-safe: no subprocess, no AF_UNIX, all stdlib + rich.
"""

from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.table import Table

log = logging.getLogger("pradyos.sovereign.repl_ext")

__all__ = ["ReplExtMixin"]

_console = Console()


class ReplExtMixin:
    """Mixin providing extended REPL commands.

    Mix into a ``cmd.Cmd`` subclass *before* ``cmd.Cmd`` in the MRO::

        class SovereignRepl(ReplExtMixin, cmd.Cmd):
            ...
    """

    # ------------------------------------------------------------------
    # do_audit — audit tail [N=20]
    # ------------------------------------------------------------------

    def do_audit(self, arg: str) -> None:
        """Print last N audit events.

        Usage: audit tail [N=20]
        """
        parts = arg.strip().split()
        n = 20
        if parts and parts[0] == "tail":
            parts = parts[1:]
        if parts:
            try:
                n = int(parts[0])
            except ValueError:
                _console.print("[yellow]Usage: audit tail [N][/yellow]")
                return

        try:
            from pradyos.core.audit import get_audit_log

            audit_log = get_audit_log()
            # get_audit_log returns an AuditLog (records); we also try EventAuditLog
            events = audit_log.tail(n)

            if not events:
                _console.print("[dim]No audit events in memory.[/dim]")
                return

            table = Table(title=f"Audit Tail (last {n})", show_lines=False)
            table.add_column("Timestamp", style="dim", width=20)
            table.add_column("Category / Kind", style="cyan", width=14)
            table.add_column("Actor", style="green", width=16)
            table.add_column("Action / Summary", style="white")

            for ev in events:
                # Supports both AuditRecord and AuditEvent
                ts = getattr(ev, "timestamp", 0.0)
                ts_str = _fmt_ts(ts)

                if hasattr(ev, "category"):
                    # AuditEvent
                    category = str(getattr(ev, "category", "SYSTEM"))
                    actor = str(getattr(ev, "actor", "system"))
                    action = str(getattr(ev, "action", ""))
                else:
                    # AuditRecord
                    category = str(getattr(ev, "kind", "event"))
                    actor = str(getattr(ev, "agent_id", "system"))
                    action = str(getattr(ev, "summary", ""))

                table.add_row(ts_str, category, actor, action[:80])

            _console.print(table)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]audit error: {exc}[/red]")

    def help_audit(self) -> None:
        _console.print("  audit tail [N=20]  — print last N audit events")

    # ------------------------------------------------------------------
    # do_metrics — metrics snapshot
    # ------------------------------------------------------------------

    def do_metrics(self, arg: str) -> None:
        """Print all registered metrics.

        Usage: metrics snapshot
        """
        try:
            from pradyos.core.metrics import get_registry

            registry = get_registry()
            snapshot = registry.snapshot()

            if not snapshot:
                _console.print("[dim]No metrics registered.[/dim]")
                return

            table = Table(title="Metrics Snapshot", show_lines=False)
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="dim", width=10)
            table.add_column("Value", style="green", justify="right")
            table.add_column("Description", style="dim")

            for name, data in sorted(snapshot.items()):
                mtype = data.get("type", "?")
                desc = data.get("description", "")
                if mtype == "counter":
                    val = str(data.get("value", 0))
                elif mtype == "gauge":
                    val = str(data.get("value", 0))
                elif mtype == "histogram":
                    count = data.get("count", 0)
                    mean = data.get("mean")
                    val = f"count={count}" + (f" mean={mean:.3f}" if mean is not None else "")
                else:
                    val = str(data.get("value", "?"))

                table.add_row(name, mtype, val, desc[:50])

            _console.print(table)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]metrics error: {exc}[/red]")

    def help_metrics(self) -> None:
        _console.print("  metrics snapshot  — print all registered metrics")

    # ------------------------------------------------------------------
    # do_config — config show | config set KEY VALUE
    # ------------------------------------------------------------------

    def do_config(self, arg: str) -> None:
        """Show or set config values.

        Usage:
          config show
          config set KEY VALUE
        """
        parts = arg.strip().split(None, 2)
        if not parts or parts[0] == "show":
            self._config_show()
        elif parts[0] == "set":
            if len(parts) < 3:
                _console.print("[yellow]Usage: config set KEY VALUE[/yellow]")
                return
            self._config_set(parts[1], parts[2])
        else:
            _console.print(f"[yellow]Unknown config subcommand: {parts[0]}[/yellow]")

    def _config_show(self) -> None:
        try:
            import dataclasses

            from pradyos.core.config import get_config

            cfg = get_config()
            table = Table(title="Current Config", show_lines=False)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="green")

            for f in dataclasses.fields(cfg):
                table.add_row(f.name, str(getattr(cfg, f.name)))

            _console.print(table)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]config show error: {exc}[/red]")

    def _config_set(self, key: str, value: str) -> None:
        """Set KEY=VALUE in the environment (non-persistent)."""
        env_key = f"PRADYOS_{key.upper()}"
        os.environ[env_key] = value
        _console.print(f"[green]Set {env_key}={value!r} (env only, non-persistent)[/green]")

        # Trigger a reload so get_config() picks up the new env value
        try:
            from pradyos.core.config import get_config, reset_config_for_tests

            reset_config_for_tests()
            cfg = get_config()
            _console.print(f"[dim]Config reloaded. {key} → {getattr(cfg, key, '?')}[/dim]")
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[yellow]Config reload after set: {exc}[/yellow]")

    def help_config(self) -> None:
        _console.print(
            "  config show         — show current config values\n"
            "  config set KEY VAL  — set PRADYOS_KEY=VAL in env"
        )

    # ------------------------------------------------------------------
    # do_archive — archive list [DATE=today]
    # ------------------------------------------------------------------

    def do_archive(self, arg: str) -> None:
        """List archived campaigns for a date.

        Usage: archive list [DATE=today]
               DATE format: YYYYMMDD
        """
        import datetime

        parts = arg.strip().split()
        if not parts or parts[0] == "list":
            date_arg = parts[1] if len(parts) > 1 else None
        else:
            date_arg = parts[0]

        if date_arg is None:
            date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        else:
            date_str = date_arg

        try:
            import json

            from pradyos.campaign.archiver import CampaignArchiver

            archiver = CampaignArchiver()
            archive_file = archiver._archive_dir / f"campaigns_{date_str}.jsonl"

            if not archive_file.exists():
                _console.print(f"[dim]No archive found for {date_str}[/dim]")
                return

            table = Table(title=f"Archived Campaigns — {date_str}", show_lines=False)
            table.add_column("ID", style="dim", width=14)
            table.add_column("Name", style="white")
            table.add_column("Status", style="cyan", width=12)
            table.add_column("Finished", style="dim", width=12)

            count = 0
            with archive_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        cid = d.get("campaign_id", "?")[:12]
                        name = d.get("name", "?")
                        status = d.get("status", "?")
                        finished = d.get("finished_at", 0)
                        ts_str = _fmt_ts(finished) if finished else "?"
                        table.add_row(cid, name[:40], status, ts_str)
                        count += 1
                    except Exception:  # noqa: BLE001
                        continue

            if count == 0:
                _console.print(f"[dim]Archive file for {date_str} is empty.[/dim]")
            else:
                _console.print(table)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]archive error: {exc}[/red]")

    def help_archive(self) -> None:
        _console.print("  archive list [YYYYMMDD]  — list archived campaigns for a date")

    # ------------------------------------------------------------------
    # do_recommend (mixin version — delegates to SovereignAdvisor)
    # ------------------------------------------------------------------

    def do_recommend(self, arg: str) -> None:
        """Show Sovereign Advisor recommendations.

        Usage: recommend [N=5]
        """
        try:
            n = int(arg.strip()) if arg.strip() else 5
        except ValueError:
            n = 5
        try:
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
            table.add_column("Conf%", style="green", width=6)
            table.add_column("Suggested Goal", style="yellow")
            for r in recs:
                table.add_row(
                    str(r.rank),
                    r.title,
                    f"{r.confidence_pct:.0f}",
                    r.suggested_campaign_goal[:60],
                )
            _console.print(table)
        except Exception as exc:  # noqa: BLE001
            _console.print(f"[red]recommend error: {exc}[/red]")

    def help_recommend(self) -> None:
        _console.print("  recommend [N=5]  — show top N Sovereign Advisor recommendations")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_ts(ts: float) -> str:
    import datetime

    try:
        dt = datetime.datetime.fromtimestamp(float(ts), tz=datetime.timezone.utc)
        return dt.strftime("%H:%M:%S")
    except Exception:  # noqa: BLE001
        return str(ts)
