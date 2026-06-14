"""Patch sovereign_web.py for Phase 52: LockManager import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.statesync import StateSyncManager  # Phase 51"
NEW_IMPORT = (
    "from pradyos.core.statesync import StateSyncManager  # Phase 51\n"
    "from pradyos.core.distributed_lock import LockManager  # Phase 52"
)
if "from pradyos.core.distributed_lock import LockManager" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 51 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order matters: register /{name}/refresh BEFORE /{name} so the literal
# /refresh suffix doesn't get parsed as a generic name.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/locks")
    async def api_locks_list() -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"locks": [], "count": 0})
        locks = lock_manager.list_locks()
        return JSONResponse({"locks": locks, "count": len(locks)})

    @app.post("/api/v1/locks")
    async def api_locks_acquire(request: Request) -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"error": "no lock manager configured"}, status_code=400)
        body = await request.json()
        for key in ("name", "holder_id"):
            if key not in body:
                return JSONResponse(
                    {"error": f"missing required key: {key}"},
                    status_code=400,
                )
        ttl = float(body.get("ttl", 30))
        lock = lock_manager.acquire(
            name=str(body["name"]),
            holder_id=str(body["holder_id"]),
            ttl=ttl,
        )
        if lock is None:
            return JSONResponse({"error": "already locked"}, status_code=409)
        return JSONResponse(lock.to_dict())

    @app.post("/api/v1/locks/{name}/refresh")
    async def api_locks_refresh(name: str, request: Request) -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        if "holder_id" not in body:
            return JSONResponse(
                {"error": "missing required key: holder_id"},
                status_code=400,
            )
        ttl = float(body.get("ttl", 30))
        ok = lock_manager.refresh(name=name, holder_id=str(body["holder_id"]), ttl=ttl)
        if not ok:
            return JSONResponse({"error": "not found or wrong holder"}, status_code=404)
        return JSONResponse({"refreshed": True})

    @app.delete("/api/v1/locks/{name}")
    async def api_locks_release(name: str, holder_id: str) -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = lock_manager.release(name=name, holder_id=holder_id)
        if not ok:
            return JSONResponse({"error": "not found or wrong holder"}, status_code=404)
        return JSONResponse({"released": True})

'''

if 'app.get("/api/v1/locks")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
