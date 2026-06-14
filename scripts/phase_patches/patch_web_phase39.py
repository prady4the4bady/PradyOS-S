"""Patch sovereign_web.py for Phase 39: add MemoryStore import + 5 endpoints.

Route order matters in FastAPI: register /search and /expire BEFORE /{key}
so they aren't captured as path params.
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.scheduler import TaskScheduler as CoreTaskScheduler  # Phase 38"
NEW_IMPORT = (
    "from pradyos.core.scheduler import TaskScheduler as CoreTaskScheduler  # Phase 38\n"
    "from pradyos.core.memory_store import MemoryStore  # Phase 39"
)
if "MemoryStore" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 38 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 5 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/memory/search")
    async def api_memory_search(request: Request) -> JSONResponse:
        tag = request.query_params.get("tag")
        if memory_store is None or not tag:
            return JSONResponse({"entries": []})
        return JSONResponse({
            "entries": [e.to_dict() for e in memory_store.search(tag)],
        })

    @app.post("/api/v1/memory/expire")
    async def api_memory_expire() -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"expired": 0})
        return JSONResponse({"expired": memory_store.expire()})

    @app.post("/api/v1/memory/{key}")
    async def api_memory_store(key: str, request: Request) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "no memory store configured"})
        body = await request.json()
        entry = memory_store.store(
            key=key,
            value=body["value"],
            tags=body.get("tags") or [],
            ttl=body.get("ttl"),
        )
        return JSONResponse(entry.to_dict())

    @app.get("/api/v1/memory/{key}")
    async def api_memory_recall(key: str) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        entry = memory_store.recall(key)
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry.to_dict())

    @app.delete("/api/v1/memory/{key}")
    async def api_memory_forget(key: str) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = memory_store.forget(key)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if "/api/v1/memory/search" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
