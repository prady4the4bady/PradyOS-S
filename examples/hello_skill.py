#!/usr/bin/env python3
"""Hello World — PradySovereign Dev Mode skill example.

Registers a "SummariseIssue" skill and runs it against a fake GitHub issue.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.dev_api import SkillEngine


def main() -> None:
    engine = SkillEngine()

    skill = engine.register_skill(
        "SummariseIssue",
        "Summarise a GitHub issue into title, description, and labels.",
        tools=["read_issue", "extract_labels"],
    )
    print(f"Registered skill: {skill['name']} (id={skill['id']})")

    result = engine.run_skill("SummariseIssue")
    print(f"\nSkill definition:")
    print(f"  Name:     {result['name']}")
    print(f"  Trigger:  {result['trigger']}")
    print(f"  Steps:    {result['steps']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"\nDemo complete. Skill '{result['name']}' is ready for LLM execution.")


if __name__ == "__main__":
    main()
