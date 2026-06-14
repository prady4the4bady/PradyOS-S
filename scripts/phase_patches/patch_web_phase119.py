#!/usr/bin/env python3
"""Phase 119 — Patch pradyos/sovereign_web.py (additive, surgical).

The Rendezvous Hashing routes live in ``pradyos/web/rendezvous_web.py``; this patch
wires them into the factory. Three additive edits, none of which rewrite the file or
touch the DASHBOARD_HTML line:
  1. Import  register_rendezvous_routes after the Phase 118 scalable bloom import.
  2. Add     `rendezvous: Any | None = None,` to create_app() signature.
  3. Insert  `register_rendezvous_routes(app, rendezvous)` immediately before
             `return app` (the ring lives in factory scope — no module state).

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
OLD_IMPORT = "from pradyos.web.scalable_bloom_web import register_scalablebloom_routes  # Phase 118\n"
NEW_IMPORT = (
    "from pradyos.web.scalable_bloom_web import register_scalablebloom_routes  # Phase 118\n"
    "from pradyos.web.rendezvous_web import register_rendezvous_routes  # Phase 119\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    scalable_bloom: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    scalable_bloom: Any | None = None,\n"
    "    rendezvous: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: register the rendezvous router before `return app` ───────────────────
OLD_RETURN = "    register_scalablebloom_routes(app, scalable_bloom)\n\n    return app"
NEW_RETURN = (
    "    register_scalablebloom_routes(app, scalable_bloom)\n\n"
    "    register_rendezvous_routes(app, rendezvous)\n\n"
    "    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("rendezvous router wiring", OLD_RETURN, NEW_RETURN),
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

    if "register_rendezvous_routes" in original:
        print("Already patched — 'register_rendezvous_routes' present. Nothing to do.")
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

    if "register_rendezvous_routes" not in text:
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
