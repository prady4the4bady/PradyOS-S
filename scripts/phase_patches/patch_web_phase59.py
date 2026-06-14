"""Patch sovereign_web.py for Phase 59: ThrottleMap import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.event_filter import EventFilterRegistry, FilterRule  # Phase 58"
NEW_IMPORT = (
    "from pradyos.core.event_filter import EventFilterRegistry, FilterRule  # Phase 58\n"
    "from pradyos.core.throttle_map import ThrottleMap  # Phase 59"
)
if "from pradyos.core.throttle_map import ThrottleMap" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 58 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: register POST /api/v1/throttle/check BEFORE GET /api/v1/throttle/{key}
# so the literal /check segment is not captured as the {key} param.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/throttle")
    async def api_throttle_list() -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"keys": [], "count": 0})
        keys = throttle_map.list_keys()
        return JSONResponse({"keys": keys, "count": len(keys)})

    @app.post("/api/v1/throttle/check")
    async def api_throttle_check(request: Request) -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"error": "no throttle map configured"})
        body = await request.json()
        for k in ("key", "limit", "window"):
            if k not in body:
                return JSONResponse(
                    {"error": f"missing required key: {k}"},
                    status_code=400,
                )
        key = str(body["key"])
        try:
            limit = int(body["limit"])
            window = float(body["window"])
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "limit must be int and window must be float"},
                status_code=400,
            )
        allowed = throttle_map.allow(key, limit, window)
        return JSONResponse({"key": key, "allowed": bool(allowed)})

    @app.get("/api/v1/throttle/{key}")
    async def api_throttle_stats(key: str, request: Request) -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        limit_q = request.query_params.get("limit")
        window_q = request.query_params.get("window")
        if limit_q is None or window_q is None:
            return JSONResponse(
                {"error": "limit and window query params required"},
                status_code=400,
            )
        try:
            limit = int(limit_q)
            window = float(window_q)
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "limit must be int and window must be float"},
                status_code=400,
            )
        stats = throttle_map.stats(key, limit, window)
        if stats is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(stats)

    @app.delete("/api/v1/throttle/{key}")
    async def api_throttle_delete(key: str) -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = throttle_map.delete(key)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if 'app.get("/api/v1/throttle")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
