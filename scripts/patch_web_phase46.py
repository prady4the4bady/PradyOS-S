"""Patch sovereign_web.py for Phase 46: WebAgent import + 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.reasoning_engine import ReasoningEngine  # Phase 45"
NEW_IMPORT = (
    "from pradyos.core.reasoning_engine import ReasoningEngine  # Phase 45\n"
    "from pradyos.core.web_agent import WebAgent  # Phase 46"
)
if "WebAgent" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 45 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/web/status")
    async def api_web_status() -> JSONResponse:
        if web_agent is None:
            return JSONResponse({
                "cache_enabled": False,
                "guardrail_enabled": False,
                "max_age": 3600,
                "timeout": 10,
            })
        return JSONResponse(web_agent.status())

    @app.get("/api/v1/web/fetch")
    async def api_web_fetch(url: str) -> JSONResponse:
        if web_agent is None:
            return JSONResponse({"error": "no web agent configured"}, status_code=400)
        result = web_agent.fetch(url)
        return JSONResponse(result.to_dict())

    @app.post("/api/v1/web/search")
    async def api_web_search(request: Request) -> JSONResponse:
        if web_agent is None:
            return JSONResponse({"error": "no web agent configured"}, status_code=400)
        body = await request.json()
        if "query" not in body:
            return JSONResponse({"error": "missing 'query' key"}, status_code=400)
        max_results = int(body.get("max_results", 5))
        results = web_agent.search(query=str(body["query"]), max_results=max_results)
        return JSONResponse({"results": [r.to_dict() for r in results]})

'''

if "/api/v1/web/status" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
