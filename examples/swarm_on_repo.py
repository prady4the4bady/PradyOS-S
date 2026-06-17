#!/usr/bin/env python3
"""PradySovereign — Dev Swarm on Its Own Repo.

Opinionated: the guild swarm introspects PradyOS's own source tree via the
codemap, then produces a team analysis of architecture, strengths, and gaps.
Dogfooding the framework for the HN demo.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.codemap import scan_package
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


def _swarm_worker(role: Any, objective: str, context: list[dict]) -> str:
    """Context-aware fake worker that answers based on real repo data injected
    in the objective."""
    replies = {
        "planner": (
            "1. Map all top-level packages and their responsibilities\n"
            "2. Identify architectural layers (core, guild, skills, web, dev_api)\n"
            "3. Assess test coverage per package\n"
            "4. Surface unused or dead code paths\n"
            "5. Recommend consolidation opportunities"
        ),
        "researcher": (
            "Repository structure: guild/ (multi-agent orchestration), "
            "skills/ (self-improving library), core/ (probabilistic data structures), "
            "codemap/ (AST introspection), examples/ (demo scripts), "
            "config/ (blueprints), scripts/ (build/test infra). "
            "The Dev API (dev_api/__init__.py) presents SkillEngine, GuildSwarm, "
            "and SovereignClient as a clean public surface."
        ),
        "engineer": (
            "Architecture: layered monolith with gated egress. "
            "Core primitives (BloomFilter, MinHash, HyperLogLog, TDigest, "
            "CountSketch, NoveltyDetector, AnalogyEngine, CompressionController) "
            "are thread-safe via threading.RLock. GuildOrg provides deterministic "
            "multi-agent blackboard orchestration. Codemap uses AST analysis for "
            "structural self-knowledge."
        ),
        "analyst": (
            "Strengths: deterministic core (testable without LLM), thread-safe, "
            "self-healing skills (Laplace-smoothed confidence, automatic pruning), "
            "structural self-introspection. Risks: no async runtime for core ops, "
            "no distributed execution, single-machine state."
        ),
        "critic": (
            "Gap: the codemap plane is read-only -- it cannot detect behavioral "
            "coupling (which functions call which across packages). "
            "Gap: no runtime dependency graph (imports are static). "
            "Gap: the Dev API's add_agent is a no-op. Fix it or remove it. "
            "Nice-to-have: hot-reload for blueprints."
        ),
        "synthesizer": (
            "PradySovereign is a well-layered agent OS: probabilistic core, "
            "deterministic guild, self-improving skills, structural self-knowledge. "
            "The Dev API is a clean facade ready for HN. "
            "Top recommendation: ship the critic's gaps as GitHub issues, "
            "then write a real LLM-driven example that chains codemap -> guild -> skill."
        ),
    }
    return replies.get(role.name, "Acknowledged.")


def main() -> None:
    print()
    print(f"  {BOLD}PradySovereign -- The Swarm That Eats Itself{RESET}")
    print(f"  {DIM}A guild of 6 agents analyses this repo through the codemap lens.{RESET}")
    print()

    # ── Gather real repo data via codemap ──────────────────────────────
    index = scan_package()
    modules = index.get("modules", {})
    total_mod = index.get("total_modules", 0)
    total_fn = sum(len(m.get("functions", [])) for m in modules.values() if "error" not in m)
    total_cls = sum(len(m.get("classes", [])) for m in modules.values() if "error" not in m)
    total_mtd = sum(len(m.get("methods", [])) for m in modules.values() if "error" not in m)
    total_loc = sum(m.get("loc", 0) for m in modules.values() if "error" not in m)
    total_dep = sum(len(m.get("dependencies", [])) for m in modules.values() if "error" not in m)

    # Top-10 largest files
    sized = sorted(
        [(p, m.get("loc", 0), len(m.get("functions", [])))
         for p, m in modules.items() if "error" not in m],
        key=lambda t: -t[1],
    )[:10]

    print(f"  {BOLD}Repo snapshot (codemap){RESET}")
    print(f"  {DIM}{'-' * 50}{RESET}")
    print(f"    Modules:    {total_mod}")
    print(f"    Functions:  {total_fn}")
    print(f"    Classes:    {total_cls}")
    print(f"    Methods:    {total_mtd}")
    print(f"    Dependencies: {total_dep}")
    print(f"    Total LOC:  {total_loc}")
    print(f"  {DIM}{'-' * 50}{RESET}")
    print(f"  Top-10 by LOC:")
    for p, loc, fn in sized:
        short = Path(p).as_posix()
        print(f"    {short:<55} {loc:>6} LOC  ({fn} functions)")
    print()

    # ── Launch the swarm ───────────────────────────────────────────────
    objective = (
        f"Analyse the PradySovereign codebase: {total_mod} modules, "
        f"{total_fn} functions, {total_cls} classes, {total_mtd} methods, "
        f"{total_loc} LOC across the package tree. "
        "Identify architectural layers, assess test coverage patterns, "
        "surface consolidation opportunities, and recommend next steps "
        "for the HN launch."
    )

    print(f"  {BOLD}Swarm analysis{RESET}")
    print(f"  {DIM}{'-' * 50}{RESET}")

    swarm = GuildSwarm(worker=_swarm_worker)
    sovereign = SovereignClient()

    t0 = time.monotonic()
    result = swarm.run_task(objective)
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
        "task": "swarm_on_repo",
        "outcome": result.get("status", "unknown"),
        "codemap": {"modules": total_mod, "functions": total_fn, "loc": total_loc},
    })

    print()
    print(f"  {BOLD}{'-' * 50}{RESET}")
    print(f"  Status: {GREEN}{result.get('status')}{RESET}  |  "
          f"Roles: {len(result.get('contributions', []))}  |  "
          f"Time: {elapsed:.2f}s  |  "
          f"LOC analysed: {total_loc}")
    print()


if __name__ == "__main__":
    main()
