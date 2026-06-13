"""Rich renderables used by the Throne.

Kept separate so the app file stays a thin orchestrator and tests can
snapshot the renderables in isolation.
"""

from __future__ import annotations

import time
from typing import Any

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text


def _bar(label: str, pct: float, width: int = 28) -> Group:
    color = "green" if pct < 70 else "yellow" if pct < 90 else "red"
    bar = ProgressBar(
        total=100,
        completed=min(100, max(0, pct)),
        width=width,
        complete_style=color,
        finished_style=color,
    )
    return Group(Text(f"{label:<10} ", style="bold cyan"), bar, Text(f"  {pct:5.1f}%", style=color))


def health_panel(snap: dict[str, Any] | None) -> Panel:
    if snap is None:
        return Panel(
            "WARDEN GRID telemetry not yet available…", title="EMPIRE HEALTH", border_style="dim"
        )
    rows: list[Any] = []
    rows.append(_bar("CPU", float(snap.get("cpu_percent", 0))))
    rows.append(_bar("RAM", float(snap.get("ram_percent", 0))))
    rows.append(_bar("SWAP", float(snap.get("swap_percent", 0))))
    for d in snap.get("disk", [])[:3]:
        rows.append(_bar("DISK", float(d.get("percent", 0))))
    for g in snap.get("gpus", []):
        rows.append(_bar(f"GPU{g.get('index', 0)}", float(g.get("util_percent", 0))))

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="bold cyan")
    meta.add_column()
    meta.add_row("host", snap.get("hostname", "?"))
    meta.add_row("platform", snap.get("platform", "?"))
    uptime = float(snap.get("uptime_sec", 0))
    meta.add_row("uptime", _fmt_duration(uptime))
    meta.add_row("processes", str(snap.get("process_count", "?")))
    la = snap.get("load_average")
    if la:
        meta.add_row("load 1/5/15", " ".join(f"{x:.2f}" for x in la))

    body = Group(*rows, Text(""), meta)
    return Panel(body, title="EMPIRE HEALTH", border_style="cyan", box=box.HEAVY)


def queue_panel(stats: dict[str, Any], records: list[dict[str, Any]]) -> Panel:
    tbl = Table.grid(padding=(0, 1))
    tbl.add_column(style="bold")
    tbl.add_column(justify="right")
    tbl.add_row("Total", str(stats.get("total", 0)))
    tbl.add_row("Queued", str(stats.get("state.QUEUED", 0)))
    tbl.add_row("Running", str(stats.get("state.RUNNING", 0)))
    tbl.add_row("Succeeded", str(stats.get("state.SUCCEEDED", 0)))
    tbl.add_row("Failed", str(stats.get("state.FAILED", 0)))
    tbl.add_row("[yellow]Escalated[/yellow]", f"[yellow]{stats.get('state.ESCALATED', 0)}[/yellow]")

    recent = Table(show_header=True, header_style="bold magenta", box=box.MINIMAL_DOUBLE_HEAD)
    recent.add_column("task", style="dim", overflow="fold", max_width=14)
    recent.add_column("priority", style="cyan")
    recent.add_column("state", style="bold")
    recent.add_column("kind")
    recent.add_column("intent", overflow="fold")
    for r in records[:10]:
        state = r.get("state", "?")
        color = {
            "RUNNING": "yellow",
            "SUCCEEDED": "green",
            "FAILED": "red",
            "ESCALATED": "magenta",
            "QUEUED": "cyan",
            "CANCELLED": "dim",
        }.get(state, "white")
        recent.add_row(
            (r.get("task_id") or "")[:14],
            r.get("priority", ""),
            f"[{color}]{state}[/{color}]",
            r.get("kind", ""),
            r.get("intent", "") or "—",
        )

    return Panel(
        Group(tbl, Text(""), recent),
        title="IMPERIUM — TASK QUEUE",
        border_style="blue",
        box=box.HEAVY,
    )


def approvals_panel(approvals: list[dict[str, Any]]) -> Panel:
    if not approvals:
        return Panel(
            Text("No proposals awaiting Sovereign approval.", style="dim"),
            title="SOVEREIGN APPROVALS",
            border_style="green",
            box=box.HEAVY,
        )
    body = Table(show_header=True, header_style="bold yellow", box=box.MINIMAL)
    body.add_column("id", style="dim")
    body.add_column("kind")
    body.add_column("intent", overflow="fold")
    body.add_column("rule")
    body.add_column("reason", overflow="fold")
    for a in approvals:
        body.add_row(
            (a.get("task_id") or "")[:14],
            a.get("kind", ""),
            a.get("intent", "") or "—",
            a.get("escalation_rule", "") or "—",
            a.get("escalation_reason", "") or "—",
        )
    note = Text(
        "Approve via: throne.approve(<task_id>)   |   Reject: throne.reject(<task_id>)",
        style="dim italic",
    )
    return Panel(
        Group(body, Text(""), note),
        title="SOVEREIGN APPROVALS",
        border_style="yellow",
        box=box.HEAVY,
    )


