"""AURORA THRONE — Full Textual cinematic UI (§13.2).

Five sovereign views navigable via keyboard 1-5 or tab:

    1 / F1  →  Morning Brief        — WARDEN health + overnight audit summary
    2 / F2  →  Project Dossiers     — all IMPERIUM tasks with status/kind/intent
    3 / F3  →  Campaign View        — running tasks with live progress + approvals
    4 / F4  →  Empire Health        — CPU/RAM/Disk/GPU panels from WARDEN GRID
    5 / F5  →  Artifact Gallery     — audit log tail with agent_id filtering

Keyboard (hidden-CLI doctrine — no raw shell ever exposed):
    1-5 / F1-F5  →  switch view
    c            →  open command bar (approve / reject by task ID prefix)
    ESC          →  close command bar
    q            →  quit

Backward-compatible ``Throne`` class is preserved for embedded use and tests:
    ``throne.run(once=True)``  renders one Rich snapshot and returns
    ``throne.run()``           launches the full ThroneApp
    ``throne.approve(id)``     proxies to IMPERIUM
    ``throne.reject(id)``      proxies to IMPERIUM
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Rich imports (for once=True / test-mode Throne shim)
# ---------------------------------------------------------------------------
from rich.console import Console
from rich.layout import Layout

# ---------------------------------------------------------------------------
# Textual imports
# ---------------------------------------------------------------------------
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from pradyos.aurora_throne.widgets import (
    approvals_panel,
    audit_panel,
    header_banner,
    health_panel,
    incidents_panel,
    queue_panel,
)
from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.imperium.checkpoint import CheckpointStore

log = logging.getLogger("pradyos.aurora_throne")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

CYAN = "bright_cyan"
AMBER = "yellow"
CRIMSON = "bright_red"
GREEN = "bright_green"
DIM = "grey50"
MAGENTA = "bright_magenta"

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

THRONE_CSS = """
Screen {
    background: #0a0e14;
    color: #c5cdd9;
}

ThroneHeader {
    height: 3;
    background: #0d1117;
    border-bottom: solid #00b4d8;
    color: #00b4d8;
    content-align: center middle;
    text-style: bold;
}

MetricBar {
    height: 3;
    margin-bottom: 1;
}

MetricBar > Label {
    width: 12;
    color: #00b4d8;
    text-style: bold;
}

MetricBar > ProgressBar {
    width: 1fr;
}

MetricBar > .pct-label {
    width: 7;
    text-align: right;
    color: #c5cdd9;
}

PanelBox {
    border: solid #1a2634;
    padding: 0 1;
    margin: 0 1 1 0;
}

