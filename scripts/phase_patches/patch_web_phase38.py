"""Patch sovereign_web.py for Phase 38: add TaskScheduler import + 4 endpoints.

Uses distinct names from the existing pradyos.sovereign.scheduler (Phase 15):
  - Import: pradyos.core.scheduler.TaskScheduler (alias as CoreTaskScheduler
    to avoid colliding with a possible existing scheduler symbol).
  - Endpoints: /api/v1/scheduler/tasks, /api/v1/scheduler/tick (distinct
    from the existing /api/v1/scheduler/jobs endpoints).
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.healing_monitor import HealingMonitor  # Phase 37"
NEW_IMPORT = (
    "from pradyos.core.healing_monitor import HealingMonitor  # Phase 37\n"
    "from pradyos.core.scheduler import TaskScheduler as CoreTaskScheduler  # Phase 38"
)
if "CoreTaskScheduler" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 37 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/scheduler/tasks")
    async def api_scheduler_tasks_list() -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"tasks": []})
        return JSONResponse({"tasks": task_scheduler.list_tasks()})

    @app.post("/api/v1/scheduler/tasks")
    async def api_scheduler_tasks_add(request: Request) -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"error": "no scheduler configured"})
        body = await request.json()
        task = task_scheduler.register(
            name=body["name"],
            interval_seconds=float(body["interval_seconds"]),
            fn=lambda: None,
        )
        return JSONResponse(task.to_dict())

    @app.delete("/api/v1/scheduler/tasks/{name}")
    async def api_scheduler_tasks_delete(name: str) -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = task_scheduler.unregister(name)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.post("/api/v1/scheduler/tick")
    async def api_scheduler_tick() -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"runs": []})
        runs = task_scheduler.tick()
        return JSONResponse({"runs": [r.to_dict() for r in runs]})

'''

if "/api/v1/scheduler/tasks" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
