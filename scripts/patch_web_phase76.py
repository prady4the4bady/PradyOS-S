#!/usr/bin/env python3
"""Phase 76 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  CountMinSketch after the Phase 75 vectorclock import.
  2. Add     `countminsketch: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/frequency endpoints immediately before `return app`.

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
OLD_IMPORT = "from pradyos.core.vectorclock import VectorClock  # Phase 75\n"
NEW_IMPORT = (
    "from pradyos.core.vectorclock import VectorClock  # Phase 75\n"
    "from pradyos.core.countminsketch import CountMinSketch  # Phase 76\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    vectorclock: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    vectorclock: Any | None = None,\n"
    "    countminsketch: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/frequency endpoints before `return app` ──────────────────────
FREQUENCY_ROUTES = '''    @app.get("/api/v1/frequency")
    async def api_frequency_stats() -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        return JSONResponse(countminsketch.stats())

    @app.post("/api/v1/frequency/add")
    async def api_frequency_add(request: Request) -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        count = body.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return JSONResponse({"error": "count must be a positive integer"}, status_code=422)
        countminsketch.add(item, count)
        return JSONResponse({"item": item, "count": count, "estimate": countminsketch.estimate(item)})

    @app.post("/api/v1/frequency/estimate")
    async def api_frequency_estimate(request: Request) -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        return JSONResponse({"item": item, "estimate": countminsketch.estimate(item)})

    @app.post("/api/v1/frequency/merge")
    async def api_frequency_merge(request: Request) -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        body = await request.json()
        items = body.get("items")
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            return JSONResponse({"error": "items must be a list of strings"}, status_code=422)
        other = CountMinSketch(countminsketch.width, countminsketch.depth)
        for entry in items:
            other.add(entry)
        merged = countminsketch.merge(other)
        result = {"merged": True, "total": merged.stats()["total"]}
        query = body.get("item")
        if isinstance(query, str) and query:
            result["estimate"] = merged.estimate(query)
        return JSONResponse(result)'''

OLD_RETURN = (
    '        return JSONResponse({"relation": relation})'
    '\n\n    return app'
)
NEW_RETURN = (
    '        return JSONResponse({"relation": relation})'
    '\n\n\n'
    + FREQUENCY_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("frequency routes", OLD_RETURN, NEW_RETURN),
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

    if "countminsketch" in original:
        print("Already patched — 'countminsketch' present. Nothing to do.")
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

    if "countminsketch" not in text or "/api/v1/frequency" not in text:
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
