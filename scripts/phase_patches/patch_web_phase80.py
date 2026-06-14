#!/usr/bin/env python3
"""Phase 80 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  FenwickTree after the Phase 79 tdigest import.
  2. Add     `fenwick: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/fenwick endpoints immediately before `return app`.

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
OLD_IMPORT = "from pradyos.core.tdigest import TDigest  # Phase 79\n"
NEW_IMPORT = (
    "from pradyos.core.tdigest import TDigest  # Phase 79\n"
    "from pradyos.core.fenwick import FenwickTree  # Phase 80\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    tdigest: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    tdigest: Any | None = None,\n"
    "    fenwick: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/fenwick endpoints before `return app` ────────────────────────
FENWICK_ROUTES = '''    @app.get("/api/v1/fenwick")
    async def api_fenwick_stats() -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        return JSONResponse(fenwick.stats())

    @app.post("/api/v1/fenwick/update")
    async def api_fenwick_update(request: Request) -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        body = await request.json()
        try:
            fenwick.update(body.get("index"), body.get("delta"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"index": body.get("index"), "delta": body.get("delta"), "total": fenwick.stats()["total"]})

    @app.post("/api/v1/fenwick/query")
    async def api_fenwick_query(request: Request) -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        body = await request.json()
        try:
            total = fenwick.range_sum(body.get("lo"), body.get("hi"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"lo": body.get("lo"), "hi": body.get("hi"), "sum": total})

    @app.post("/api/v1/fenwick/point")
    async def api_fenwick_point(request: Request) -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        body = await request.json()
        try:
            value = fenwick.point_query(body.get("index"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"index": body.get("index"), "value": value})'''

OLD_RETURN = (
    '        return JSONResponse(result)'
    '\n\n    return app'
)
NEW_RETURN = (
    '        return JSONResponse(result)'
    '\n\n\n'
    + FENWICK_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("fenwick routes", OLD_RETURN, NEW_RETURN),
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

    if "fenwick" in original:
        print("Already patched — 'fenwick' present. Nothing to do.")
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

    if "fenwick" not in text or "/api/v1/fenwick" not in text:
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
