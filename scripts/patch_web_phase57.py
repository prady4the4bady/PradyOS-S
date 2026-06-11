"""Patch sovereign_web.py for Phase 57: SemaphoreGate import + 5 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.timeout_guard import TimeoutGuard, TimeoutExpiredError  # Phase 56"
NEW_IMPORT = (
    "from pradyos.core.timeout_guard import TimeoutGuard, TimeoutExpiredError  # Phase 56\n"
    "from pradyos.core.semaphore_gate import SemaphoreGate, SemaphoreNotFoundError  # Phase 57"
)
if "from pradyos.core.semaphore_gate import SemaphoreGate" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 56 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 5 endpoints before `    return app` ────────────────────────────────
# Order: register /{name}/acquire and /{name}/release BEFORE the bare /{name}
# GET so the literal suffixes don't get captured as the {name} param.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/semaphores")
    async def api_semaphores_list() -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"names": [], "count": 0})
        names = semaphore_gate.list_names()
        return JSONResponse({"names": names, "count": len(names)})

    @app.post("/api/v1/semaphores")
    async def api_semaphores_create(request: Request) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "no semaphore gate configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        capacity = int(body.get("capacity", 1))
        try:
            stats = semaphore_gate.create(name=str(body["name"]), capacity=capacity)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return JSONResponse(stats.to_dict())

    @app.post("/api/v1/semaphores/{name}/acquire")
    async def api_semaphores_acquire(name: str, request: Request) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        # Default to 5s cap for HTTP safety — never block indefinitely from a web call.
        raw_timeout = body.get("timeout", 5.0)
        timeout_v = None if raw_timeout is None else float(raw_timeout)
        try:
            ok = semaphore_gate.acquire(name, timeout=timeout_v)
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "name": name,
            "acquired": bool(ok),
            "stats": stats.to_dict(),
        })

    @app.post("/api/v1/semaphores/{name}/release")
    async def api_semaphores_release(name: str) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            semaphore_gate.release(name)
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "name": name,
            "released": True,
            "stats": stats.to_dict(),
        })

    @app.get("/api/v1/semaphores/{name}")
    async def api_semaphores_get(name: str) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(stats.to_dict())

'''

if 'app.get("/api/v1/semaphores")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
