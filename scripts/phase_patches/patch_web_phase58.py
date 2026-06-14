"""Patch sovereign_web.py for Phase 58: EventFilterRegistry import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.semaphore_gate import SemaphoreGate, SemaphoreNotFoundError  # Phase 57"
NEW_IMPORT = (
    "from pradyos.core.semaphore_gate import SemaphoreGate, SemaphoreNotFoundError  # Phase 57\n"
    "from pradyos.core.event_filter import EventFilterRegistry, FilterRule  # Phase 58"
)
if "from pradyos.core.event_filter import EventFilterRegistry" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 57 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: register POST /{name}/apply BEFORE GET/DELETE /{name} so the literal
# /apply segment is never captured as a name parameter.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/filters")
    async def api_filters_list() -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"names": [], "count": 0})
        names = event_filter_registry.list_names()
        return JSONResponse({"names": names, "count": len(names)})

    @app.post("/api/v1/filters")
    async def api_filters_create(request: Request) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "no filter registry configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        mode = str(body.get("mode", "AND"))
        if mode not in ("AND", "OR"):
            return JSONResponse({"error": "mode must be AND or OR"}, status_code=400)
        rules_raw = body.get("rules") or []
        rules = []
        for r in rules_raw:
            if not isinstance(r, dict):
                continue
            rules.append(FilterRule(
                field=str(r.get("field", "")),
                op=str(r.get("op", "")),
                value=r.get("value"),
            ))
        name = str(body["name"])
        filt = event_filter_registry.register(name, rules, mode)
        result = {"name": name}
        result.update(filt.to_dict())
        return JSONResponse(result)

    @app.post("/api/v1/filters/{name}/apply")
    async def api_filters_apply(name: str, request: Request) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        events = body.get("events") or []
        if not isinstance(events, list):
            events = []
        try:
            matched = event_filter_registry.apply(name, events)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "name": name,
            "matched": len(matched),
            "events": matched,
        })

    @app.delete("/api/v1/filters/{name}")
    async def api_filters_delete(name: str) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = event_filter_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if 'app.get("/api/v1/filters")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
