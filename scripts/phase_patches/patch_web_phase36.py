"""Patch sovereign_web.py for Phase 36: add StateManager import + 5 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.reactor import ReactorEngine  # Phase 35"
NEW_IMPORT = (
    "from pradyos.core.reactor import ReactorEngine  # Phase 35\n"
    "from pradyos.core.state_manager import StateManager  # Phase 36"
)
if "StateManager" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 35 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 5 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.post("/api/v1/os/shutdown")
    async def api_os_shutdown(request: Request) -> JSONResponse:
        if state_manager is None:
            return JSONResponse({"results": [], "message": "no state manager"})
        results = state_manager.shutdown()
        return JSONResponse({"results": results})

    @app.get("/api/v1/os/state/{module}")
    async def api_os_state_list(module: str) -> JSONResponse:
        if state_manager is None or state_manager._store is None:
            return JSONResponse({"module": module, "keys": []})
        return JSONResponse({
            "module": module,
            "keys": state_manager._store.list_keys(module),
        })

    @app.get("/api/v1/os/state/{module}/{key}")
    async def api_os_state_get(module: str, key: str, request: Request) -> JSONResponse:
        if state_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        raw = request.query_params.get("version")
        version = int(raw) if raw is not None else None
        result = state_manager.load_state(module, key, version=version)
        if result is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(result)

    @app.post("/api/v1/os/state/{module}/{key}")
    async def api_os_state_save(module: str, key: str, request: Request) -> JSONResponse:
        if state_manager is None or state_manager._store is None:
            return JSONResponse({"error": "no state manager configured"})
        body = await request.json()
        result = state_manager.save_state(module, key, body["data"])
        return JSONResponse(result)

    @app.get("/api/v1/os/status")
    async def api_os_status() -> JSONResponse:
        if state_manager is None:
            return JSONResponse({
                "store_connected": False,
                "registered_modules": [],
                "hook_count": 0,
            })
        return JSONResponse(state_manager.status())

'''

if "/api/v1/os/shutdown" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
