"""AURORA THRONE — Full Textual cinematic UI (Phase 1, §13.2).

Five sovereign views bound to keys 1-5 and function keys:

    1 / F1  →  Morning Brief        — daily command summary
    2 / F2  →  Project Dossiers     — task ledger by project
    3 / F3  →  Campaign View        — running operations + approvals
    4 / F4  →  Empire Health        — WARDEN GRID telemetry
    5 / F5  →  Artifact Gallery     — DLQ, rollback registry, audit deep-dive

Keyboard shortcuts (hidden-CLI doctrine preserved — no raw shell):

    a <id>   →  approve escalated task by prefix
    r <id>   →  reject  escalated task by prefix
    q / ESC  →  quit

CSS palette: dark terminal aesthetic — cyan sovereignty, amber warnings,
crimson alerts, ghost-grey dims.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
    Tab,
    TabbedContent,
    TabPane,
)

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.imperium.checkpoint import CheckpointStore

# Phase 2 imports — optional (graceful no-op if not yet wired)
try:
    from pradyos.campaign.model import Campaign, CampaignStatus, NodeStatus
    from pradyos.campaign.registry import CampaignRegistry
    _HAS_CAMPAIGN = True
except ImportError:
    _HAS_CAMPAIGN = False  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Palette constants
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

ThroneFooter {
    height: 2;
    background: #0d1117;
    border-top: solid #1a2634;
    color: #4a5568;
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

PanelBox.-warn {
    border: solid #d4a017;
}

PanelBox.-crit {
    border: solid #c62828;
}

PanelBox.-ok {
    border: solid #00897b;
}

.panel-title {
    color: #00b4d8;
    text-style: bold;
    padding: 0 1;
    background: #0d1117;
}

.dim {
    color: #4a5568;
}

.ok { color: #00897b; }
.warn { color: #d4a017; }
.crit { color: #c62828; }
.running { color: #f39c12; }
.queued { color: #00b4d8; }
.succeeded { color: #00897b; }
.failed { color: #c62828; }
.escalated { color: #9b59b6; text-style: bold; }

ApprovalCard {
    height: auto;
    border: solid #9b59b6;
    margin: 0 0 1 0;
    padding: 0 1;
    background: #120a1e;
}

ApprovalCard > .card-header {
    text-style: bold;
    color: #9b59b6;
}

ApprovalCard > .card-body {
    color: #c5cdd9;
}

ApprovalCard > Horizontal {
    height: 3;
    margin-top: 1;
}

ApprovalCard Button {
    margin-right: 1;
}

#approve-btn {
    background: #00897b;
    color: white;
}

#reject-btn {
    background: #c62828;
    color: white;
}

IncidentRow {
    height: 2;
    border-bottom: dashed #1a2634;
}

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

#morning-brief {
    layout: grid;
    grid-size: 2;
    grid-gutter: 1;
}

#brief-left {
    row-span: 1;
}

#brief-right {
    row-span: 1;
}

#dossiers-table {
    height: 1fr;
}

#campaign-outer {
    layout: vertical;
    height: 1fr;
}

#campaign-oracle-bar {
    height: 3;
    background: #0d1117;
    border-bottom: solid #1a2634;
    padding: 0 2;
    color: #c5cdd9;
}

#campaign-pane {
    layout: horizontal;
    height: 1fr;
}

#campaign-left {
    width: 62%;
    border-right: solid #1a2634;
    layout: vertical;
}

#campaign-table {
    height: 1fr;
}

#campaign-node-table {
    height: 1fr;
    background: #060a0f;
}

#campaign-tasks {
    width: 60%;
    border-right: solid #1a2634;
}

#campaign-approvals {
    width: 38%;
    padding: 0 1;
}

#health-grid {
    layout: grid;
    grid-size: 2;
    grid-gutter: 1;
}

#gallery-log {
    height: 1fr;
    background: #060a0f;
    border: solid #1a2634;
}

DataTable {
    background: #0a0e14;
    color: #c5cdd9;
}

DataTable > .datatable--header {
    background: #0d1117;
    color: #00b4d8;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1a2634;
}
"""

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _http_get_json(base: str, path: str, timeout: float = 1.5) -> dict[str, Any] | None:
    """Generic HTTP GET → JSON dict, best-effort (TCP only, no AF_UNIX)."""
    try:
        req = urllib.request.Request(base.rstrip("/") + path)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:  # noqa: BLE001
        return None


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


