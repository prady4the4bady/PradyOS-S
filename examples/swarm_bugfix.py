#!/usr/bin/env python3
"""Swarm Bugfix — PradySovereign Dev Mode multi-agent example.

Simulates a bug-fix workflow through a guild of specialist agents.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.dev_api import GuildSwarm, SovereignClient


# ── Fake worker that simulates role contributions ───────────────────────────
def fake_worker(role: Any, objective: str, context: list[dict]) -> str:
    """Deterministic fake responses for each role — no LLM required."""
    replies = {
        "planner": "1. Locate the bug in module x\n2. Apply the fix\n3. Add tests\n4. Review",
        "coder": "def fix(): return 'patched'",
        "tester": "Tests pass: all 5 assertions green.",
        "critic": "Risk: low. The fix is isolated and well-tested.",
    }
    return replies.get(role.name, "Acknowledged.")


def main() -> None:
    print("PradySovereign Swarm Bugfix Demo")
    print("=" * 40)

    swarm = GuildSwarm(worker=fake_worker)
    sovereign = SovereignClient()

    bug = "User login fails with 500 error when password contains special characters."

    print(f"\nBug description: {bug}")
    print("\n--- Swarm Execution Trace ---")

    result = swarm.run_task(bug)

    for contrib in result.get("contributions", []):
        print(f"\n  [{contrib['role'].upper()}]")
        print(f"    {contrib['content']}")

    print(f"\n  [SYNTHESIS]")
    print(f"    {result.get('synthesis', 'N/A')}")

    sovereign.log_decision({
        "action": "log",
        "task": "swarm_bugfix",
        "outcome": result.get("status", "unknown"),
        "synthesis": result.get("synthesis", ""),
    })
    print(f"\n  Status: {result.get('status')}")
    print(f"\nDemo complete. Execution trace logged via SovereignClient.")


if __name__ == "__main__":
    main()
