#!/usr/bin/env python3
"""Phase 70 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  DependencyGraph + CycleError after the Phase 69 anomaly import.
  2. Add     `dependency_graph: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/deps endpoints immediately before `return app`.

All file I/O uses newline='' so existing LF line endings are preserved verbatim
(no accidental CRLF translation on Windows). Each anchor must occur exactly once;
the script aborts loudly on any mismatch, asserts the DASHBOARD_HTML line is left
untouched, and finally re-parses the file with ``ast`` so a broken patch can
never be written out (exit 1 on any failure).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_FILE = ROOT / "pradyos" / "sovereign_web.py"


# ── Edit 1: import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.anomaly_detector import AnomalyDetector  # Phase 69\n"
NEW_IMPORT = (
    "from pradyos.core.anomaly_detector import AnomalyDetector  # Phase 69\n"
    "from pradyos.core.dependency_graph import DependencyGraph, CycleError  # Phase 70\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    anomaly_detector: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    anomaly_detector: Any | None = None,\n"
    "    dependency_graph: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/deps endpoints before `return app` ───────────────────────────
DEPS_ROUTES = '''    @app.get("/api/v1/deps/{node}")
    async def api_deps_get(node: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        return JSONResponse(dependency_graph.describe(node))

    @app.post("/api/v1/deps")
    async def api_deps_post(request: Request) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        body = await request.json()
        frm = body.get("from")
        to = body.get("to")
        if not frm or not to:
            return JSONResponse({"error": "both 'from' and 'to' are required"}, status_code=422)
        dependency_graph.add_dependency(frm, to)
        return JSONResponse({"from": frm, "to": to, "added": True})

    @app.delete("/api/v1/deps/{frm}/{to}")
    async def api_deps_delete(frm: str, to: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        removed = dependency_graph.remove_dependency(frm, to)
        return JSONResponse({"from": frm, "to": to, "removed": removed})

    @app.get("/api/v1/deps/{node}/sort")
    async def api_deps_sort(node: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        try:
            order = dependency_graph.topological_sort(node)
        except CycleError as exc:
            return JSONResponse({"error": "cycle detected", "cycle": exc.cycle}, status_code=409)
        return JSONResponse({"node": node, "order": order})

    @app.get("/api/v1/deps/{node}/impact")
    async def api_deps_impact(node: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        return JSONResponse({"node": node, "impact_score": dependency_graph.impact_score(node)})'''

OLD_RETURN = '        d["cached"] = False\n        return JSONResponse(d)\n\n    return app'
NEW_RETURN = (
    '        d["cached"] = False\n        return JSONResponse(d)\n\n\n'
    + DEPS_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("deps routes", OLD_RETURN, NEW_RETURN),
]


def _dashboard_line_len(text: str) -> int:
    for line in text.split("\n"):
        if line.startswith("_DASHBOARD_HTML = "):
            return len(line)
    print("ERROR: could not locate _DASHBOARD_HTML line.", file=sys.stderr)
    sys.exit(1)


def patch() -> None:
    with open(WEB_FILE, "r", newline="") as fh:
        original = fh.read()

    if "dependency_graph" in original:
        print("Already patched — 'dependency_graph' present. Nothing to do.")
        return

    if "\r" in original:
        print("ERROR: file already contains CR bytes — refusing to patch.", file=sys.stderr)
        sys.exit(1)

    dash_len_before = _dashboard_line_len(original)
    lines_before = original.count("\n")
    expected_delta = 0

    text = original
    for name, old, new in EDITS:
        occurrences = text.count(old)
        if occurrences != 1:
            print(f"ERROR: anchor '{name}' found {occurrences} times (expected 1).",
                  file=sys.stderr)
            sys.exit(1)
        text = text.replace(old, new, 1)
        expected_delta += new.count("\n") - old.count("\n")

    # ── Integrity assertions ────────────────────────────────────────────────────
    lines_after = text.count("\n")
    actual_delta = lines_after - lines_before
    if actual_delta != expected_delta:
        print(f"ERROR: line-count delta {actual_delta} != expected {expected_delta}.",
              file=sys.stderr)
        sys.exit(1)

    if "\r" in text:
        print("ERROR: patch introduced CR bytes — aborting.", file=sys.stderr)
        sys.exit(1)

    dash_len_after = _dashboard_line_len(text)
    if dash_len_after != dash_len_before:
        print(f"ERROR: _DASHBOARD_HTML line length changed "
              f"({dash_len_before} -> {dash_len_after}).", file=sys.stderr)
        sys.exit(1)

    if "dependency_graph" not in text or "/api/v1/deps" not in text:
        print("ERROR: expected content missing after patch.", file=sys.stderr)
        sys.exit(1)

    # ── Syntax gate: never write a file that won't parse ─────────────────────────
    try:
        ast.parse(text)
    except SyntaxError as exc:
        print(f"ERROR: patched text fails to parse: {exc}", file=sys.stderr)
        sys.exit(1)

    with open(WEB_FILE, "w", newline="") as fh:
        fh.write(text)

    # Re-verify the file as written on disk.
    try:
        ast.parse(WEB_FILE.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        print(f"ERROR: written file fails to parse: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Patched pradyos/sovereign_web.py successfully.")
    print(f"  lines: {lines_before} -> {lines_after} (+{actual_delta})")
    print(f"  _DASHBOARD_HTML line length unchanged: {dash_len_after}")


if __name__ == "__main__":
    patch()
