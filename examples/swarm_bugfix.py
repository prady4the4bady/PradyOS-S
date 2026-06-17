#!/usr/bin/env python3
"""PradySovereign Dev Mode — Swarm Bugfix.

Six specialist agents collaborate on a blackboard to fix a production bug.
No LLM required: the fake_worker shows the orchestration pattern.
Swap in an OllamaGuildWorker for real AI.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.dev_api import GuildSwarm, SovereignClient

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
RESET = "\033[0m"


ROLE_ICONS = {
    "planner": "STRAT",
    "researcher": "FACT",
    "engineer": "CODE",
    "analyst": "RISK",
    "critic": "FLAW",
    "synthesizer": "SYNTH",
}


def fake_worker(role: Any, objective: str, context: list[dict]) -> str:
    replies = {
        "planner": (
            "1. Isolate the input path that routes password chars\n"
            "2. Trace the SQL construction to find the injection point\n"
            "3. Apply parameterised queries in the login handler\n"
            "4. Add test cases for all special-character permutations\n"
            "5. Roll out with a feature flag"
        ),
        "researcher": (
            "OWASP ASVS V2.1.1 requires parameterised queries for all user input. "
            "CWE-89 (SQL Injection) classified as HIGH severity. "
            "The password field bypasses the existing sanitizer because "
            "special chars are URL-encoded after validation."
        ),
        "engineer": (
            "Fix: replace string interpolation in auth/login.py:44 with "
            "cursor.execute('SELECT * FROM users WHERE name = ? AND pass = ?', "
            "(uname, pwd_hash)). The password hash column already uses SHA-256. "
            "Add input length check > 128 chars => 400."
        ),
        "analyst": (
            "Impact: auth bypass on accounts with special-char passwords (~12 % of users). "
            "Fix cost: 1 hour dev + 30 min test + 15 min deploy. "
            "Regression risk: LOW — the change is isolated to one query in one handler. "
            "Monitoring: add 500-rate alert on /auth/login."
        ),
        "critic": (
            "Risk: the fix does not address secondary injection via the username field. "
            "Recommend auditing all 5 query sites in auth/ for the same pattern. "
            "Also: the length check should be at the form-parse layer, not in the query builder."
        ),
        "synthesizer": (
            "Fix: parameterise auth/login.py:44. Audit remaining 4 query sites in auth/. "
            "Add length check at form-parse layer. Add 500 alert. "
            "Test: 12 special-char passwords + empty + max-length + Unicode. "
            "Rollout: feature-flag behind canary, monitor 30 min, then 100 %."
        ),
    }
    return replies.get(role.name, "Acknowledged.")


def main() -> None:
    swarm = GuildSwarm(worker=fake_worker)
    sovereign = SovereignClient()

    bug = "User login fails with 500 error when password contains special characters."

    print()
    print(f"  {BOLD}PradySovereign Swarm Bugfix{RESET}")
    print(f"  {DIM}A guild of 6 specialist agents collaborates on a production bug.{RESET}")
    print()
    print(f"  {YELLOW}Objective:{RESET} {bug}")
    print()
    print(f"  {BOLD}{'=' * 55}{RESET}")

    t0 = time.monotonic()
    result = swarm.run_task(bug)
    elapsed = time.monotonic() - t0

    for contrib in result.get("contributions", []):
        role = contrib["role"]
        icon = ROLE_ICONS.get(role, "AGNT")
        print()
        print(f"  [{BOLD}{MAGENTA}{icon}{RESET}] {CYAN}{role.upper()}{RESET}")
        for line in contrib["content"].strip().split("\n"):
            print(f"     {line.strip()}")

    print()
    print(f"  [{BOLD}{GREEN}DONE{RESET}] {CYAN}SYNTHESIS{RESET}")
    for line in result.get("synthesis", "").strip().split("\n"):
        print(f"     {line.strip()}")

    sovereign.log_decision({
        "action": "log",
        "task": "swarm_bugfix",
        "outcome": result.get("status", "unknown"),
        "synthesis": result.get("synthesis", ""),
    })

    print()
    print(f"  {BOLD}{'=' * 55}{RESET}")
    print(f"  Status: {GREEN}{result.get('status')}{RESET}  |  "
          f"Roles: {len(result.get('contributions', []))}  |  "
          f"Time: {elapsed:.2f}s")
    print(f"  {DIM}Decision logged via SovereignClient -> var/state/sovereign_decisions.jsonl{RESET}")
    print()


if __name__ == "__main__":
    main()
