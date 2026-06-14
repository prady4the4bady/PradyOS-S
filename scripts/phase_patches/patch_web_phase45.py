"""Patch sovereign_web.py for Phase 45: ReasoningEngine import + 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.execution_engine import ExecutionEngine, ExecutionStatus  # Phase 44"
NEW_IMPORT = (
    "from pradyos.core.execution_engine import ExecutionEngine, ExecutionStatus  # Phase 44\n"
    "from pradyos.core.reasoning_engine import ReasoningEngine  # Phase 45"
)
if "ReasoningEngine" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 44 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/reason/status")
    async def api_reason_status() -> JSONResponse:
        if reasoning_engine is None:
            return JSONResponse({"rule_count": 0, "auto_approve_levels": []})
        return JSONResponse(reasoning_engine.status())

    @app.post("/api/v1/reason/rules")
    async def api_reason_add_rule(request: Request) -> JSONResponse:
        if reasoning_engine is None:
            return JSONResponse({"error": "no reasoning engine configured"}, status_code=400)
        body = await request.json()
        try:
            reasoning_engine.add_rule(body)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"rule_count": reasoning_engine.rule_count()})

    @app.post("/api/v1/reason")
    async def api_reason(request: Request) -> JSONResponse:
        if reasoning_engine is None:
            return JSONResponse({"error": "no reasoning engine configured"}, status_code=400)
        body = await request.json()
        if "goal" not in body:
            return JSONResponse({"error": "missing 'goal' key"}, status_code=400)
        plan = reasoning_engine.plan(
            goal=str(body["goal"]),
            state=body.get("state") or {},
        )
        return JSONResponse(plan.to_dict())

'''

if "/api/v1/reason/status" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
