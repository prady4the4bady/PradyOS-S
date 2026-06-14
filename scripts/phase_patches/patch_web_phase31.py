"""Patch sovereign_web.py for Phase 31: add signal_aggregator param and 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.watchpoint import WatchpointSystem  # Phase 30"
NEW_IMPORT = (
    "from pradyos.core.watchpoint import WatchpointSystem  # Phase 30\n"
    "from pradyos.core.signal_aggregator import SignalAggregator  # Phase 31"
)
if "SignalAggregator" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 30 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add signal_aggregator param to create_app() ────────────────────────────
OLD_PARAM = "    watchpoint_system: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    watchpoint_system: Any | None = None,\n"
    "    signal_aggregator: Any | None = None,\n"
    ") -> FastAPI:"
)
if "signal_aggregator" not in src:
    assert OLD_PARAM in src, "Could not find create_app param anchor"
    src = src.replace(OLD_PARAM, NEW_PARAM, 1)

# ── 3. Add 3 new endpoints before `return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/signals")
    async def api_signals_list() -> JSONResponse:
        if signal_aggregator is None:
            return JSONResponse({"signals": []})
        return JSONResponse({"signals": signal_aggregator.list_signals()})

    @app.post("/api/v1/signals")
    async def api_signals_record(request: Request) -> JSONResponse:
        if signal_aggregator is None:
            return JSONResponse({"error": "no signal aggregator configured"})
        body = await request.json()
        pt = signal_aggregator.record(
            name=body["name"],
            value=float(body["value"]),
            timestamp=body.get("timestamp"),
        )
        return JSONResponse(pt.to_dict())

    @app.get("/api/v1/signals/{name}")
    async def api_signals_get(name: str, request: Request) -> JSONResponse:
        if signal_aggregator is None:
            return JSONResponse({"name": name, "points": [], "count": 0, "stats": None})
        try:
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        points = signal_aggregator.get(name, limit=limit)
        return JSONResponse({
            "name": name,
            "points": [pt.to_dict() for pt in points],
            "count": len(points),
            "stats": signal_aggregator.stats(name),
        })

'''

if "/api/v1/signals" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
