"""Patch script — Phase 25: wire AuditReplayEngine into sovereign_web.py."""
import pathlib
import re
import sys

WEB = pathlib.Path("pradyos/sovereign_web.py")
src = WEB.read_text(encoding="utf-8")

# ── 1. Add replay_engine param to create_app() signature ──────────────────
OLD_SIG = "    scorecard: Any | None = None,\n) -> FastAPI:"
NEW_SIG = (
    "    scorecard: Any | None = None,\n"
    "    replay_engine: Any | None = None,\n"
    ") -> FastAPI:"
)
assert OLD_SIG in src, "ERROR: scorecard param anchor not found"
src = src.replace(OLD_SIG, NEW_SIG, 1)

# ── 2. Add import for time (already present) and AuditReplayEngine import ──
# Insert after the existing 'from pradyos.core.ledger import EventLedger' line
OLD_IMPORT = "from pradyos.core.ledger import EventLedger"
NEW_IMPORT = (
    "from pradyos.core.ledger import EventLedger\n"
    "from pradyos.core.audit_replay import AuditReplayEngine  # Phase 25"
)
# Only add if not already present
if "audit_replay" not in src:
    assert OLD_IMPORT in src, "ERROR: ledger import anchor not found"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 3. Insert /api/v1/audit/replay endpoint before `return app` ───────────
OLD_RETURN = "    return app\n"
NEW_ENDPOINT = """\
    @app.get("/api/v1/audit/replay")
    async def api_audit_replay(at: float | None = None) -> JSONResponse:
        import time as _time
        ts = at if at is not None else _time.time()
        if replay_engine is None:
            return JSONResponse(
                {"at": ts, "entries": [], "state": {}, "event_count": 0}
            )
        return JSONResponse(replay_engine.replay(ts).to_dict())

    return app
"""
assert OLD_RETURN in src, "ERROR: 'return app' anchor not found"
# Replace only the LAST occurrence of `    return app\n` (inside create_app)
idx = src.rfind(OLD_RETURN)
src = src[:idx] + NEW_ENDPOINT + src[idx + len(OLD_RETURN):]

WEB.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
