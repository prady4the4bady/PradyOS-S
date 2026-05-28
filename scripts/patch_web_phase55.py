"""Patch sovereign_web.py for Phase 55: BulkheadManager import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.retry_policy import RetryPolicy  # Phase 54"
NEW_IMPORT = (
    "from pradyos.core.retry_policy import RetryPolicy  # Phase 54\n"
    "from pradyos.core.bulkhead_pool import BulkheadManager, BulkheadRejectedError  # Phase 55"
)
if "from pradyos.core.bulkhead_pool import BulkheadManager" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 54 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: register /{name}/submit BEFORE /{name} so the literal `/submit`
# doesn't get parsed as a pool name.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/bulkheads")
    async def api_bulkheads_list() -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"pools": []})
        return JSONResponse({"pools": bulkhead_manager.list_pools()})

    @app.post("/api/v1/bulkheads")
    async def api_bulkheads_create(request: Request) -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"error": "no bulkhead manager configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        try:
            pool = bulkhead_manager.create(
                name=str(body["name"]),
                max_workers=int(body.get("max_workers", 4)),
                queue_depth=int(body.get("queue_depth", 8)),
            )
        except ValueError:
            return JSONResponse({"error": "pool already exists"})
        return JSONResponse(pool.get_stats().to_dict())

    @app.post("/api/v1/bulkheads/{name}/submit")
    async def api_bulkheads_submit(name: str, request: Request) -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        pool = bulkhead_manager.get(name)
        if pool is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        sleep_s = float(body.get("sleep", 0.0))

        import time as _time

        def _no_op() -> str:
            if sleep_s > 0:
                _time.sleep(sleep_s)
            return "ok"

        try:
            pool.submit(_no_op)
        except BulkheadRejectedError:
            return JSONResponse(
                {
                    "name": name,
                    "submitted": False,
                    "error": "BulkheadRejectedError",
                },
                status_code=429,
            )
        return JSONResponse({
            "name": name,
            "submitted": True,
            "stats": pool.get_stats().to_dict(),
        })

    @app.get("/api/v1/bulkheads/{name}")
    async def api_bulkheads_get(name: str) -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        pool = bulkhead_manager.get(name)
        if pool is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(pool.get_stats().to_dict())

'''

if 'app.get("/api/v1/bulkheads")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
