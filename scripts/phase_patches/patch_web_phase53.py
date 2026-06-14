"""Patch sovereign_web.py for Phase 53: CircuitBreaker import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.distributed_lock import LockManager  # Phase 52"
NEW_IMPORT = (
    "from pradyos.core.distributed_lock import LockManager  # Phase 52\n"
    "from pradyos.core.circuit_breaker import CircuitBreaker, BreakerState  # Phase 53"
)
if "from pradyos.core.circuit_breaker import CircuitBreaker" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 52 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order matters: /{name}/reset must be declared BEFORE /{name} so the literal
# /reset suffix isn't captured as part of the breaker name.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/breakers")
    async def api_breakers_list() -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"breakers": [], "count": 0})
        return JSONResponse({
            "breakers": circuit_breaker.list_breakers(),
            "count": circuit_breaker.count(),
        })

    @app.post("/api/v1/breakers")
    async def api_breakers_register(request: Request) -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"error": "no circuit breaker configured"}, status_code=400)
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        name = str(body["name"])
        # Ensure breaker state exists by triggering create-or-get.
        with circuit_breaker._lock:
            bs = circuit_breaker._get_or_create_locked(name)
        return JSONResponse(bs.to_dict())

    @app.post("/api/v1/breakers/{name}/reset")
    async def api_breakers_reset(name: str) -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = circuit_breaker.reset(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"reset": True})

    @app.get("/api/v1/breakers/{name}")
    async def api_breakers_get(name: str) -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        bs = circuit_breaker.get_state(name)
        if bs is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(bs.to_dict())

'''

if 'app.get("/api/v1/breakers")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
