#!/usr/bin/env python3
"""Personal Assistant — PradySovereign Local Mode demo.

Simulates an end-to-day workflow: read inbox → summarise → propose calendar
event → send draft reply — all with Sovereign approval logging.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.dev_api import SovereignClient


# ── Fake data sources ─────────────────────────────────────────────────────
INBOX = [
    {"from": "alice@example.com", "subject": "Project update", "body": "The API refactor landed. CI green. Ready for review."},
    {"from": "bob@example.com", "subject": "Meeting reminder", "body": "Don't forget the design review at 2pm tomorrow."},
    {"from": "carol@example.com", "subject": "Bug report", "body": "Login page crashes when session expires. Severity: high."},
]

CALENDAR = [
    {"title": "Design Review", "time": "tomorrow 14:00", "duration": "1h"},
]


def main() -> None:
    bp = Path(__file__).resolve().parent.parent / "config" / "blueprints" / "personal_assistant.yaml"
    if not bp.is_file():
        print(f"FATAL: blueprint not found at {bp}", file=sys.stderr)
        sys.exit(1)

    print("[SOVEREIGN] PradySovereign Personal Assistant -- Local Mode Demo")
    print("=" * 55)

    sovereign = SovereignClient()

    # 1. Read & summarise inbox
    print("\n  [SOVEREIGN] [1/3] Reading inbox...")
    for msg in INBOX:
        summary = f"[{msg['from']}] {msg['subject']}: {msg['body'][:60]}..."
        sovereign.log_decision({
            "action": "summarise",
            "source": msg["from"],
            "subject": msg["subject"],
            "summary": summary,
        })
        print(f"    Logged: {msg['from']} - {msg['subject']}")

    # 2. Propose calendar event
    print("\n  [SOVEREIGN] [2/3] Proposing calendar events...")
    for event in CALENDAR:
        proposal = sovereign.submit_proposal({
            "type": "calendar",
            "title": event["title"],
            "time": event["time"],
            "duration": event["duration"],
            "reasoning": f"Schedule {event['title']} to align the team on scope.",
        })
        if proposal.get("approved", True):
            print(f"    Approved: {event['title']} at {event['time']}")
        else:
            print(f"    Pending Sovereign review: {event['title']}")

    # 3. Draft reply
    print("\n  [SOVEREIGN] [3/3] Drafting replies...")
    draft = f"Dear Carol,\n\nThanks for the report. We'll prioritize the session-expiry fix in the next sprint.\n\nBest,\nPersonal Assistant"
    sovereign.log_decision({
        "action": "draft_reply",
        "to": "carol@example.com",
        "subject": "Re: Bug report",
        "draft": draft,
    })
    print("    Draft logged via SovereignClient.")

    print(f"\n  [SOVEREIGN] Demo complete. {len(INBOX)} messages summarised, 1 event proposed, 1 draft logged.")
    print("  [SOVEREIGN] All actions recorded in the Decision Journal.")


if __name__ == "__main__":
    main()
