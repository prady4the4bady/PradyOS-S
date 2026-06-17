#!/usr/bin/env python3
"""PradySovereign Dev Mode — Hello Skill.

A self-improving skill engine in four lines of real work.
Run it. Read it. Steal it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.dev_api import SkillEngine

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RESET = "\033[0m"


def main() -> None:
    engine = SkillEngine()

    print()
    print(f"  {BOLD}PradySovereign Skill Engine — Quickstart{RESET}")
    print(f"  {DIM}Teach the engine a skill. Use it instantly. Watch it get better.{RESET}")
    print()

    # ── 1. LEARN ──────────────────────────────────────────────────────────
    print(f"  {YELLOW}1. Learn{RESET}  {DIM}Register a new skill from experience{RESET}")

    skill = engine.register_skill(
        "SummariseIssue",
        "Summarise a GitHub issue into title, description, and labels.",
        tools=["read_issue", "extract_labels", "classify_category"],
    )

    sid = skill["id"]
    print(f"     Skill     {CYAN}{skill['name']}{RESET}")
    print(f"     ID        {DIM}{sid}{RESET}")
    print(f"     Steps     {', '.join(skill['steps'])}")
    print(f"     Version   {skill['version']}")
    print(f"     Confidence {skill['confidence']}  {DIM}(prior, 0 evidence yet){RESET}")
    print()

    # ── 2. RUN ────────────────────────────────────────────────────────────
    print(f"  {YELLOW}2. Run{RESET}   {DIM}Execute the skill retrieves plan + confidence{RESET}")

    result = engine.run_skill("SummariseIssue")
    print(f"     Name:      {CYAN}{result['name']}{RESET}")
    print(f"     Trigger:   {result['trigger']}")
    print(f"     Steps:     {', '.join(result['steps'])}")
    print(f"     Confidence: {result['confidence']}")
    print()

    # ── 3. REINFORCE ──────────────────────────────────────────────────────
    print(f"  {YELLOW}3. Reinforce{RESET}  {DIM}Tell the engine it worked -> confidence goes up{RESET}")

    engine._lib.reinforce(sid, success=True, example="Fixed #42: added input validation")
    engine._lib.reinforce(sid, success=True, example="Fixed #99: null check before render")
    engine._lib.reinforce(sid, success=False, example="#107: misunderstood — not a summarisation issue")

    stats = engine.stats()
    reinforced = engine._lib.recall(sid)
    print(f"     Confidence now: {GREEN}{reinforced['confidence']}{RESET}  {DIM}(2 success + 1 failure, Laplace-smoothed){RESET}")
    print(f"     Library:  {stats['skills']} skill(s), {stats['proven']} proven, {stats['total_attempts']} total attempts")
    print()

    # ── 4. MATCH ──────────────────────────────────────────────────────────
    print(f"  {YELLOW}4. Match{RESET}  {DIM}Ask the engine: \"what skill fits 'summarize github label issue'?\"{RESET}")

    matches = engine._lib.match("summarize github label issue")
    for m in matches:
        print(f"     {GREEN}{m['name']}{RESET}  overlap={m['match_overlap']}  confidence={m['confidence']}  {DIM}matched terms: {m['matched_terms']}{RESET}")

    print()
    print(f"  {MAGENTA}Done.{RESET}  {DIM}One skill, registered, run, reinforced, and matched -- four primitives.{RESET}")
    print()


if __name__ == "__main__":
    main()