def _campaign_status_color(status: str) -> str:
    return {
        "running":      "yellow",
        "planning":     "cyan",
        "succeeded":    "green",
        "failed":       "red",
        "rolled_back":  "magenta",
        "paused":       "yellow",
        "pending":      "dim",
        "cancelled":    "dim",
    }.get(status.lower(), "white")


def _node_status_color(status: str) -> str:
    return {
        "running":           "yellow",
        "planning":          "cyan",
        "ready":             "cyan",
        "succeeded":         "green",
        "failed":            "red",
        "rolled_back":       "magenta",
        "skipped":           "dim",
        "pending":           "dim",
        "awaiting_approval": "magenta",
    }.get(status.lower(), "white")


# ---------------------------------------------------------------------------
# Custom widgets
# ---------------------------------------------------------------------------

class ThroneHeader(Widget):
    DEFAULT_CSS = ""
    ts: reactive[str] = reactive("")

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
    """A single labelled progress bar for a numeric percentage metric."""

    def __init__(self, label: str, pct: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._pct = min(100.0, max(0.0, pct))

    def compose(self) -> ComposeResult:
        color = "green" if self._pct < 70 else "yellow" if self._pct < 90 else "red"
        yield Label(self._label)
        bar = ProgressBar(total=100, show_percentage=False, show_eta=False)
        bar.advance(self._pct)
        yield bar
        yield Label(f"{self._pct:5.1f}%", classes="pct-label")

    def _get_css_modifier(self) -> str:
        if self._pct >= 90:
            return "-crit"
        if self._pct >= 70:
            return "-warn"
        return "-ok"


class PanelBox(Container):
    """A titled bordered container."""

    def __init__(self, title: str, *args: Any, modifier: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._title = title
        self._modifier = modifier
        if modifier:
            self.add_class(modifier)

    def compose(self) -> ComposeResult:
        yield Static(f" {self._title} ", classes="panel-title")


class ApprovalCard(Widget):
    """Interactive card for an escalated task awaiting approval."""

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
        yield Static(f"[bold magenta]APPROVAL REQUIRED[/bold magenta]  [{tid}]", classes="card-header")
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


# ---------------------------------------------------------------------------
# View panes
# ---------------------------------------------------------------------------

class MorningBriefPane(TabPane):
    """View 1 — command summary, top incidents, pending approvals at a glance."""

    def __init__(self, throne: "ThroneApp") -> None:
        super().__init__("Morning Brief", id="pane-morning")
        self._throne = throne

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="brief-greeting", classes="")
            with Horizontal():
                with Vertical(id="brief-left"):
                    yield Static("[bold cyan]SYSTEM STATUS[/bold cyan]", classes="panel-title")
                    yield Static(id="brief-health", classes="")
                with Vertical(id="brief-right"):
                    yield Static("[bold yellow]OPEN INCIDENTS[/bold yellow]", classes="panel-title")
                    yield Static(id="brief-incidents", classes="")
            with Vertical():
                yield Static("[bold magenta]PENDING APPROVALS[/bold magenta]", classes="panel-title")
                yield Static(id="brief-approvals", classes="")
            with Vertical():
                yield Static("[bold cyan]RECENT AUDIT[/bold cyan]", classes="panel-title")
                yield Static(id="brief-audit", classes="")

    def refresh_data(
        self,
        snap: dict | None,
        incidents: list,
        stats: dict,
        approvals: list,
        audit: list,
    ) -> None:
        # Greeting
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        try:
            self.query_one("#brief-greeting", Static).update(
                f"[bold bright_cyan]{greeting}, Sovereign.[/bold bright_cyan]  "
                f"[grey50]Empire integrity check — {datetime.now().strftime('%A, %B %-d, %Y')}[/grey50]"
            )
        except Exception:  # noqa: BLE001
            pass

        # Health summary
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
        try:
            self.query_one("#brief-health", Static).update(health_txt)
        except Exception:  # noqa: BLE001
            pass

        # Incidents
        if incidents:
            lines = []
            for inc in incidents[:6]:
                sev = inc.get("severity", "?")
                color = _sev_color(sev)
                lines.append(f"[{color}]{sev}[/{color}] {inc.get('component','?')} — {inc.get('summary','?')}")
            inc_txt = "\n".join(lines)
        else:
            inc_txt = "[green]All clear — no open incidents[/green]"
        try:
            self.query_one("#brief-incidents", Static).update(inc_txt)
        except Exception:  # noqa: BLE001
            pass

        # Approvals
        ap_count = len(approvals)
        ap_txt = (
            f"[magenta]{ap_count} task(s) awaiting Sovereign approval — switch to Campaign View (3)[/magenta]"
            if ap_count else "[green]No approvals pending[/green]"
        )
        try:
            self.query_one("#brief-approvals", Static).update(ap_txt)
        except Exception:  # noqa: BLE001
            pass

        # Audit tail
        if audit:
            lines = []
            for r in audit[-6:]:
                ts = r.get("timestamp_iso", "")[-8:] or "—"
                agent = r.get("agent_id", "?")
                kind = r.get("kind", "?")
                summary = (r.get("summary") or "")[:80]
                ec = r.get("exit_code")
                ec_fmt = f"[red]{ec}[/red]" if isinstance(ec, int) and ec not in (0, None) else ""
                lines.append(f"[dim]{ts}[/dim] [cyan]{agent}[/cyan] {ec_fmt} {summary}")
            audit_txt = "\n".join(lines)
        else:
            audit_txt = "[dim]Audit ledger empty[/dim]"
        try:
            self.query_one("#brief-audit", Static).update(audit_txt)
        except Exception:  # noqa: BLE001
            pass


class ProjectDossiersPane(TabPane):
    """View 2 — full task ledger with state/priority grouping."""

    def __init__(self, throne: "ThroneApp") -> None:
        super().__init__("Project Dossiers", id="pane-dossiers")
        self._throne = throne
        self._ready = False

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]PROJECT DOSSIERS — IMPERIUM TASK LEDGER[/bold cyan]", classes="panel-title")
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
    """View 3 — live campaign DAGs, ORACLE status, sovereign approvals."""

    def __init__(self, throne: "ThroneApp") -> None:
        super().__init__("Campaign View", id="pane-campaign")
        self._throne = throne
        self._ready = False
        self._last_approval_ids: set[str] = set()
        self._selected_campaign_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="campaign-outer"):
            # ORACLE status bar
            yield Static(
                "[dim]ORACLE — checking…[/dim]",
                id="campaign-oracle-bar",
            )
            with Horizontal(id="campaign-pane"):
                # Left: campaigns + nodes
                with Vertical(id="campaign-left"):
                    yield Static(
                        "[bold yellow]CAMPAIGNS[/bold yellow]",
                        classes="panel-title",
                    )
                    camp_tbl = DataTable(id="campaign-table", cursor_type="row")
                    camp_tbl.add_columns("id", "status", "name", "nodes", "progress")
                    yield camp_tbl
                    yield Static(
                        "[bold cyan]NODES[/bold cyan]",
                        classes="panel-title",
                    )
                    node_tbl = DataTable(id="campaign-node-table", cursor_type="row")
                    node_tbl.add_columns("node", "status", "intent", "dur")
                    yield node_tbl
                # Right: IMPERIUM active tasks + approvals
                with ScrollableContainer(id="campaign-approvals"):
                    yield Static(
                        "[bold yellow]ACTIVE TASKS[/bold yellow]",
                        classes="panel-title",
                    )
                    task_tbl = DataTable(id="campaign-tasks-tbl", cursor_type="row")
                    task_tbl.add_columns("id", "state", "intent", "dur")
                    yield task_tbl
                    yield Static(
                        "[bold magenta]APPROVALS[/bold magenta]",
                        classes="panel-title",
                    )
                    yield Static(
                        "[dim]No escalated tasks[/dim]",
                        id="no-approvals-msg",
                    )

    def on_mount(self) -> None:
        self._ready = True

    def refresh_data(
        self,
        records: list[dict],
        approvals: list[dict],
        campaigns: list[dict] | None = None,
        oracle_status: dict | None = None,
    ) -> None:
        if not self._ready:
            return

        # ---- ORACLE status bar ----
        try:
            bar = self.query_one("#campaign-oracle-bar", Static)
            if oracle_status is None:
                bar.update("[dim]ORACLE — not connected[/dim]")
            elif oracle_status.get("alive"):
                model = oracle_status.get("model", "?")
                models = oracle_status.get("available_models", [])
                model_fmt = (
                    f"[green]{model}[/green]" if model in models
                    else f"[yellow]{model} (not pulled)[/yellow]"
                )
                bar.update(
                    f"[bold cyan]ORACLE[/bold cyan]  "
                    f"model={model_fmt}  "
                    f"url=[dim]{oracle_status.get('base_url', '?')}[/dim]  "
                    f"[green]● ONLINE[/green]"
                )
            else:
                url = oracle_status.get("base_url", "?")
                bar.update(
                    f"[bold cyan]ORACLE[/bold cyan]  "
                    f"[red]● OFFLINE[/red]  "
                    f"[dim]Ollama not reachable at {url}[/dim]"
                )
        except NoMatches:
            pass

        # ---- Campaigns table ----
        try:
            camp_tbl = self.query_one("#campaign-table", DataTable)
            camp_tbl.clear()
            for c in (campaigns or []):
                status = c.get("status", "?")
                sc = _campaign_status_color(status)
                progress = c.get("progress", {})
                total = sum(progress.values()) if progress else 0
                done = progress.get("succeeded", 0)
                prog_str = (
                    f"{done}/{total}"
                    if total
                    else "—"
                )
                camp_tbl.add_row(
                    (c.get("campaign_id") or "")[:14],
                    f"[{sc}]{status}[/{sc}]" if sc else status,
                    (c.get("name") or "—")[:32],
                    str(total),
                    prog_str,
                    key=c.get("campaign_id"),
                )
            # Auto-select first active campaign for node drill-down
            if campaigns and self._selected_campaign_id is None:
                for c in campaigns:
                    if c.get("status") not in ("succeeded", "cancelled", "rolled_back"):
                        self._selected_campaign_id = c.get("campaign_id")
                        break
        except NoMatches:
            pass

        # ---- Node drill-down for selected campaign ----
        try:
            node_tbl = self.query_one("#campaign-node-table", DataTable)
            node_tbl.clear()
            if campaigns and self._selected_campaign_id:
                selected = next(
                    (c for c in campaigns if c.get("campaign_id") == self._selected_campaign_id),
                    None,
                )
                if selected:
                    now = time.time()
                    for node in selected.get("nodes", {}).values():
                        nstatus = node.get("status", "?")
                        nsc = _node_status_color(nstatus)
                        started = float(node.get("started_at") or 0)
                        dur = _fmt_duration(now - started) if started else "—"
                        node_tbl.add_row(
                            (node.get("node_id") or "")[:14],
                            f"[{nsc}]{nstatus}[/{nsc}]" if nsc else nstatus,
                            (node.get("task_intent") or "—")[:44],
                            dur,
                            key=node.get("node_id"),
                        )
        except NoMatches:
            pass

        # ---- Active IMPERIUM tasks ----
        try:
            task_tbl = self.query_one("#campaign-tasks-tbl", DataTable)
            task_tbl.clear()
            active_states = {"RUNNING", "QUEUED", "ESCALATED"}
            now = time.time()
            for r in records:
                if r.get("state") not in active_states:
                    continue
                state = r.get("state", "?")
                sc = _state_color(state)
                started = float(r.get("started_at") or 0)
                dur = _fmt_duration(now - started) if started else "—"
                task_tbl.add_row(
                    (r.get("task_id") or "")[:14],
                    f"[{sc}]{state}[/{sc}]" if sc else state,
                    (r.get("intent") or "—")[:38],
                    dur,
                    key=r.get("task_id"),
                )
        except NoMatches:
            pass

        # ---- Approval cards ----
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
    """View 4 — full WARDEN GRID telemetry with metric bars."""

    def __init__(self, throne: "ThroneApp") -> None:
        super().__init__("Empire Health", id="pane-health")
        self._throne = throne

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold cyan]EMPIRE HEALTH — WARDEN GRID TELEMETRY[/bold cyan]", classes="panel-title")
            yield Static(id="health-meta", classes="")
            with Vertical(id="health-bars"):
                yield Static("[dim]Awaiting telemetry…[/dim]", id="health-placeholder")
            yield Static("[bold red]OPEN INCIDENTS[/bold red]", classes="panel-title")
            tbl = DataTable(id="health-incidents", cursor_type="row")
            tbl.add_columns("sev", "component", "summary", "occurrences", "first_seen")
            yield tbl

    def refresh_data(self, snap: dict | None, incidents: list[dict]) -> None:
        # Meta
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
        try:
            self.query_one("#health-meta", Static).update(meta_txt)
        except NoMatches:
            pass

        # Metric bars
        bars_container = None
        try:
            bars_container = self.query_one("#health-bars")
            placeholder = bars_container.query_one("#health-placeholder", Static)
        except NoMatches:
            bars_container = None

        if bars_container is not None:
            # Remove old MetricBars
            for mb in list(bars_container.query(MetricBar)):
                mb.remove()

            if snap:
                try:
                    placeholder.display = False
                except Exception:  # noqa: BLE001
                    pass
                metrics = [
                    ("CPU", snap.get("cpu_percent", 0)),
                    ("RAM", snap.get("ram_percent", 0)),
                    ("SWAP", snap.get("swap_percent", 0)),
                ]
                for d in snap.get("disk", [])[:4]:
                    mount = d.get("mount", "?")
                    metrics.append((f"DSK {mount[:6]}", d.get("percent", 0)))
                for g in snap.get("gpus", [])[:2]:
                    metrics.append((f"GPU{g.get('index',0)}", g.get("util_percent", 0)))
                for label, pct in metrics:
                    bars_container.mount(MetricBar(label, float(pct)))
            else:
                try:
                    placeholder.display = True
                except Exception:  # noqa: BLE001
                    pass

        # Incidents table
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
    """View 5 — DLQ, rollback entries, completed tasks, deep audit log."""

    def __init__(self, throne: "ThroneApp") -> None:
        super().__init__("Artifact Gallery", id="pane-gallery")
        self._throne = throne
        self._ready = False

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                with Vertical():
                    yield Static("[bold red]DEAD LETTER QUEUE[/bold red]", classes="panel-title")
                    tbl_dlq = DataTable(id="gallery-dlq", cursor_type="row")
                    tbl_dlq.add_columns("task_id", "intent", "attempts", "final_error", "failed_at")
                    yield tbl_dlq
                with Vertical():
                    yield Static("[bold yellow]COMPLETED TASKS[/bold yellow]", classes="panel-title")
                    tbl_done = DataTable(id="gallery-done", cursor_type="row")
                    tbl_done.add_columns("task_id", "kind", "intent", "finished_at")
                    yield tbl_done
            yield Static("[bold cyan]AUDIT LOG — DEEP DIVE[/bold cyan]", classes="panel-title")
            yield RichLog(id="gallery-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        self._ready = True

    def refresh_data(self, dlq: list, records: list[dict], audit: list[dict]) -> None:
        if not self._ready:
            return

        # DLQ
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

        # Completed tasks
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

        # Audit log
        try:
            log_widget = self.query_one("#gallery-log", RichLog)
            log_widget.clear()
            for r in audit[-40:]:
                ts = r.get("timestamp_iso", "")[:19] or "—"
                agent = r.get("agent_id", "?")
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
# Command bar overlay
# ---------------------------------------------------------------------------

class CommandBar(Widget):
    """Sovereign command input — approve/reject by task ID prefix."""

    def __init__(self, throne: "ThroneApp") -> None:
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
        if not raw:
            return
        self._throne.execute_command(raw)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class ThroneApp(App):
    """AURORA THRONE — Sovereign Governance Chamber, Phase 1 Textual edition."""

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
        Binding("d", "show_dashboard", "Dashboard", show=True),
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
        campaign_engine: Any | None = None,
        oracle_url: str | None = None,
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

        # Phase 2: campaign engine + oracle status
        self._campaign_engine = campaign_engine
        self._oracle_url = oracle_url or os.environ.get(
            "PRADYOS_ORACLE_URL", "http://127.0.0.1:11435"
        )
        # Lazy-load campaign registry for standalone mode
        self._campaign_registry: Any | None = None
        if _HAS_CAMPAIGN and campaign_engine is None:
            try:
                self._campaign_registry = CampaignRegistry()
            except Exception:  # noqa: BLE001
                pass

        # Panes — instantiated here, composed below
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

    # ---------- data refresh ----------

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
        # Standalone: read checkpoint
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
        return [r.to_dict() for r in self._audit.tail(50)]

    def _gather_dlq(self) -> list[Any]:
        if self._imperium is not None:
            return self._imperium.dead_letter_queue()
        return []

    def _gather_campaigns(self) -> list[dict[str, Any]]:
        """Return serialised campaign dicts from CampaignEngine or registry."""
        # In-process engine takes priority
        if self._campaign_engine is not None:
            try:
                reg = self._campaign_engine._registry
                return [c.to_dict() for c in reg.recent(30)]
            except Exception:  # noqa: BLE001
                return []
        # Standalone: read from registry loaded at startup
        if self._campaign_registry is not None:
            try:
                return [c.to_dict() for c in self._campaign_registry.recent(30)]
            except Exception:  # noqa: BLE001
                return []
        return []

    def _gather_oracle_status(self) -> dict[str, Any] | None:
        """Poll the Oracle HTTP status endpoint (non-blocking, best-effort)."""
        return _http_get_json(self._oracle_url, "/oracle/status", timeout=1.0)

    @work(thread=True)
    def _refresh_all(self) -> None:
        """Fetch all data sources in a background thread, then dispatch to UI."""
        snap = self._gather_health()
        incidents = self._gather_incidents()
        stats, records, approvals = self._gather_queue()
        audit = self._gather_audit()
        dlq = self._gather_dlq()
        campaigns = self._gather_campaigns()
        oracle_status = self._gather_oracle_status()
        # Update each pane from main thread via call_from_thread
        self.call_from_thread(
            self._apply_refresh,
            snap, incidents, stats, records, approvals, audit, dlq,
            campaigns, oracle_status,
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
        campaigns: list | None = None,
        oracle_status: dict | None = None,
    ) -> None:
        self._morning.refresh_data(snap, incidents, stats, approvals, audit)
        self._dossiers.refresh_data(records)
        self._campaign.refresh_data(records, approvals, campaigns, oracle_status)
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

    def action_show_dashboard(self) -> None:
        """Push the DashboardScreen (Phase 12 observability view)."""
        from pradyos.aurora_throne.dashboard import ObservabilityDashboard  # noqa: PLC0415
        # Re-use an existing wired dashboard if available, else create one.
        dash = getattr(self, "_observability_dashboard", None)
        self.push_screen(DashboardScreen(dashboard=dash))

    # ---------- sovereign commands ----------

    def execute_command(self, raw: str) -> None:
        """Parse and execute a Sovereign command from the command bar.

        Commands:
            a <task_id>            — approve escalated task
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
            self.notify(f"Unknown command: {verb!r}  (a=approve, r=reject, q=quit)", severity="error")
        self.action_close_command()

    def _resolve_task_id(self, prefix: str) -> str | None:
        """Resolve a task ID prefix to a full ID via IMPERIUM or checkpoint."""
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
# DashboardScreen (Phase 12 — Observability Dashboard)
# ---------------------------------------------------------------------------

class DashboardScreen(Screen):
    """Full-screen observability dashboard.

    Renders three panels:
      - Live Bus Events  — last 50 events from the EventBus ring buffer
      - Quarantine       — tasks quarantined by SelfHealEngine
      - System Health    — coarse health signal from kernel metrics

    Accessible via the ``d`` keybind from :class:`ThroneApp`.
    Press ``escape`` or ``q`` to dismiss and return to the main throne.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Back", show=True),
        Binding("q", "dismiss", "Back", show=False),
    ]

    def __init__(self, dashboard: Any | None = None) -> None:
        super().__init__()
        self._dashboard = dashboard

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="dash-events"):
                yield Static(
                    "[bold cyan]LIVE BUS EVENTS[/bold cyan]",
                    classes="panel-title",
                )
                yield RichLog(id="dash-events-log", highlight=True, markup=True, wrap=True)
            with Vertical(id="dash-quarantine"):
                yield Static(
                    "[bold red]QUARANTINE[/bold red]",
                    classes="panel-title",
                )
                yield RichLog(id="dash-quarantine-log", highlight=True, markup=True, wrap=True)
            with Vertical(id="dash-health"):
                yield Static(
                    "[bold yellow]SYSTEM HEALTH[/bold yellow]",
                    classes="panel-title",
                )
                yield RichLog(id="dash-health-log", highlight=True, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_dashboard()
        self.set_interval(2.0, self._refresh_dashboard)

    def _refresh_dashboard(self) -> None:
        """Pull a fresh snapshot and update all three panels."""
        if self._dashboard is None:
            self._write_panel("dash-events-log", ["[dim]No dashboard wired[/dim]"])
            self._write_panel("dash-quarantine-log", ["[dim]—[/dim]"])
            self._write_panel("dash-health-log", ["[dim]—[/dim]"])
            return

        try:
            snap = self._dashboard.get_live_snapshot()
        except Exception as exc:  # noqa: BLE001
            self._write_panel("dash-events-log", [f"[red]Error: {exc}[/red]"])
            return

        # Live Bus Events
        events = snap.bus_events[-20:]  # most recent 20 for display
        if events:
            lines = []
            for ev in reversed(events):
                ts = ev.get("ts", 0.0)
                ts_fmt = time.strftime("%H:%M:%S", time.localtime(float(ts))) if ts else "--"
                topic = ev.get("topic", "?")
                payload_str = str(ev.get("payload", {}))[:80]
                lines.append(f"[dim]{ts_fmt}[/dim] [cyan]{topic}[/cyan]  {payload_str}")
        else:
            lines = ["[dim]No events yet[/dim]"]
        self._write_panel("dash-events-log", lines)

        # Quarantine
        q = snap.quarantine
        if q:
            q_lines = [f"[red]{tid[:24]}[/red]" for tid in q]
        else:
            q_lines = ["[green]No quarantined tasks[/green]"]
        self._write_panel("dash-quarantine-log", q_lines)

        # System Health
        health = snap.system_health
        status = health.get("status", "?")
        status_color = {"ok": "green", "degraded": "yellow", "critical": "red"}.get(status, "white")
        last_ts = health.get("last_event_ts")
        last_fmt = (
            time.strftime("%H:%M:%S", time.localtime(float(last_ts)))
            if last_ts is not None else "none"
        )
        h_lines = [
            f"[{status_color}]STATUS: {status.upper()}[/{status_color}]",
            f"[dim]Active tasks:[/dim]      [cyan]{health.get('active_tasks', 0)}[/cyan]",
            f"[dim]Dead-letter queue:[/dim] [cyan]{health.get('dead_letter_count', 0)}[/cyan]",
            f"[dim]Last event:[/dim]        [dim]{last_fmt}[/dim]",
        ]
        self._write_panel("dash-health-log", h_lines)

    def _write_panel(self, widget_id: str, lines: list) -> None:
        try:
            log_w = self.query_one(f"#{widget_id}", RichLog)
            log_w.clear()
            for line in lines:
                log_w.write(line)
        except NoMatches:
            pass

    def action_dismiss(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging

    parser = argparse.ArgumentParser(
        prog="pradyos-throne",
        description="AURORA THRONE — Sovereign Governance Chamber (Textual edition)",
    )
    parser.add_argument("--warden-url", default=None,
                        help="WARDEN GRID base URL")
    parser.add_argument("--oracle-url", default=None,
                        help="ORACLE status endpoint base URL")
    parser.add_argument("--refresh-hz", type=float, default=2.0,
                        help="Display refresh rate in Hz (default 2)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    app = ThroneApp(
        warden_url=args.warden_url,
        oracle_url=args.oracle_url,
        refresh_hz=args.refresh_hz,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
