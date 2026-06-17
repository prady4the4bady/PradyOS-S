"""SOVEREIGN CLI -- headless command interface for PRADY OS.

Entry point: pradyos-sovereign
No Textual required. Pure argparse. Windows-safe (TCP only, pathlib paths,
sys.executable, no fork/killpg/start_new_session).

Commands:
    status                          Show live system state
    approve <task_id>               Approve an escalated task
    reject  <task_id>               Reject an escalated task
    run-campaign <campaign_id>      Launch a campaign by ID
    list-campaigns [--status STR]   List campaigns
    schedule list                   List cron schedules
    schedule add --name --cron --intent  Add a schedule
    schedule remove <schedule_id>   Remove a schedule
    daemon                          Start personal-assistant daemon

State sources:
    IMPERIUM checkpoint  -> var/state/imperium_tasks.jsonl  (read)
    WARDEN GRID HTTP     -> http://localhost:8765/health    (read)
    Sovereign decisions  -> var/state/sovereign_decisions.jsonl (write)
    Campaign registry    -> var/state/campaigns.jsonl       (read)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_STATE_DIR = Path(os.environ.get("PRADYOS_STATE_PATH", str(_ROOT / "var" / "state")))

_CHECKPOINT = _STATE_DIR / "imperium_tasks.jsonl"
_DECISIONS = _STATE_DIR / "sovereign_decisions.jsonl"
_SCHEDULES = _STATE_DIR / "schedules.jsonl"

_WARDEN_HOST = os.environ.get("PRADYOS_WARDEN_HOST", "localhost")
_WARDEN_PORT = int(os.environ.get("PRADYOS_WARDEN_PORT", "8765"))

# ---------------------------------------------------------------------------
# Checkpoint reader
# ---------------------------------------------------------------------------


def _load_checkpoint() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not _CHECKPOINT.exists():
        return latest
    try:
        with _CHECKPOINT.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                    latest[rec["task_id"]] = rec
                except (json.JSONDecodeError, KeyError):
                    continue
    except OSError:
        pass
    return latest


# ---------------------------------------------------------------------------
# WARDEN GRID HTTP
# ---------------------------------------------------------------------------


def _warden_health() -> dict[str, Any] | None:
    try:
        import urllib.request

        url = f"http://{_WARDEN_HOST}:{_WARDEN_PORT}/health"
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Decisions writer
# ---------------------------------------------------------------------------


def _write_decision(decision: dict[str, Any]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    decision["at"] = time.time()
    with _DECISIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(decision, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Task-ID prefix resolver
# ---------------------------------------------------------------------------


def _resolve_task_id(raw: str, tasks: dict[str, Any]) -> str | None:
    if raw in tasks:
        return raw
    matches = [tid for tid in tasks if tid.startswith(raw)]
    if len(matches) == 1:
        return matches[0]
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    print("PRADY OS -- SOVEREIGN STATUS")
    print("=" * 52)

    tasks = _load_checkpoint()
    if tasks:
        states = Counter(t["state"] for t in tasks.values())
        print(f"\nTASKS  ({len(tasks)} total)")
        for state, count in sorted(states.items()):
            print(f"  {state:<24} {count:>4}")

        pending = [t for t in tasks.values() if t["state"] == "ESCALATED"]
        if pending:
            print(f"\nPENDING APPROVALS  ({len(pending)})")
            for t in pending:
                print(f"  [{t['task_id'][:8]}]  {t.get('intent') or t['kind']}")
                if t.get("escalation_reason"):
                    print(f"              Reason: {t['escalation_reason']}")
    else:
        print("\n  No task history found.")

    health = _warden_health()
    if health:
        print("\nWARDEN GRID")
        print(f"  CPU    {health.get('cpu_percent', '?'):>5}%")
        print(f"  Memory {health.get('memory_percent', '?'):>5}%")
        print(f"  Disk   {health.get('disk_percent', '?'):>5}%")
        incs = health.get("active_incidents", 0)
        if incs:
            print(f"  !! Active incidents: {incs}")
    else:
        print(f"\nWARDEN GRID  offline  (http://{_WARDEN_HOST}:{_WARDEN_PORT})")

    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    tasks = _load_checkpoint()
    task_id = _resolve_task_id(args.task_id, tasks)
    if task_id is None:
        print(f"ERROR: task '{args.task_id}' not found (or ambiguous).", file=sys.stderr)
        return 1

    rec = tasks[task_id]
    if rec["state"] != "ESCALATED":
        print(
            f"WARNING: task {task_id[:8]} is in state {rec['state']}, not ESCALATED.",
            file=sys.stderr,
        )

    approver = getattr(args, "approver", "sovereign")
    _write_decision({"action": "approve", "task_id": task_id, "approver": approver})
    print(f"APPROVED  [{task_id[:8]}]  {rec.get('intent') or rec['kind']}  (by {approver})")
    print("  Decision written to sovereign_decisions.jsonl — IMPERIUM will apply on next poll.")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    tasks = _load_checkpoint()
    task_id = _resolve_task_id(args.task_id, tasks)
    if task_id is None:
        print(f"ERROR: task '{args.task_id}' not found (or ambiguous).", file=sys.stderr)
        return 1

    rec = tasks[task_id]
    reason = getattr(args, "reason", "")
    approver = getattr(args, "approver", "sovereign")
    _write_decision(
        {"action": "reject", "task_id": task_id, "approver": approver, "reason": reason}
    )
    print(f"REJECTED  [{task_id[:8]}]  {rec.get('intent') or rec['kind']}  (by {approver})")
    if reason:
        print(f"  Reason: {reason}")
    return 0


def cmd_run_campaign(args: argparse.Namespace) -> int:
    import asyncio

    try:
        from pradyos.campaign.engine import CampaignEngine
        from pradyos.campaign.registry import CampaignRegistry
    except ImportError as e:
        print(f"ERROR: campaign engine unavailable: {e}", file=sys.stderr)
        return 1

    reg = CampaignRegistry()
    campaign_id: str = args.campaign_id
    campaign = reg.get(campaign_id)
    if campaign is None:
        all_c = reg.all()
        matches = [c for c in all_c if c.campaign_id.startswith(campaign_id)]
        if len(matches) == 1:
            campaign = matches[0]
        elif len(matches) > 1:
            print("ERROR: ambiguous campaign ID prefix — be more specific.", file=sys.stderr)
            return 1
        else:
            print(f"ERROR: campaign '{campaign_id}' not found.", file=sys.stderr)
            return 1

    print(f"Launching  [{campaign.campaign_id[:8]}]  {campaign.name}")
    engine = CampaignEngine()
    result = asyncio.run(engine.run_campaign(campaign))
    print(f"Status: {result.status.value}")
    if result.error:
        print(f"Error: {result.error}")
    return 0 if result.status.value == "succeeded" else 1


def cmd_list_campaigns(args: argparse.Namespace) -> int:
    try:
        from pradyos.campaign.registry import CampaignRegistry
    except ImportError as e:
        print(f"ERROR: campaign engine unavailable: {e}", file=sys.stderr)
        return 1

    reg = CampaignRegistry()
    campaigns = reg.all()

    status_filter = getattr(args, "status", None)
    if status_filter:
        campaigns = [c for c in campaigns if c.status.value == status_filter]

    if not campaigns:
        print("No campaigns found.")
        return 0

    print(f"{'ID':10}  {'NAME':30}  {'STATUS':15}  {'PROGRESS':10}")
    print("-" * 72)
    for c in sorted(campaigns, key=lambda x: x.created_at, reverse=True):
        cid = c.campaign_id[:8]
        prog = c.progress()
        total = sum(prog.values())
        pstr = f"{prog.get('succeeded', 0)}/{total}"
        print(f"{cid:10}  {c.name[:30]:30}  {c.status.value:15}  {pstr:10}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    try:
        from pradyos.campaign.scheduler import CampaignScheduler
    except ImportError as e:
        print(f"ERROR: scheduler unavailable: {e}", file=sys.stderr)
        return 1

    sched = CampaignScheduler(state_dir=_SCHEDULES.parent)
    sub = args.schedule_cmd

    if sub == "list":
        schedules = sched.list_schedules()
        if not schedules:
            print("No schedules.")
            return 0
        print(f"{'ID':10}  {'NAME':25}  {'CRON':15}  {'LAST RUN':20}  EN")
        print("-" * 80)
        for s in schedules:
            sid = s["schedule_id"][:8]
            lr = s.get("last_run")
            lrstr = time.strftime("%Y-%m-%d %H:%M", time.localtime(lr)) if lr else "never"
            en = "yes" if s.get("enabled", True) else "no"
            print(f"{sid:10}  {s['name'][:25]:25}  {s['cron']:15}  {lrstr:20}  {en}")
        return 0

    elif sub == "add":
        tasks_payload: list[Any] = []
        if getattr(args, "tasks", None):
            try:
                tasks_payload = json.loads(args.tasks)
            except json.JSONDecodeError as e:
                print(f"ERROR: --tasks must be valid JSON: {e}", file=sys.stderr)
                return 1
        try:
            sid = sched.add_schedule(
                name=args.name,
                cron=args.cron,
                intent=args.intent,
                tasks_payload=tasks_payload,
            )
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"Schedule added  [{sid[:8]}]  {args.name}  ({args.cron})")
        return 0

    elif sub == "remove":
        ok = sched.remove_schedule(args.schedule_id)
        if ok:
            print(f"Schedule removed: {args.schedule_id[:8]}")
        else:
            print(f"ERROR: schedule '{args.schedule_id}' not found.", file=sys.stderr)
            return 1
        return 0

    print(f"ERROR: unknown schedule subcommand '{sub}'", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Daemon (personal-assistant)
# ---------------------------------------------------------------------------


def cmd_daemon(args: argparse.Namespace) -> int:
    """Start the personal-assistant daemon."""
    import uvicorn

    blueprint = getattr(args, "blueprint", None)
    if blueprint:
        bp_path = _ROOT / "config" / "blueprints" / blueprint
        import yaml  # type: ignore[import-untyped]

        try:
            with bp_path.open(encoding="utf-8") as fh:
                config = yaml.safe_load(fh)
        except FileNotFoundError:
            print(f"ERROR: blueprint not found: {bp_path}", file=sys.stderr)
            return 1
    else:
        config = {"agent_name": "personal-assistant", "sovereign_policies": {}}

    from pradyos.sovereign_web import create_app

    app = create_app()
    host = getattr(args, "host", "127.0.0.1")
    port = int(getattr(args, "port", "8000"))

    print(f"Starting {config.get('agent_name', 'daemon')} on http://{host}:{port}")
    print(f"Blueprint: {blueprint or '(none)'}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pradyos-sovereign",
        description="PRADY OS SOVEREIGN -- headless command interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Decisions (approve/reject) are written to sovereign_decisions.jsonl\n"
            "and applied by the running IMPERIUM daemon within 2 seconds."
        ),
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # --- status ---
    p_st = sub.add_parser("status", help="Show live system state")
    p_st.set_defaults(func=cmd_status)

    # --- approve ---
    p_ap = sub.add_parser("approve", help="Approve an escalated task")
    p_ap.add_argument("task_id", help="Task ID or unique prefix")
    p_ap.add_argument("--approver", default="sovereign")
    p_ap.set_defaults(func=cmd_approve)

    # --- reject ---
    p_rj = sub.add_parser("reject", help="Reject an escalated task")
    p_rj.add_argument("task_id", help="Task ID or unique prefix")
    p_rj.add_argument("--reason", default="")
    p_rj.add_argument("--approver", default="sovereign")
    p_rj.set_defaults(func=cmd_reject)

    # --- run-campaign ---
    p_rc = sub.add_parser("run-campaign", help="Launch a campaign")
    p_rc.add_argument("campaign_id", help="Campaign ID or unique prefix")
    p_rc.set_defaults(func=cmd_run_campaign)

    # --- list-campaigns ---
    p_lc = sub.add_parser("list-campaigns", help="List campaigns")
    p_lc.add_argument("--status", default=None, help="Filter by status string")
    p_lc.set_defaults(func=cmd_list_campaigns)

    # --- schedule ---
    p_sc = sub.add_parser("schedule", help="Manage cron schedules")
    sc_sub = p_sc.add_subparsers(dest="schedule_cmd", metavar="SUBCOMMAND")
    sc_sub.required = True

    sc_sub.add_parser("list", help="List all schedules")

    p_add = sc_sub.add_parser("add", help="Add a cron schedule")
    p_add.add_argument("--name", required=True, help="Human-readable name")
    p_add.add_argument("--cron", required=True, help="5-field cron expression (e.g. '0 6 * * *')")
    p_add.add_argument("--intent", required=True, help="Campaign intent description")
    p_add.add_argument("--tasks", default=None, help="JSON list of task payloads (optional)")

    p_rm = sc_sub.add_parser("remove", help="Remove a schedule")
    p_rm.add_argument("schedule_id", help="Schedule ID or unique prefix")

    p_sc.set_defaults(func=cmd_schedule)

    # --- daemon ---
    p_daemon = sub.add_parser("daemon", help="Start personal-assistant daemon")
    p_daemon.add_argument("--blueprint", default="personal_assistant.yaml", help="Blueprint filename in config/blueprints/")
    p_daemon.add_argument("--host", default="127.0.0.1")
    p_daemon.add_argument("--port", default="8000")
    p_daemon.set_defaults(func=cmd_daemon)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
