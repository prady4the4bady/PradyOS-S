#!/usr/bin/env python3
"""Phase 105 — Patch pradyos/sovereign_web.py (additive, surgical).

The Q-Digest routes live in ``pradyos/web/qdigest_web.py``; this patch wires them
into the factory. Three additive edits, none of which rewrite the file or touch
the DASHBOARD_HTML line:
  1. Import  register_qdigest_routes after the Phase 104 augmentedsketch import.
  2. Add     `qdigest: Any | None = None,` to create_app() signature.
  3. Insert  `register_qdigest_routes(app, qdigest)` immediately before
             `return app` (the digest lives in factory scope — no module state).

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
OLD_IMPORT = "from pradyos.web.augmentedsketch_web import register_augmentedsketch_routes  # Phase 104\n"
NEW_IMPORT = (
    "from pradyos.web.augmentedsketch_web import register_augmentedsketch_routes  # Phase 104\n"
    "from pradyos.web.qdigest_web import register_qdigest_routes  # Phase 105\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    augmented_sketch: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    augmented_sketch: Any | None = None,\n"
    "    qdigest: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: register the q-digest router before `return app` ─────────────────────
OLD_RETURN = "    register_augmentedsketch_routes(app, augmented_sketch)\n\n    return app"
NEW_RETURN = (
    "    register_augmentedsketch_routes(app, augmented_sketch)\n\n"
    "    register_qdigest_routes(app, qdigest)\n\n"
    "    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("q-digest router wiring", OLD_RETURN, NEW_RETURN),
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

    if "register_qdigest_routes" in original:
        print("Already patched — 'register_qdigest_routes' present. Nothing to do.")
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

    if "register_qdigest_routes" not in text:
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
