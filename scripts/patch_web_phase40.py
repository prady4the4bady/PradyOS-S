"""Patch sovereign_web.py for Phase 40: ControlPlane import + 2 endpoints.

DEVIATION: Phase 36 already owns GET /api/v1/os/status (returns state_manager
status). To preserve Phase 36 tests, Phase 40 uses GET /api/v1/os/control for
the unified ControlPlane status. POST /api/v1/os/tick is new and unconflicted.
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.memory_store import MemoryStore  # Phase 39"
NEW_IMPORT = (
    "from pradyos.core.memory_store import MemoryStore  # Phase 39\n"
    "from pradyos.core.control_plane import ControlPlane, VERSION as OS_VERSION  # Phase 40"
)
if "ControlPlane" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 39 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 2 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/os/control")
    async def api_os_control() -> JSONResponse:
        if control_plane is None:
            return JSONResponse({
                "os_version": OS_VERSION,
                "uptime_seconds": 0,
                "modules": {},
            })
        return JSONResponse(control_plane.status())

    @app.post("/api/v1/os/tick")
    async def api_os_tick() -> JSONResponse:
        if control_plane is None:
            return JSONResponse({"ticks": [], "healed": [], "reactions": []})
        return JSONResponse(control_plane.tick())

'''

if "/api/v1/os/control" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
