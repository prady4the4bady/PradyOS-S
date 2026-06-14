#!/usr/bin/env python3
"""Phase 74 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  HyperLogLog after the Phase 73 hash_ring import.
  2. Add     `hyperloglog: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/cardinality endpoints immediately before `return app`.

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
OLD_IMPORT = "from pradyos.core.hash_ring import HashRing, NodeNotFoundError  # Phase 73\n"
NEW_IMPORT = (
    "from pradyos.core.hash_ring import HashRing, NodeNotFoundError  # Phase 73\n"
    "from pradyos.core.hyperloglog import HyperLogLog  # Phase 74\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    hash_ring: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    hash_ring: Any | None = None,\n"
    "    hyperloglog: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/cardinality endpoints before `return app` ────────────────────
CARDINALITY_ROUTES = '''    @app.get("/api/v1/cardinality")
    async def api_cardinality_stats() -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        return JSONResponse(hyperloglog.stats())

    @app.post("/api/v1/cardinality/add")
    async def api_cardinality_add(request: Request) -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        body = await request.json()
        if "items" in body:
            items = body.get("items")
            if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                return JSONResponse({"error": "items must be a list of strings"}, status_code=422)
        elif "item" in body:
            item = body.get("item")
            if not isinstance(item, str):
                return JSONResponse({"error": "item must be a string"}, status_code=422)
            items = [item]
        else:
            return JSONResponse({"error": "item or items is required"}, status_code=422)
        hyperloglog.add_many(items)
        return JSONResponse({"added": len(items), "estimate": hyperloglog.estimate()})

    @app.get("/api/v1/cardinality/estimate")
    async def api_cardinality_estimate() -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        return JSONResponse({"estimate": hyperloglog.estimate()})

    @app.delete("/api/v1/cardinality")
    async def api_cardinality_clear() -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        hyperloglog.clear()
        return JSONResponse({"cleared": True})'''

OLD_RETURN = (
    '        return JSONResponse({"node": node, "removed": True})'
    '\n\n    return app'
)
NEW_RETURN = (
    '        return JSONResponse({"node": node, "removed": True})'
    '\n\n\n'
    + CARDINALITY_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("cardinality routes", OLD_RETURN, NEW_RETURN),
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

    if "hyperloglog" in original:
        print("Already patched — 'hyperloglog' present. Nothing to do.")
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

    if "hyperloglog" not in text or "/api/v1/cardinality" not in text:
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