def incidents_panel(incidents: list[dict[str, Any]]) -> Panel:
    if not incidents:
        return Panel(
            Text("All clear. WARDEN GRID reports no open incidents.", style="green"),
            title="WARDEN GRID — INCIDENTS",
            border_style="green",
            box=box.HEAVY,
        )
    tbl = Table(show_header=True, header_style="bold red", box=box.MINIMAL_DOUBLE_HEAD)
    tbl.add_column("sev")
    tbl.add_column("component")
    tbl.add_column("summary", overflow="fold")
    tbl.add_column("occ", justify="right")
    for i in incidents:
        sev = i.get("severity", "?")
        color = {"INFO": "cyan", "WARN": "yellow", "CRIT": "red", "FATAL": "bold red"}.get(
            sev, "white"
        )
        tbl.add_row(
            f"[{color}]{sev}[/{color}]",
            i.get("component", "?"),
            i.get("summary", ""),
            str(i.get("occurrences", 1)),
        )
    return Panel(tbl, title="WARDEN GRID — INCIDENTS", border_style="red", box=box.HEAVY)


def audit_panel(records: list[dict[str, Any]]) -> Panel:
    tbl = Table(show_header=True, header_style="bold cyan", box=box.MINIMAL)
    tbl.add_column("when", style="dim")
    tbl.add_column("agent")
    tbl.add_column("kind")
    tbl.add_column("exit", justify="right")
    tbl.add_column("summary", overflow="fold")
    for r in records[-10:]:
        ts = r.get("timestamp_iso") or _fmt_ts(r.get("timestamp", 0))
        ex = r.get("exit_code")
        ex_text = "—" if ex is None else str(ex)
        if isinstance(ex, int) and ex != 0:
            ex_text = f"[red]{ex}[/red]"
        tbl.add_row(ts, r.get("agent_id", "?"), r.get("kind", "?"), ex_text, r.get("summary", ""))
    return Panel(tbl, title="AUDIT TAIL — LAST 10 ACTIONS", border_style="magenta", box=box.HEAVY)


def forge_panel(
    queue: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    driver: dict[str, Any] | None,
) -> Panel:
    """ASCENT self-improvement review — the autonomous proposals awaiting the
    Sovereign's approve/reject, the driver heartbeat, and recent decisions."""
    if driver and driver.get("running"):
        beat = (
            f"[green]● live[/green]  ticks: [cyan]{driver.get('ticks', 0)}[/cyan]  "
            f"interval: [cyan]{driver.get('interval_s', '—')}s[/cyan]"
        )
    elif driver is not None:
        beat = "[yellow]○ idle[/yellow]"
    else:
        beat = "[dim]driver offline[/dim]"

    qtbl = Table(show_header=True, header_style="bold magenta", box=box.MINIMAL_DOUBLE_HEAD)
    qtbl.add_column("seq", style="dim", justify="right")
    qtbl.add_column("module", style="cyan", overflow="fold")
    qtbl.add_column("risk", justify="right")
    qtbl.add_column("directive", overflow="fold")
    if queue:
        for item in queue[:10]:
            rb = item.get("risk_before")
            ra = item.get("risk_after")
            risk = f"{rb}→{ra}" if rb is not None and ra is not None else str(rb or "—")
            qtbl.add_row(
                str(item.get("seq", "?")),
                item.get("module", "?"),
                risk,
                (item.get("directive") or "—")[:70],
            )
    else:
        qtbl.add_row("—", "[dim]no proposals awaiting review[/dim]", "—", "—")

    dtbl = Table(show_header=True, header_style="bold cyan", box=box.MINIMAL)
    dtbl.add_column("seq", style="dim", justify="right")
    dtbl.add_column("module", overflow="fold")
    dtbl.add_column("decision")
    dtbl.add_column("by")
    for d in decisions[-6:]:
        status = d.get("status", "?")
        color = {"approved": "green", "rejected": "red"}.get(status, "white")
        dtbl.add_row(
            str(d.get("seq", "?")),
            d.get("module", "?"),
            f"[{color}]{status}[/{color}]",
            d.get("by", "—"),
        )

    body = Group(
        Text.from_markup(f"heartbeat: {beat}"),
        Text(""),
        Text.from_markup(
            "[bold]Proposals awaiting Sovereign approval[/bold] — `ascent approve|reject <seq>`"
        ),
        qtbl,
        Text(""),
        Text.from_markup("[bold]Recent decisions[/bold]"),
        dtbl,
    )
    return Panel(body, title="ASCENT — SELF-FORGE", border_style="green", box=box.HEAVY)


def header_banner() -> Panel:
    text = Text()
    text.append("PRADY OS ", style="bold cyan")
    text.append("— SOVEREIGN EDITION", style="bold")
    text.append(
        "\nThe machine owns execution. The Sovereign owns strategic authorization.",
        style="italic dim",
    )
    return Panel(text, border_style="cyan", box=box.HEAVY)


def _fmt_duration(s: float) -> str:
    s = int(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _fmt_ts(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else "—"
