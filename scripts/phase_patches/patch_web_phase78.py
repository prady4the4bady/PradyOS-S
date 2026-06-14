#!/usr/bin/env python3
"""Phase 78 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  SkipList after the Phase 77 merkle_tree import.
  2. Add     `skiplist: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/skiplist endpoints immediately before `return app`.

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
OLD_IMPORT = "from pradyos.core.merkle_tree import MerkleTree  # Phase 77\n"
NEW_IMPORT = (
    "from pradyos.core.merkle_tree import MerkleTree  # Phase 77\n"
    "from pradyos.core.skiplist import SkipList  # Phase 78\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    merkle_tree: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    merkle_tree: Any | None = None,\n"
    "    skiplist: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/skiplist endpoints before `return app` ───────────────────────
SKIPLIST_ROUTES = '''    @app.get("/api/v1/skiplist")
    async def api_skiplist_stats() -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        return JSONResponse(skiplist.stats())

    @app.post("/api/v1/skiplist/insert")
    async def api_skiplist_insert(request: Request) -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        body = await request.json()
        key = body.get("key")
        if not isinstance(key, str) or not key:
            return JSONResponse({"error": "key is required"}, status_code=422)
        skiplist.insert(key, body.get("value"))
        return JSONResponse({"key": key, "value": body.get("value"), "size": len(skiplist)})

    @app.post("/api/v1/skiplist/search")
    async def api_skiplist_search(request: Request) -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        body = await request.json()
        key = body.get("key")
        if not isinstance(key, str) or not key:
            return JSONResponse({"error": "key is required"}, status_code=422)
        value = skiplist.search(key)
        return JSONResponse({"key": key, "value": value, "found": key in skiplist})

    @app.post("/api/v1/skiplist/range")
    async def api_skiplist_range(request: Request) -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        body = await request.json()
        lo = body.get("lo")
        hi = body.get("hi")
        if not isinstance(lo, str) or not isinstance(hi, str):
            return JSONResponse({"error": "lo and hi are required strings"}, status_code=422)
        pairs = skiplist.range_query(lo, hi)
        return JSONResponse({"lo": lo, "hi": hi, "results": [[k, v] for k, v in pairs], "count": len(pairs)})'''

OLD_RETURN = (
    '        return JSONResponse({"item": item, "proof": path, "root": merkle_tree.root})'
    '\n\n    return app'
)
NEW_RETURN = (
    '        return JSONResponse({"item": item, "proof": path, "root": merkle_tree.root})'
    '\n\n\n'
    + SKIPLIST_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("skiplist routes", OLD_RETURN, NEW_RETURN),
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

    if "skiplist" in original:
        print("Already patched — 'skiplist' present. Nothing to do.")
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

    if "skiplist" not in text or "/api/v1/skiplist" not in text:
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
