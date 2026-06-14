#!/usr/bin/env python3
"""Phase 21B — Patch pradyos/sovereign_web.py.

This script performs two surgical edits:
  1. Adds `config_reloader: Any | None = None,` to create_app() signature.
  2. Inserts GET /api/v1/config/status and POST /api/v1/config/reload
     endpoints immediately before `return app`.

NEVER rewrites the file in full; never touches the DASHBOARD_HTML line.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_FILE = ROOT / "pradyos" / "sovereign_web.py"


def patch() -> None:
    original = WEB_FILE.read_text(encoding="utf-8")
    text = original

    # ------------------------------------------------------------------
    # Guard: abort if already patched
    # ------------------------------------------------------------------
    if "config_reloader" in text:
        print("Already patched — nothing to do.")
        return

    # ------------------------------------------------------------------
    # 1. Add `config_reloader` param to create_app() signature
    #    Target:   `    intent: Any | None = None,\n`
    #    Replace with same line plus the new param after it.
    # ------------------------------------------------------------------
    OLD_SIG = "    intent: Any | None = None,\n"
    NEW_SIG = (
        "    intent: Any | None = None,\n"
        "    config_reloader: Any | None = None,\n"
    )
    if OLD_SIG not in text:
        print("ERROR: could not find signature anchor.", file=sys.stderr)
        sys.exit(1)
    text = text.replace(OLD_SIG, NEW_SIG, 1)

    # ------------------------------------------------------------------
    # 2. Insert two new endpoints before `    return app`
    #    Target:   the exact string `\n    return app\n` (unique in file)
    # ------------------------------------------------------------------
    NEW_ENDPOINTS = '''
    # ── Phase 21: Sovereign Config Hot-Reload ───────────────────────────────

    @app.get("/api/v1/config/status")
    async def config_status() -> JSONResponse:
        if config_reloader is not None:
            return JSONResponse(config_reloader.status(), status_code=200)
        return JSONResponse(
            {
                "running": False,
                "config_path": None,
                "last_reload": None,
                "poll_interval": None,
            },
            status_code=200,
        )

    @app.post("/api/v1/config/reload")
    async def config_reload() -> JSONResponse:
        import time as _time
        if config_reloader is not None:
            result = config_reloader.load()
            return JSONResponse(result.to_dict(), status_code=200)
        return JSONResponse(
            {
                "success": False,
                "error": "no reloader configured",
                "changes": [],
                "timestamp": _time.time(),
            },
            status_code=200,
        )

'''
    RETURN_ANCHOR = "\n    return app\n"
    if RETURN_ANCHOR not in text:
        print("ERROR: could not find 'return app' anchor.", file=sys.stderr)
        sys.exit(1)
    text = text.replace(RETURN_ANCHOR, NEW_ENDPOINTS + "    return app\n", 1)

    # ------------------------------------------------------------------
    # Safety check: DASHBOARD_HTML line must be untouched
    # ------------------------------------------------------------------
    orig_lines = original.splitlines()
    new_lines = text.splitlines()
    dashboard_line = next(
        (ln for ln in orig_lines if "_DASHBOARD_HTML" in ln and ln.startswith("_DASHBOARD_HTML")),
        None,
    )
    if dashboard_line:
        assert dashboard_line in new_lines, "DASHBOARD_HTML line was accidentally modified!"

    WEB_FILE.write_text(text, encoding="utf-8")
    print(f"Patched {WEB_FILE} successfully.")
    print("  + config_reloader param added to create_app()")
    print("  + GET  /api/v1/config/status")
    print("  + POST /api/v1/config/reload")


if __name__ == "__main__":
    patch()
