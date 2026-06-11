"""Patch sovereign_web.py for Phase 44: ExecutionEngine import + 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.approval_queue import ApprovalQueue, ApprovalStatus  # Phase 43"
NEW_IMPORT = (
    "from pradyos.core.approval_queue import ApprovalQueue, ApprovalStatus  # Phase 43\n"
    "from pradyos.core.execution_engine import ExecutionEngine, ExecutionStatus  # Phase 44"
)
if "ExecutionEngine" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 43 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/execute/status")
    async def api_execute_status() -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({
                "allowlist": [],
                "total_runs": 0,
                "last_status": None,
            })
        return JSONResponse(execution_engine.status())

    @app.get("/api/v1/execute/history")
    async def api_execute_history(request: Request) -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({"results": []})
        try:
            limit = int(request.query_params.get("limit", 50))
        except (ValueError, TypeError):
            limit = 50
        return JSONResponse({
            "results": [r.to_dict() for r in execution_engine.history(limit)],
        })

    @app.post("/api/v1/execute/{entry_id}")
    async def api_execute_run(entry_id: str) -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({"error": "no execution engine configured"}, status_code=400)
        if approval_queue is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        entry = approval_queue.get(entry_id)
        if entry is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        result = execution_engine.run(entry)
        return JSONResponse(result.to_dict())

'''

if "/api/v1/execute/status" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
