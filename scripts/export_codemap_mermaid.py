#!/usr/bin/env python3
"""Export codemap index as a Mermaid architecture diagram.

Usage:
    python scripts/export_codemap_mermaid.py          # print to stdout
    python scripts/export_codemap_mermaid.py -o arch  # write arch.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pradyos.codemap import scan_package


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export codemap as Mermaid diagram")
    parser.add_argument("-o", "--output", help="Output file (without .md suffix)")
    args = parser.parse_args()

    index = scan_package()
    modules = index.get("modules", {})

    # Group modules by top-level package
    packages: dict[str, list[str]] = {}
    for path in sorted(modules):
        info = modules[path]
        if "error" in info:
            continue
        parts = path.split("/")
        pkg = parts[1] if len(parts) > 1 else "root"
        packages.setdefault(pkg, []).append(path)

    deps: set[tuple[str, str]] = set()
    for path, info in modules.items():
        if "error" in info:
            continue
        for dep in info.get("dependencies", []):
            for pkg in packages:
                if dep.startswith(pkg) or dep.startswith("pradyos." + pkg):
                    # Find which package this path belongs to
                    parts = path.split("/")
                    src_pkg = parts[1] if len(parts) > 1 else "root"
                    if src_pkg != pkg:
                        deps.add((src_pkg, pkg))

    lines = ["graph TD"]
    for pkg, items in sorted(packages.items()):
        label = pkg.replace("_", " ").title()
        if pkg == "root":
            label = "Root"
        loc = sum(modules[m].get("loc", 0) for m in items if "error" not in modules.get(m, {}))
        lines.append(f"  {pkg}[{label} ({len(items)} modules, {loc} LOC)]")

    for src, tgt in sorted(deps):
        lines.append(f"  {src} --> {tgt}")

    output = "\n".join(lines) + "\n"

    if args.output:
        path = Path(args.output)
        if path.suffix != ".md":
            path = path.with_suffix(".md")
        path.write_text(output, encoding="utf-8")
        print(f"Written to {path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
