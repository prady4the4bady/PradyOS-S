"""Patch sovereign_web.py for Phase 33: add correlation_engine param and 2 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.snapshot_store import SnapshotStore  # Phase 32"
NEW_IMPORT = (
    "from pradyos.core.snapshot_store import SnapshotStore  # Phase 32\n"
    "from pradyos.core.correlation_engine import CorrelationEngine  # Phase 33"
)
if "CorrelationEngine" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 32 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 2 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/correlate")
    async def api_correlate_get(request: Request) -> JSONResponse:
        if correlation_engine is None:
            return JSONResponse({"error": "no correlation engine configured"})
        sa = request.query_params.get("signal_a")
        sb = request.query_params.get("signal_b")
        if not sa or not sb:
            return JSONResponse({"error": "signal_a and signal_b are required"})
        try:
            window = float(request.query_params.get("window", 3600))
        except (ValueError, TypeError):
            window = 3600.0
        result = correlation_engine.correlate(sa, sb, window_secs=window)
        return JSONResponse(result.to_dict())

    @app.post("/api/v1/correlate")
    async def api_correlate_post(request: Request) -> JSONResponse:
        if correlation_engine is None:
            return JSONResponse({"error": "no correlation engine configured"})
        body = await request.json()
        sa = body.get("signal_a")
        sb = body.get("signal_b")
        if not sa or not sb:
            return JSONResponse({"error": "signal_a and signal_b are required"})
        window = float(body.get("window", 3600))
        result = correlation_engine.correlate(sa, sb, window_secs=window)
        return JSONResponse(result.to_dict())

'''

if "/api/v1/correlate" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