PanelBox.-warn { border: solid #d4a017; }
PanelBox.-crit { border: solid #c62828; }
PanelBox.-ok   { border: solid #00897b; }

.panel-title {
    color: #00b4d8;
    text-style: bold;
    padding: 0 1;
    background: #0d1117;
}

.dim       { color: #4a5568; }
.ok        { color: #00897b; }
.warn      { color: #d4a017; }
.crit      { color: #c62828; }
.running   { color: #f39c12; }
.queued    { color: #00b4d8; }
.succeeded { color: #00897b; }
.failed    { color: #c62828; }
.escalated { color: #9b59b6; text-style: bold; }

ApprovalCard {
    height: auto;
    border: solid #9b59b6;
    margin: 0 0 1 0;
    padding: 0 1;
    background: #120a1e;
}

ApprovalCard > .card-header { text-style: bold; color: #9b59b6; }
ApprovalCard > .card-body   { color: #c5cdd9; }
ApprovalCard > Horizontal   { height: 3; margin-top: 1; }
ApprovalCard Button         { margin-right: 1; }

CommandBar {
    height: 3;
    background: #0d1117;
    border-top: solid #1a2634;
    padding: 0 1;
}

CommandBar Label {
    color: #00b4d8;
    width: auto;
    margin-right: 1;
}

CommandBar Input {
    width: 1fr;
    background: #0a0e14;
    border: solid #1a2634;
    color: #c5cdd9;
}

#campaign-pane         { layout: horizontal; }
#campaign-tasks        { width: 60%; border-right: solid #1a2634; }
#campaign-approvals    { width: 40%; padding: 0 1; }

DataTable { background: #0a0e14; color: #c5cdd9; }
DataTable > .datatable--header { background: #0d1117; color: #00b4d8; text-style: bold; }
DataTable > .datatable--cursor { background: #1a2634; }

#gallery-log {
    height: 1fr;
    background: #060a0f;
    border: solid #1a2634;
}
"""

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _warden_get(url: str, path: str, timeout: float = 1.5) -> dict[str, Any] | None:
    full = f"{url.rstrip('/')}{path}"
    try:
        with urllib.request.urlopen(full, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


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


def _state_color(state: str) -> str:
    return {
        "RUNNING": "running",
        "QUEUED": "queued",
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "ESCALATED": "escalated",
        "CANCELLED": "dim",
    }.get(state, "")


def _sev_color(sev: str) -> str:
    return {"INFO": "ok", "WARN": "warn", "CRIT": "crit", "FATAL": "crit"}.get(sev, "")


# ---------------------------------------------------------------------------
# Textual custom widgets
# ---------------------------------------------------------------------------


class ThroneHeader(Widget):
    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="hdr-text")

    def on_mount(self) -> None:
        self.set_interval(1, self._tick)
        self._tick()

    def _tick(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        try:
            self.query_one("#hdr-text", Static).update(
                f"[bold bright_cyan]PRADY OS — SOVEREIGN EDITION[/bold bright_cyan]"
                f"  [grey50]|[/grey50]  [white]{now}[/white]"
                f"  [grey50]|[/grey50]  [grey50]The machine owns execution.[/grey50]"
            )
        except NoMatches:
            pass


class MetricBar(Widget):
    """A labelled progress bar for a numeric percentage metric."""

    def __init__(self, label: str, pct: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._pct = min(100.0, max(0.0, pct))

    def compose(self) -> ComposeResult:
        yield Label(self._label)
        bar = ProgressBar(total=100, show_percentage=False, show_eta=False)
        bar.advance(self._pct)
        yield bar
        yield Label(f"{self._pct:5.1f}%", classes="pct-label")


class PanelBox(Container):
    """A titled bordered container."""

    def __init__(self, title: str, *args: Any, modifier: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._title = title
        if modifier:
            self.add_class(modifier)

    def compose(self) -> ComposeResult:
        yield Static(f" {self._title} ", classes="panel-title")


class ApprovalCard(Widget):
    """Interactive card for an escalated task awaiting Sovereign approval."""

    def __init__(self, record: dict[str, Any], imperium: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rec = record
        self._imperium = imperium

    def compose(self) -> ComposeResult:
        tid = self._rec.get("task_id", "?")[:16]
        kind = self._rec.get("kind", "?")
        intent = self._rec.get("intent") or "—"
        rule = self._rec.get("escalation_rule") or "—"
        reason = self._rec.get("escalation_reason") or "—"
        yield Static(
            f"[bold magenta]APPROVAL REQUIRED[/bold magenta]  [{tid}]", classes="card-header"
        )
        yield Static(f"[dim]kind:[/dim] {kind}   [dim]rule:[/dim] {rule}", classes="card-body")
        yield Static(f"[dim]intent:[/dim] {intent}", classes="card-body")
        yield Static(f"[dim]reason:[/dim] {reason}", classes="card-body")
        with Horizontal():
            yield Button("✓ Approve", id=f"approve-{tid}", variant="success")
            yield Button("✗ Reject", id=f"reject-{tid}", variant="error")

    @on(Button.Pressed)
    def _on_button(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        rec_tid = self._rec.get("task_id", "")
        if btn_id.startswith("approve-") and self._imperium:
            self._imperium.approve(rec_tid, approver="sovereign")
            self.remove()
        elif btn_id.startswith("reject-") and self._imperium:
            self._imperium.reject(rec_tid, approver="sovereign", reason="rejected via Throne")
            self.remove()


class CommandBar(Widget):
    """Sovereign command input — approve/reject by task ID prefix."""

    def __init__(self, throne: ThroneApp) -> None:
        super().__init__()
        self._throne = throne

    def compose(self) -> ComposeResult:
        yield Label("⌘")
        yield Input(placeholder="a <task_id>  |  r <task_id>  |  q", id="cmd-input")

    def on_mount(self) -> None:
        self.query_one("#cmd-input", Input).focus()

    @on(Input.Submitted)
    def _execute(self, event: Input.Submitted) -> None:
        raw = (event.value or "").strip()
        event.input.clear()
        if raw:
            self._throne.execute_command(raw)


# ---------------------------------------------------------------------------
# View panes
# ---------------------------------------------------------------------------


class MorningBriefPane(TabPane):
    """View 1 — WARDEN health + overnight audit summary."""

    def __init__(self, throne: ThroneApp) -> None:
        super().__init__("Morning Brief", id="pane-morning")
        self._throne = throne

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="brief-greeting")
            with Horizontal():
                with Vertical(id="brief-left"):
                    yield Static("[bold cyan]SYSTEM STATUS[/bold cyan]", classes="panel-title")
                    yield Static(id="brief-health")
                with Vertical(id="brief-right"):
                    yield Static("[bold yellow]OPEN INCIDENTS[/bold yellow]", classes="panel-title")
                    yield Static(id="brief-incidents")
            with Vertical():
                yield Static(
                    "[bold magenta]PENDING APPROVALS[/bold magenta]", classes="panel-title"
                )
                yield Static(id="brief-approvals")
            with Vertical():
                yield Static("[bold cyan]RECENT AUDIT[/bold cyan]", classes="panel-title")
                yield Static(id="brief-audit")

    def refresh_data(
        self,
        snap: dict | None,
        incidents: list,
        stats: dict,
        approvals: list,
        audit: list,
    ) -> None:
        hour = datetime.now().hour
        greeting = (
            "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        )
        _upd(
            self,
            "#brief-greeting",
            Static,
            f"[bold bright_cyan]{greeting}, Sovereign.[/bold bright_cyan]  "
            f"[grey50]Empire integrity check — {datetime.now().strftime('%Y-%m-%d')}[/grey50]",
        )

        if snap:
            cpu = snap.get("cpu_percent", 0)
            ram = snap.get("ram_percent", 0)
            disk_pct = snap.get("disk", [{}])[0].get("percent", 0) if snap.get("disk") else 0

            def _c(v: float) -> str:
                return "crit" if v >= 90 else "warn" if v >= 70 else "ok"

            health_txt = (
                f"[{_c(cpu)}]CPU {cpu:.1f}%[/{_c(cpu)}]   "
                f"[{_c(ram)}]RAM {ram:.1f}%[/{_c(ram)}]   "
                f"[{_c(disk_pct)}]DISK {disk_pct:.1f}%[/{_c(disk_pct)}]"
            )
        else:
            health_txt = "[dim]WARDEN GRID offline — no telemetry[/dim]"
        _upd(self, "#brief-health", Static, health_txt)

        if incidents:
            lines = []
            for inc in incidents[:6]:
                sev = inc.get("severity", "?")
                color = _sev_color(sev)
                lines.append(
                    f"[{color}]{sev}[/{color}] {inc.get('component','?')} — {inc.get('summary','?')}"
                )
            inc_txt = "\n".join(lines)
        else:
            inc_txt = "[green]All clear — no open incidents[/green]"
        _upd(self, "#brief-incidents", Static, inc_txt)

        ap_count = len(approvals)
        ap_txt = (
            f"[magenta]{ap_count} task(s) awaiting Sovereign approval — switch to Campaign View (3)[/magenta]"
            if ap_count
            else "[green]No approvals pending[/green]"
        )
        _upd(self, "#brief-approvals", Static, ap_txt)

        if audit:
            lines = []
            for r in audit[-6:]:
                ts = r.get("timestamp_iso", "")[-8:] or "—"
                agent = r.get("agent_id", "?")
                summary = (r.get("summary") or "")[:80]
                ec = r.get("exit_code")
                ec_fmt = f"[red]{ec}[/red] " if isinstance(ec, int) and ec not in (0, None) else ""
                lines.append(f"[dim]{ts}[/dim] [cyan]{agent}[/cyan] {ec_fmt}{summary}")
            audit_txt = "\n".join(lines)
        else:
            audit_txt = "[dim]Audit ledger empty[/dim]"
        _upd(self, "#brief-audit", Static, audit_txt)


class ProjectDossiersPane(TabPane):
    """View 2 — all IMPERIUM tasks with status, kind, intent."""

    def __init__(self, throne: ThroneApp) -> None:
        super().__init__("Project Dossiers", id="pane-dossiers")
        self._throne = throne
        self._ready = False

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]PROJECT DOSSIERS — IMPERIUM TASK LEDGER[/bold cyan]", classes="panel-title"
        )
        tbl = DataTable(id="dossiers-table", cursor_type="row")
        tbl.add_columns("task_id", "priority", "state", "kind", "intent", "attempts", "age")
        yield tbl

    def on_mount(self) -> None:
        self._ready = True

    def refresh_data(self, records: list[dict]) -> None:
        if not self._ready:
            return
        try:
            tbl = self.query_one("#dossiers-table", DataTable)
        except NoMatches:
            return
        tbl.clear()
        now = time.time()
        for r in records:
            state = r.get("state", "?")
            sc = _state_color(state)
            age = now - float(r.get("queued_at") or now)
            tbl.add_row(
                (r.get("task_id") or "")[:16],
                r.get("priority", ""),
                f"[{sc}]{state}[/{sc}]" if sc else state,
                r.get("kind", ""),
                (r.get("intent") or "—")[:60],
                str(r.get("attempts", 0)),
                _fmt_duration(age),
                key=r.get("task_id"),
            )


class CampaignViewPane(TabPane):
    """View 3 — running tasks with live progress + sovereign approval interface."""

    def __init__(self, throne: ThroneApp) -> None:
        super().__init__("Campaign View", id="pane-campaign")
        self._throne = throne
        self._ready = False
        self._last_approval_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        with Horizontal(id="campaign-pane"):
            with Vertical(id="campaign-tasks"):
                yield Static("[bold yellow]ACTIVE OPERATIONS[/bold yellow]", classes="panel-title")
                tbl = DataTable(id="campaign-table", cursor_type="row")
                tbl.add_columns("id", "state", "kind", "intent", "dur")
                yield tbl
            with ScrollableContainer(id="campaign-approvals"):
                yield Static("[bold magenta]APPROVAL QUEUE[/bold magenta]", classes="panel-title")
                yield Static("[dim]No escalated tasks[/dim]", id="no-approvals-msg")

    def on_mount(self) -> None:
        self._ready = True

    def refresh_data(self, records: list[dict], approvals: list[dict]) -> None:
        if not self._ready:
            return
        try:
            tbl = self.query_one("#campaign-table", DataTable)
            tbl.clear()
            active_states = {"RUNNING", "QUEUED", "ESCALATED"}
            now = time.time()
            for r in records:
                if r.get("state") not in active_states:
                    continue
                state = r.get("state", "?")
                sc = _state_color(state)
                started = float(r.get("started_at") or 0)
                dur = _fmt_duration(now - started) if started else "—"
                tbl.add_row(
                    (r.get("task_id") or "")[:14],
                    f"[{sc}]{state}[/{sc}]" if sc else state,
                    r.get("kind", ""),
                    (r.get("intent") or "—")[:50],
                    dur,
                    key=r.get("task_id"),
                )
        except NoMatches:
            pass

        new_ids = {a.get("task_id", "") for a in approvals}
        if new_ids == self._last_approval_ids:
            return
        self._last_approval_ids = new_ids
        try:
            container = self.query_one("#campaign-approvals")
            for card in list(container.query(ApprovalCard)):
                card.remove()
            msg = container.query_one("#no-approvals-msg", Static)
        except NoMatches:
            return
        if not approvals:
            msg.display = True
            msg.update("[dim]No escalated tasks awaiting approval[/dim]")
        else:
            msg.display = False
            for a in approvals:
                container.mount(ApprovalCard(a, self._throne._imperium))


class EmpireHealthPane(TabPane):
    """View 4 — CPU/RAM/Disk/GPU panels from WARDEN GRID."""

    def __init__(self, throne: ThroneApp) -> None:
        super().__init__("Empire Health", id="pane-health")
        self._throne = throne

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                "[bold cyan]EMPIRE HEALTH — WARDEN GRID TELEMETRY[/bold cyan]",
                classes="panel-title",
            )
            yield Static(id="health-meta")
            with Vertical(id="health-bars"):
                yield Static("[dim]Awaiting telemetry…[/dim]", id="health-placeholder")
            yield Static("[bold red]OPEN INCIDENTS[/bold red]", classes="panel-title")
            tbl = DataTable(id="health-incidents", cursor_type="row")
            tbl.add_columns("sev", "component", "summary", "occurrences", "first_seen")
            yield tbl

    def refresh_data(self, snap: dict | None, incidents: list[dict]) -> None:
        if snap:
            uptime = _fmt_duration(float(snap.get("uptime_sec", 0)))
            la_raw = snap.get("load_average")
            la = " / ".join(f"{x:.2f}" for x in la_raw) if la_raw else "—"
            meta_txt = (
                f"[bold]{snap.get('hostname','?')}[/bold]  "
                f"[dim]{snap.get('platform','?')}[/dim]  "
                f"uptime: [cyan]{uptime}[/cyan]  "
                f"processes: [cyan]{snap.get('process_count','?')}[/cyan]  "
                f"load: [cyan]{la}[/cyan]"
            )
        else:
            meta_txt = "[dim]WARDEN GRID offline[/dim]"
        _upd(self, "#health-meta", Static, meta_txt)

        try:
            bars_container = self.query_one("#health-bars")
            for mb in list(bars_container.query(MetricBar)):
                mb.remove()
            placeholder = bars_container.query_one("#health-placeholder", Static)
            if snap:
                placeholder.display = False
                metrics: list[tuple[str, float]] = [
                    ("CPU", float(snap.get("cpu_percent", 0))),
                    ("RAM", float(snap.get("ram_percent", 0))),
                    ("SWAP", float(snap.get("swap_percent", 0))),
                ]
                for d in snap.get("disk", [])[:4]:
                    mount = d.get("mount", "?")
                    metrics.append((f"DSK {mount[:6]}", float(d.get("percent", 0))))
                for g in snap.get("gpus", [])[:2]:
                    metrics.append((f"GPU{g.get('index',0)}", float(g.get("util_percent", 0))))
                for label, pct in metrics:
                    bars_container.mount(MetricBar(label, pct))
            else:
                placeholder.display = True
        except NoMatches:
            pass

        try:
            tbl = self.query_one("#health-incidents", DataTable)
            tbl.clear()
            for inc in incidents:
                sev = inc.get("severity", "?")
                color = _sev_color(sev)
                first = inc.get("first_seen_iso") or inc.get("first_seen") or "—"
                if isinstance(first, float):
                    first = time.strftime("%H:%M:%S", time.localtime(first))
                tbl.add_row(
                    f"[{color}]{sev}[/{color}]" if color else sev,
                    inc.get("component", "?"),
                    (inc.get("summary") or "—")[:70],
                    str(inc.get("occurrences", 1)),
                    str(first)[-8:],
                )
        except NoMatches:
            pass


class ArtifactGalleryPane(TabPane):
    """View 5 — audit log tail with filtering by agent_id + DLQ + completed tasks."""

    def __init__(self, throne: ThroneApp) -> None:
        super().__init__("Artifact Gallery", id="pane-gallery")
        self._throne = throne
        self._ready = False
        self._filter_agent: str = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                with Vertical():
                    yield Static("[bold red]DEAD LETTER QUEUE[/bold red]", classes="panel-title")
                    tbl_dlq = DataTable(id="gallery-dlq", cursor_type="row")
                    tbl_dlq.add_columns("task_id", "intent", "attempts", "final_error", "failed_at")
                    yield tbl_dlq
                with Vertical():
                    yield Static(
                        "[bold yellow]COMPLETED TASKS[/bold yellow]", classes="panel-title"
                    )
                    tbl_done = DataTable(id="gallery-done", cursor_type="row")
                    tbl_done.add_columns("task_id", "kind", "intent", "finished_at")
                    yield tbl_done
            with Horizontal():
                yield Label("[cyan]Filter agent_id:[/cyan]")
                yield Input(placeholder="(blank = all)", id="gallery-filter")
            yield Static("[bold cyan]AUDIT LOG — DEEP DIVE[/bold cyan]", classes="panel-title")
            yield RichLog(id="gallery-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        self._ready = True

    @on(Input.Changed, "#gallery-filter")
    def _on_filter_change(self, event: Input.Changed) -> None:
        self._filter_agent = (event.value or "").strip().lower()

    def refresh_data(self, dlq: list, records: list[dict], audit: list[dict]) -> None:
        if not self._ready:
            return
        try:
            tbl = self.query_one("#gallery-dlq", DataTable)
            tbl.clear()
            for e in dlq:
                d = e.to_dict() if hasattr(e, "to_dict") else e
                failed = d.get("failed_at") or 0
                failed_fmt = time.strftime("%H:%M:%S", time.localtime(failed)) if failed else "—"
                tbl.add_row(
                    (d.get("task_id") or "")[:14],
                    (d.get("intent") or "—")[:30],
                    str(d.get("attempts", "?")),
                    (d.get("final_error") or "—")[:40],
                    failed_fmt,
                )
        except NoMatches:
            pass

        try:
            tbl2 = self.query_one("#gallery-done", DataTable)
            tbl2.clear()
            done = [r for r in records if r.get("state") == "SUCCEEDED"][-20:]
            for r in reversed(done):
                fin = r.get("finished_at") or 0
                fin_fmt = time.strftime("%H:%M:%S", time.localtime(fin)) if fin else "—"
                tbl2.add_row(
                    (r.get("task_id") or "")[:14],
                    r.get("kind", ""),
                    (r.get("intent") or "—")[:30],
                    fin_fmt,
                )
        except NoMatches:
            pass

        try:
            log_widget = self.query_one("#gallery-log", RichLog)
            log_widget.clear()
            filt = self._filter_agent
            for r in audit[-60:]:
                agent = r.get("agent_id", "?")
                if filt and filt not in agent.lower():
                    continue
                ts = r.get("timestamp_iso", "")[:19] or "—"
                kind = r.get("kind", "?")
                summary = (r.get("summary") or "")[:120]
                ec = r.get("exit_code")
                ec_fmt = f"[red]exit={ec}[/red] " if isinstance(ec, int) and ec != 0 else ""
                log_widget.write(
                    f"[dim]{ts}[/dim] [cyan]{agent}[/cyan] [yellow]{kind}[/yellow] {ec_fmt}{summary}"
                )
        except NoMatches:
            pass


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _upd(widget: Widget, selector: str, wtype: type, content: str) -> None:
    """Quietly update a Static widget's content; ignore NoMatches."""
    try:
        widget.query_one(selector, wtype).update(content)
    except (NoMatches, Exception):  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# ThroneApp — main Textual application
# ---------------------------------------------------------------------------


class ThroneApp(App):
    """AURORA THRONE — Sovereign Governance Chamber (Textual cinematic UI)."""

    TITLE = "PRADY OS — SOVEREIGN EDITION"
    CSS = THRONE_CSS
    BINDINGS = [
        Binding("1", "show_tab('pane-morning')", "Morning Brief", show=True),
        Binding("2", "show_tab('pane-dossiers')", "Dossiers", show=True),
        Binding("3", "show_tab('pane-campaign')", "Campaign", show=True),
        Binding("4", "show_tab('pane-health')", "Health", show=True),
        Binding("5", "show_tab('pane-gallery')", "Gallery", show=True),
        Binding("f1", "show_tab('pane-morning')", "Morning Brief", show=False),
        Binding("f2", "show_tab('pane-dossiers')", "Dossiers", show=False),
        Binding("f3", "show_tab('pane-campaign')", "Campaign", show=False),
        Binding("f4", "show_tab('pane-health')", "Health", show=False),
        Binding("f5", "show_tab('pane-gallery')", "Gallery", show=False),
        Binding("c", "focus_command", "Command", show=True),
        Binding("escape", "close_command", "Close", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        imperium: Any | None = None,
        warden_url: str | None = None,
        audit: AuditLog | None = None,
        checkpoint: CheckpointStore | None = None,
        refresh_hz: float = 2.0,
    ) -> None:
        super().__init__()
        self._imperium = imperium
        self._warden_url = warden_url or os.environ.get(
            "PRADYOS_WARDEN_URL", "http://127.0.0.1:9701"
        )
        self._audit = audit or get_audit_log()
        self._checkpoint = checkpoint or CheckpointStore()
        self._refresh_interval = max(0.5, 1.0 / max(0.1, refresh_hz))
        self._refresh_timer: Timer | None = None
        self._cmd_bar_visible = False

        self._morning = MorningBriefPane(self)
        self._dossiers = ProjectDossiersPane(self)
        self._campaign = CampaignViewPane(self)
        self._health = EmpireHealthPane(self)
        self._gallery = ArtifactGalleryPane(self)

    def compose(self) -> ComposeResult:
        yield ThroneHeader()
        with TabbedContent():
            yield self._morning
            yield self._dossiers
            yield self._campaign
            yield self._health
            yield self._gallery
        self._cmd_bar = CommandBar(self)
        self._cmd_bar.display = False
        yield self._cmd_bar
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_timer = self.set_interval(self._refresh_interval, self._refresh_all)
        self._refresh_all()

    # ---------- data gathering ----------

    def _gather_health(self) -> dict[str, Any] | None:
        return _warden_get(self._warden_url, "/health")

    def _gather_incidents(self) -> list[dict[str, Any]]:
        data = _warden_get(self._warden_url, "/incidents")
        return data.get("open", []) if data else []

    def _gather_queue(self) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        if self._imperium is not None:
            stats = self._imperium.stats()
            recs = [r.to_dict() for r in self._imperium.queue.iter_priority_order()]
            approvals = [r.to_dict() for r in self._imperium.pending_approvals()]
            return stats, recs, approvals
        latest = self._checkpoint.load_latest()
        records = list(latest.values())
        records.sort(key=lambda r: r.get("queued_at", 0))
        approvals = [r for r in records if r.get("state") == "ESCALATED"]
        stats: dict[str, Any] = {"total": len(records), "pending_approvals": len(approvals)}
        for r in records:
            k = f"state.{r.get('state','?')}"
            stats[k] = stats.get(k, 0) + 1
        return stats, records, approvals

    def _gather_audit(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._audit.tail(60)]

    def _gather_dlq(self) -> list[Any]:
        if self._imperium is not None:
            return self._imperium.dead_letter_queue()
        return []

    @work(thread=True)
    def _refresh_all(self) -> None:
        snap = self._gather_health()
        incidents = self._gather_incidents()
        stats, records, approvals = self._gather_queue()
        audit = self._gather_audit()
        dlq = self._gather_dlq()
        self.call_from_thread(
            self._apply_refresh, snap, incidents, stats, records, approvals, audit, dlq
        )

    def _apply_refresh(
        self,
        snap: dict | None,
        incidents: list,
        stats: dict,
        records: list,
        approvals: list,
        audit: list,
        dlq: list,
    ) -> None:
        self._morning.refresh_data(snap, incidents, stats, approvals, audit)
        self._dossiers.refresh_data(records)
        self._campaign.refresh_data(records, approvals)
        self._health.refresh_data(snap, incidents)
        self._gallery.refresh_data(dlq, records, audit)

    # ---------- actions ----------

    def action_show_tab(self, tab_id: str) -> None:
        try:
            tc = self.query_one(TabbedContent)
            tc.active = tab_id
        except NoMatches:
            pass

    def action_focus_command(self) -> None:
        self._cmd_bar.display = True
        self._cmd_bar_visible = True
        try:
            self._cmd_bar.query_one("#cmd-input", Input).focus()
        except NoMatches:
            pass

    def action_close_command(self) -> None:
        self._cmd_bar.display = False
        self._cmd_bar_visible = False

    # ---------- sovereign commands ----------

    def execute_command(self, raw: str) -> None:
        """Parse and execute a Sovereign command (approve / reject / quit).

        Commands:
            a <task_id>            — approve escalated task by ID prefix
            r <task_id> [reason]   — reject escalated task
            q                      — quit
        """
        parts = raw.strip().split(None, 2)
        if not parts:
            return
        verb = parts[0].lower()
        if verb in ("q", "quit", "exit"):
            self.exit()
            return
        if verb in ("a", "approve"):
            if len(parts) < 2:
                self.notify("Usage: a <task_id>", severity="error")
                return
            tid = parts[1]
            full_id = self._resolve_task_id(tid)
            if full_id and self._imperium:
                ok = self._imperium.approve(full_id, approver="sovereign")
                self.notify(
                    f"✓ Approved {full_id[:16]}" if ok else f"Cannot approve {tid}",
                    severity="information" if ok else "error",
                )
            else:
                self.notify(f"Task not found: {tid}", severity="error")
        elif verb in ("r", "reject"):
            if len(parts) < 2:
                self.notify("Usage: r <task_id> [reason]", severity="error")
                return
            tid = parts[1]
            reason = parts[2] if len(parts) > 2 else "rejected via Throne"
            full_id = self._resolve_task_id(tid)
            if full_id and self._imperium:
                ok = self._imperium.reject(full_id, approver="sovereign", reason=reason)
                self.notify(
                    f"✗ Rejected {full_id[:16]}" if ok else f"Cannot reject {tid}",
                    severity="warning" if ok else "error",
                )
            else:
                self.notify(f"Task not found: {tid}", severity="error")
        else:
            self.notify(
                f"Unknown command: {verb!r}  (a=approve, r=reject, q=quit)", severity="error"
            )
        self.action_close_command()

    def _resolve_task_id(self, prefix: str) -> str | None:
        if self._imperium is not None:
            for rec in self._imperium.queue.all_records():
                if rec.spec.task_id.startswith(prefix):
                    return rec.spec.task_id
            return None
        latest = self._checkpoint.load_latest()
        for tid in latest:
            if tid.startswith(prefix):
                return tid
        return None


# ---------------------------------------------------------------------------
# Throne — backward-compatible Rich shim (used by tests and --once mode)
# ---------------------------------------------------------------------------


def _warden_get_rich(url: str, path: str, timeout: float = 1.5) -> dict[str, Any] | None:
    """Re-export of _warden_get for the Throne shim."""
    return _warden_get(url, path, timeout)


class Throne:
    """Sovereign Governance Chamber — backward-compatible wrapper.

    ``run(once=True)``  → renders one Rich snapshot to stdout (used by tests)
    ``run()``           → launches the full Textual ThroneApp
    ``approve(id)``     → proxies to embedded IMPERIUM
    ``reject(id)``      → proxies to embedded IMPERIUM

    Hidden-CLI doctrine: this class does NOT expose ``exec``, ``shell``,
    ``system``, ``run_shell``, or ``command`` as public methods.
    """

    def __init__(
        self,
        imperium: Any | None = None,
        warden_url: str | None = None,
        audit: AuditLog | None = None,
        checkpoint: CheckpointStore | None = None,
        refresh_hz: float = 2.0,
    ) -> None:
        self.imperium = imperium
        self.warden_url = warden_url or os.environ.get(
            "PRADYOS_WARDEN_URL", "http://127.0.0.1:9701"
        )
        self.audit = audit or get_audit_log()
        self.checkpoint = checkpoint or CheckpointStore()
        self.refresh_hz = refresh_hz
        self.console = Console()
        self._stop = threading.Event()
        self._app: ThroneApp | None = None

    # ---------- public API ----------

    def approve(self, task_id: str, by: str = "sovereign") -> bool:
        if self.imperium is None:
            self.console.print("[red]Standalone Throne cannot issue approvals[/red]")
            return False
        return self.imperium.approve(task_id, approver=by)

    def reject(self, task_id: str, by: str = "sovereign", reason: str = "") -> bool:
        if self.imperium is None:
            self.console.print("[red]Standalone Throne cannot issue approvals[/red]")
            return False
        return self.imperium.reject(task_id, approver=by, reason=reason)

    def stop(self) -> None:
        self._stop.set()
        if self._app is not None:
            try:
                self._app.exit()
            except Exception:  # noqa: BLE001
                pass

    def run(self, once: bool = False) -> None:
        """Render the Throne.

        If ``once=True``: produce one Rich snapshot and return immediately.
        Otherwise: launch the full Textual ThroneApp.
        """
        if once:
            self._run_rich_once()
            return
        self._app = ThroneApp(
            imperium=self.imperium,
            warden_url=self.warden_url,
            audit=self.audit,
            checkpoint=self.checkpoint,
            refresh_hz=self.refresh_hz,
        )
        self._app.run()

    # ---------- internal Rich snapshot ----------

    def _run_rich_once(self) -> None:
        snap = _warden_get(self.warden_url, "/health")
        incidents_data = _warden_get(self.warden_url, "/incidents")
        incidents = (incidents_data or {}).get("open", [])
        stats, records, approvals = self._gather_queue()
        audit = self._gather_audit()

        layout = Layout()
        layout.split_column(
            Layout(header_banner(), name="header", size=4),
            Layout(name="upper"),
            Layout(name="middle"),
            Layout(name="lower"),
        )
        layout["upper"].split_row(
            Layout(health_panel(snap), name="health", ratio=1),
            Layout(queue_panel(stats, records), name="queue", ratio=1),
        )
        layout["middle"].split_row(
            Layout(approvals_panel(approvals), name="approvals", ratio=1),
            Layout(incidents_panel(incidents), name="incidents", ratio=1),
        )
        layout["lower"].update(audit_panel(audit))
        self.console.print(layout)

    def _gather_queue(self) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        if self.imperium is not None:
            stats = self.imperium.stats()
            recs = [r.to_dict() for r in self.imperium.queue.iter_priority_order()]
            approvals = [r.to_dict() for r in self.imperium.pending_approvals()]
            return stats, recs, approvals
        latest = self.checkpoint.load_latest()
        records = list(latest.values())
        records.sort(key=lambda r: (r.get("priority", "BACKGROUND"), r.get("queued_at", 0)))
        stats: dict[str, Any] = {"total": len(records), "pending_approvals": 0}
        for r in records:
            k = f"state.{r.get('state', '?')}"
            stats[k] = stats.get(k, 0) + 1
        approvals = [r for r in records if r.get("state") == "ESCALATED"]
        stats["pending_approvals"] = len(approvals)
        return stats, records, approvals

    def _gather_audit(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.audit.tail(20)]


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pradyos-throne",
        description="AURORA THRONE — Sovereign Governance Chamber",
    )
    parser.add_argument(
        "--once", action="store_true", help="render once with Rich and exit (non-interactive)"
    )
    parser.add_argument(
        "--warden-url",
        default=None,
        help="WARDEN GRID base URL (default $PRADYOS_WARDEN_URL or http://127.0.0.1:9701)",
    )
    parser.add_argument(
        "--refresh-hz", type=float, default=2.0, help="Display refresh rate in Hz (default 2)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    if args.once:
        throne = Throne(warden_url=args.warden_url, refresh_hz=args.refresh_hz)
        throne.run(once=True)
        return 0

    app = ThroneApp(warden_url=args.warden_url, refresh_hz=args.refresh_hz)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
