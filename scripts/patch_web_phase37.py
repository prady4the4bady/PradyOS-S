"""Patch sovereign_web.py for Phase 37: add HealingMonitor import + 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.state_manager import StateManager  # Phase 36"
NEW_IMPORT = (
    "from pradyos.core.state_manager import StateManager  # Phase 36\n"
    "from pradyos.core.healing_monitor import HealingMonitor  # Phase 37"
)
if "HealingMonitor" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 36 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/healer/components")
    async def api_healer_components() -> JSONResponse:
        if healing_monitor is None:
            return JSONResponse({"components": []})
        return JSONResponse({"components": healing_monitor.list_components()})

    @app.post("/api/v1/healer/check")
    async def api_healer_check() -> JSONResponse:
        if healing_monitor is None:
            return JSONResponse({"healed": []})
        events = healing_monitor.check_and_heal()
        return JSONResponse({"healed": [e.to_dict() for e in events]})

    @app.get("/api/v1/healer/log")
    async def api_healer_log(request: Request) -> JSONResponse:
        if healing_monitor is None:
            return JSONResponse({"events": []})
        try:
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        return JSONResponse({
            "events": [e.to_dict() for e in healing_monitor.get_log(limit)],
        })

'''

if "/api/v1/healer/components" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
