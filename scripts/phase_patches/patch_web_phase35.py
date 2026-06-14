"""Patch sovereign_web.py for Phase 35: add ReactorEngine import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.integration_bus import SovereignBus  # Phase 34"
NEW_IMPORT = (
    "from pradyos.core.integration_bus import SovereignBus  # Phase 34\n"
    "from pradyos.core.reactor import ReactorEngine  # Phase 35"
)
if "ReactorEngine" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 34 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/reactor/rules")
    async def api_reactor_rules_list() -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"rules": []})
        return JSONResponse({"rules": reactor_engine.list_rules()})

    @app.post("/api/v1/reactor/rules")
    async def api_reactor_rules_add(request: Request) -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"error": "no reactor configured"})
        body = await request.json()
        rule = reactor_engine.add_rule(
            decision_type=body["decision_type"],
            action=body["action"],
            context_filter=body.get("context_filter"),
        )
        return JSONResponse(rule.to_dict())

    @app.delete("/api/v1/reactor/rules/{rule_id}")
    async def api_reactor_rules_delete(rule_id: str) -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = reactor_engine.remove_rule(rule_id)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/reactor/log")
    async def api_reactor_log(request: Request) -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"reactions": []})
        try:
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        return JSONResponse({
            "reactions": [r.to_dict() for r in reactor_engine.get_log(limit)],
        })

'''

if "/api/v1/reactor/rules" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
