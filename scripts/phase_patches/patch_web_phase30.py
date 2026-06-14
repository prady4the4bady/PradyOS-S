"""Patch sovereign_web.py for Phase 30: add watchpoint_system param and 3 endpoints."""
import re
import sys
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.capability_registry import CapabilityRegistry  # Phase 29"
NEW_IMPORT = (
    "from pradyos.core.capability_registry import CapabilityRegistry  # Phase 29\n"
    "from pradyos.core.watchpoint import WatchpointSystem  # Phase 30"
)
if "WatchpointSystem" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 29 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add watchpoint_system param to create_app() ────────────────────────────
OLD_PARAM = "    capability_registry: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    capability_registry: Any | None = None,\n"
    "    watchpoint_system: Any | None = None,\n"
    ") -> FastAPI:"
)
if "watchpoint_system" not in src:
    assert OLD_PARAM in src, "Could not find create_app param anchor"
    src = src.replace(OLD_PARAM, NEW_PARAM, 1)

# ── 3. Add 3 new endpoints before `return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/watchpoints")
    async def api_watchpoints_get() -> JSONResponse:
        if watchpoint_system is None:
            return JSONResponse({"watchpoints": [], "status": {}})
        return JSONResponse({
            "watchpoints": [w.to_dict() for w in watchpoint_system.get_watchpoints()],
            "status": watchpoint_system.status(),
        })

    @app.post("/api/v1/watchpoints")
    async def api_watchpoints_post(request: Request) -> JSONResponse:
        if watchpoint_system is None:
            return JSONResponse({"error": "no watchpoint system configured"})
        body = await request.json()
        wp = watchpoint_system.register(
            name=body["name"],
            metric=body["metric"],
            operator=body["operator"],
            threshold=float(body["threshold"]),
            severity=body.get("severity", "warn"),
            enabled=bool(body.get("enabled", True)),
        )
        return JSONResponse(wp.to_dict())

    @app.post("/api/v1/watchpoints/check")
    async def api_watchpoints_check(request: Request) -> JSONResponse:
        if watchpoint_system is None:
            return JSONResponse({"alerts": [], "count": 0})
        body = await request.json()
        fired = watchpoint_system.check(
            metric=body["metric"],
            value=float(body["value"]),
        )
        return JSONResponse({"alerts": [a.to_dict() for a in fired], "count": len(fired)})

'''

if "/api/v1/watchpoints" not in src:
    assert "    return app\n" in src or "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
