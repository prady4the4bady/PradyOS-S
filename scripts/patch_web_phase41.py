"""Patch sovereign_web.py for Phase 41: HeartbeatLoop import + lifecycle + 2 endpoints.

Uses @app.on_event("startup"/"shutdown") to keep the existing FastAPI() call
unchanged (lifespan injection would require rewriting that line).
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.control_plane import ControlPlane, VERSION as OS_VERSION  # Phase 40"
NEW_IMPORT = (
    "from pradyos.core.control_plane import ControlPlane, VERSION as OS_VERSION  # Phase 40\n"
    "from pradyos.core.heartbeat import HeartbeatLoop  # Phase 41"
)
if "HeartbeatLoop" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 40 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add lifecycle hooks + 2 endpoints before `    return app` ──────────────
NEW_CODE = '''
    @app.on_event("startup")
    async def _heartbeat_startup() -> None:
        if heartbeat is not None:
            await heartbeat.start()

    @app.on_event("shutdown")
    async def _heartbeat_shutdown() -> None:
        if heartbeat is not None:
            await heartbeat.stop()

    @app.get("/api/v1/heartbeat/status")
    async def api_heartbeat_status() -> JSONResponse:
        if heartbeat is None:
            return JSONResponse({
                "running": False,
                "tick_count": 0,
                "interval_seconds": 0,
            })
        return JSONResponse(heartbeat.status())

    @app.post("/api/v1/heartbeat/stop")
    async def api_heartbeat_stop() -> JSONResponse:
        if heartbeat is None:
            return JSONResponse({"stopped": False})
        await heartbeat.stop()
        return JSONResponse({"stopped": True})

'''

if "/api/v1/heartbeat/status" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_CODE + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
