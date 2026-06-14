#!/usr/bin/env python3
"""Phase 73 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  HashRing + NodeNotFoundError after the Phase 72 bloom_filter import.
  2. Add     `hash_ring: Any | None = None,` to create_app() signature.
  3. Insert  the /api/v1/hashring endpoints immediately before `return app`.

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
OLD_IMPORT = "from pradyos.core.bloom_filter import BloomFilter  # Phase 72\n"
NEW_IMPORT = (
    "from pradyos.core.bloom_filter import BloomFilter  # Phase 72\n"
    "from pradyos.core.hash_ring import HashRing, NodeNotFoundError  # Phase 73\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    bloom_filter: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    bloom_filter: Any | None = None,\n"
    "    hash_ring: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: /api/v1/hashring endpoints before `return app` ───────────────────────
HASHRING_ROUTES = '''    @app.get("/api/v1/hashring")
    async def api_hashring_stats() -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        return JSONResponse(hash_ring.stats())

    @app.post("/api/v1/hashring/nodes")
    async def api_hashring_add(request: Request) -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        body = await request.json()
        node = body.get("node")
        if not node or not isinstance(node, str):
            return JSONResponse({"error": "node is required"}, status_code=422)
        hash_ring.add_node(node)
        return JSONResponse({"node": node, "added": True, "nodes": hash_ring.nodes()})

    @app.get("/api/v1/hashring/node/{key}")
    async def api_hashring_get(key: str) -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        return JSONResponse({"key": key, "node": hash_ring.get_node(key)})

    @app.delete("/api/v1/hashring/nodes/{node}")
    async def api_hashring_remove(node: str) -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        try:
            hash_ring.remove_node(node)
        except NodeNotFoundError:
            return JSONResponse({"error": f"no such node: {node}"}, status_code=404)
        return JSONResponse({"node": node, "removed": True})'''

OLD_RETURN = (
    '        return JSONResponse({"cleared": True})'
    '\n\n    return app'
)
NEW_RETURN = (
    '        return JSONResponse({"cleared": True})'
    '\n\n\n'
    + HASHRING_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("hashring routes", OLD_RETURN, NEW_RETURN),
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

    if "hash_ring" in original:
        print("Already patched — 'hash_ring' present. Nothing to do.")
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

    if "hash_ring" not in text or "/api/v1/hashring" not in text:
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
