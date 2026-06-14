#!/usr/bin/env python3
"""Phase 79 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  TDigest after the Phase 78 skiplist import.
  2. Add     `tdigest: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/tdigest endpoints immediately before `return app`.

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
OLD_IMPORT = "from pradyos.core.skiplist import SkipList  # Phase 78\n"
NEW_IMPORT = (
    "from pradyos.core.skiplist import SkipList  # Phase 78\n"
    "from pradyos.core.tdigest import TDigest  # Phase 79\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    skiplist: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    skiplist: Any | None = None,\n"
    "    tdigest: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/tdigest endpoints before `return app` ────────────────────────
TDIGEST_ROUTES = '''    @app.get("/api/v1/tdigest")
    async def api_tdigest_stats() -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        return JSONResponse(tdigest.stats())

    @app.post("/api/v1/tdigest/add")
    async def api_tdigest_add(request: Request) -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        body = await request.json()
        value = body.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return JSONResponse({"error": "value must be a number"}, status_code=422)
        weight = body.get("weight", 1)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            return JSONResponse({"error": "weight must be a positive number"}, status_code=422)
        tdigest.add(value, weight)
        return JSONResponse({"value": value, "weight": weight, "count": tdigest.count})

    @app.post("/api/v1/tdigest/percentile")
    async def api_tdigest_percentile(request: Request) -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        body = await request.json()
        q = body.get("q")
        if not isinstance(q, (int, float)) or isinstance(q, bool) or not 0.0 <= q <= 100.0:
            return JSONResponse({"error": "q must be a number in [0, 100]"}, status_code=422)
        try:
            value = tdigest.percentile(q)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"q": q, "value": value})

    @app.post("/api/v1/tdigest/merge")
    async def api_tdigest_merge(request: Request) -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        body = await request.json()
        values = body.get("values")
        if not isinstance(values, list) or not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in values
        ):
            return JSONResponse({"error": "values must be a list of numbers"}, status_code=422)
        other = TDigest()
        for entry in values:
            other.add(entry)
        merged = tdigest.merge(other)
        result = {"merged": True, "count": merged.count}
        q = body.get("q")
        if isinstance(q, (int, float)) and not isinstance(q, bool) and 0.0 <= q <= 100.0 and merged.count > 0:
            result["percentile"] = merged.percentile(q)
        return JSONResponse(result)'''

OLD_RETURN = (
    '        return JSONResponse({"lo": lo, "hi": hi, "results": [[k, v] for k, v in pairs], "count": len(pairs)})'
    '\n\n    return app'
)
NEW_RETURN = (
    '        return JSONResponse({"lo": lo, "hi": hi, "results": [[k, v] for k, v in pairs], "count": len(pairs)})'
    '\n\n\n'
    + TDIGEST_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("tdigest routes", OLD_RETURN, NEW_RETURN),
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

    if "tdigest" in original:
        print("Already patched — 'tdigest' present. Nothing to do.")
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

    if "tdigest" not in text or "/api/v1/tdigest" not in text:
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
