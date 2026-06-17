#!/usr/bin/env python3
"""Codemap Demo — structural self-knowledge of own code.

Scans the pradyos/ package tree and prints a summary of modules,
functions, classes, and dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.codemap import scan_package


def main() -> None:
    print("PradySovereign Codemap Demo")
    print("=" * 50)

    index = scan_package()
    modules = index.get("modules", {})
    total = index.get("total_modules", 0)

    print(f"\nScanned {total} Python modules.\n")

    total_funcs = 0
    total_classes = 0
    total_methods = 0
    total_loc = 0

    for path, info in sorted(modules.items()):
        if "error" in info:
            print(f"  [ERR] {path} — {info['error']}")
            continue
        funcs = len(info.get("functions", []))
        classes = len(info.get("classes", []))
        methods = len(info.get("methods", []))
        loc = info.get("loc", 0)
        deps = len(info.get("dependencies", []))
        total_funcs += funcs
        total_classes += classes
        total_methods += methods
        total_loc += loc

        desc = f"{funcs} fn, {classes} cls, {methods} mtd, {deps} dep"
        print(f"  {path:<55} {desc:>25} ({loc} LOC)")

    print(f"\n{'-' * 60}")
    print(f"  Total: {total} modules, {total_funcs} functions, "
          f"{total_classes} classes, {total_methods} methods, {total_loc} LOC")
    print(f"\nDemo complete. The agent can now introspect its own structure.")


if __name__ == "__main__":
    main()
