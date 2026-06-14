"""Patch sovereign_web.py for Phase 49: TaskQueue import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.event_store import EventStore  # Phase 48"
NEW_IMPORT = (
    "from pradyos.core.event_store import EventStore  # Phase 48\n"
    "from pradyos.core.task_queue import TaskQueue  # Phase 49"
)
if "from pradyos.core.task_queue import TaskQueue" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 48 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.post("/api/v1/tasks")
    async def api_tasks_submit(request: Request) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"error": "no task queue configured"}, status_code=400)
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing 'name' key"}, status_code=400)
        task = task_queue.submit(
            name=str(body["name"]),
            payload=body.get("payload") or {},
            priority=int(body.get("priority", 5)),
        )
        return JSONResponse(task.to_dict())

    @app.get("/api/v1/tasks")
    async def api_tasks_list(request: Request) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"tasks": [], "count": 0})
        status = request.query_params.get("status")
        tasks = task_queue.list_tasks(status=status)
        return JSONResponse({
            "tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
        })

    @app.get("/api/v1/tasks/{task_id}")
    async def api_tasks_get(task_id: str) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        task = task_queue.get(task_id)
        if task is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(task.to_dict())

    @app.delete("/api/v1/tasks/{task_id}")
    async def api_tasks_cancel(task_id: str) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        task = task_queue.get(task_id)
        if task is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        cancelled = task_queue.cancel(task_id)
        if not cancelled:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"cancelled": True})

'''

if "/api/v1/tasks\"" not in src and "/api/v1/tasks\"" not in src:
    # use a more reliable check based on the actual route definitions
    if 'app.post("/api/v1/tasks")' not in src:
        assert "    return app" in src, "Could not find 'return app' anchor"
        src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
