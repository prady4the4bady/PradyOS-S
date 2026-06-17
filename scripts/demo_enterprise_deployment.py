#!/usr/bin/env python3
"""Enterprise Deployment Demo — PradySovereign Enterprise Mode.

Simulates a multi-agent fleet deployment based on the enterprise blueprint:
  - loads blueprint
  - deploys replicas of the enterprise agent interactively
  - uses Sovereign approvals for each deployment step
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.dev_api import GuildSwarm, SovereignClient


def load_blueprint(path: str) -> dict[str, Any]:
    import yaml  # type: ignore[import-untyped]
    bp = Path(__file__).resolve().parent.parent / "config" / "blueprints" / path
    with bp.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def fake_worker(role: Any, objective: str, context: list[dict]) -> str:
    replies = {
        "planner": "1. Check auth logs\n2. Review file permissions\n3. Scan open ports\n4. Report findings",
        "researcher": "Found 3 stale sudo entries and port 8443 exposed on internal interface.",
        "engineer": "Patch applied: removed sudo entries, restricted port 8443 to localhost.",
        "analyst": "Risk: medium. No active exploits but reduces attack surface by 40%.",
        "critic": "Approved. All changes are reversible and within policy.",
        "synthesizer": "Security audit complete: 2 findings remediated, 1 accepted risk.",
    }
    return replies.get(role.name, "Acknowledged.")


def main() -> None:
    bp_path = Path(__file__).resolve().parent.parent / "config" / "blueprints" / "enterprise_agent.yaml"
    if not bp_path.is_file():
        print(f"FATAL: blueprint not found at {bp_path}", file=sys.stderr)
        sys.exit(1)

    print("[SOVEREIGN] PradySovereign Enterprise Mode -- Blueprint Deployment")
    print("=" * 60)

    sovereign = SovereignClient()
    blueprint = load_blueprint("enterprise_agent.yaml")
    print(f"\n  [SOVEREIGN] Blueprint: {blueprint['agent_name']} v{blueprint.get('version', '?')}")
    print(f"  [SOVEREIGN] Fleet replicas: {blueprint['agent_fleet']['replicas']}")
    print(f"  [SOVEREIGN] Roles: {', '.join(blueprint['agent_fleet']['roles'])}")
    print(f"  [SOVEREIGN] Double approval: {blueprint['sovereign_policies'].get('require_double_approval', False)}")

    # Deploy each replica (simulate approval per replica)
    print("\n  [SOVEREIGN] --- Deploying agent fleet ---")
    for i in range(blueprint["agent_fleet"]["replicas"]):
        print(f"\n  [SOVEREIGN] [Replica {i+1}] Proposing deployment ...")
        proposal = sovereign.submit_proposal({
            "action": "deploy_agent",
            "blueprint": blueprint["agent_name"],
            "replica": i + 1,
            "roles": blueprint["agent_fleet"]["roles"],
        })
        print(f"    Proposed: {proposal}")

        time.sleep(0.1)
        sovereign.log_decision({
            "action": "approve_deployment",
            "replica": i + 1,
        })
        print("    Approved (logged to Decision Journal)")

    # Run a fleet task via GuildSwarm
    print("\n  [SOVEREIGN] --- Running fleet task ---")
    swarm = GuildSwarm(worker=fake_worker)
    result = swarm.run_task(
        "Audit system security: check logs, verify permissions, report vulnerabilities."
    )
    for contrib in result.get("contributions", []):
        print(f"\n    [{contrib['role'].upper()}]")
        print(f"    {contrib['content']}")

    print(f"\n    [DONE]")
    print(f"    {result.get('synthesis', 'N/A')}")
    print(f"\n  [SOVEREIGN] Fleet task status: {result.get('status', 'unknown')}")
    print(f"  [SOVEREIGN] Enterprise deployment complete. All decisions logged.")


if __name__ == "__main__":
    main()
