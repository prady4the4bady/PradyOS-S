"""Patch sovereign_web.py for Phase 63: AggregateRegistry import + 5 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.tag_index import TagIndex  # Phase 61"
NEW_IMPORT_LINES = [
    "from pradyos.core.tag_index import TagIndex  # Phase 61",
]

# Find which Phase 62 import line is actually present (the spec says it exists).
candidates_62 = [
    "from pradyos.core.event_router import RouterRegistry, EventRouter, Route  # Phase 62",
    "from pradyos.core.event_router import RouterRegistry  # Phase 62",
    "from pradyos.core.event_router import EventRouter, RouterRegistry, Route  # Phase 62",
    "from pradyos.core.event_router import RouterRegistry, EventRouter  # Phase 62",
]
import_anchor = None
for cand in candidates_62:
    if cand in src:
        import_anchor = cand
        break

if import_anchor is None:
    # Fall back to Phase 61 anchor
    import_anchor = OLD_IMPORT

NEW_IMPORT = (
    import_anchor
    + "\nfrom pradyos.core.aggregate_root import AggregateRegistry  # Phase 63"
)
if "from pradyos.core.aggregate_root import AggregateRegistry" not in src:
    assert import_anchor in src, "Could not find import anchor"
    src = src.replace(import_anchor, NEW_IMPORT, 1)

# ── 2. Add 5 endpoints before `    return app` ────────────────────────────────
# Order: literal sub-paths (`/state`, `/events`) for {aggregate_id} are registered
# AFTER the bare DELETE /{aggregate_id} because FastAPI dispatches on the longest
# matching prefix when methods differ; both share the {aggregate_id} prefix but
# different suffixes — no conflict.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/aggregates")
    async def api_aggregates_list() -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"aggregates": []})
        return JSONResponse({"aggregates": aggregate_registry.list_aggregates()})

    @app.post("/api/v1/aggregates/{aggregate_id}/events")
    async def api_aggregates_apply(aggregate_id: str, request: Request) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "no aggregate registry configured"})
        body = await request.json()
        if "event_type" not in body:
            return JSONResponse({"error": "missing required key: event_type"}, status_code=400)
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        agg = aggregate_registry.get_or_create(aggregate_id)
        event = agg.apply(str(body["event_type"]), payload)
        return JSONResponse(event.to_dict())

    @app.get("/api/v1/aggregates/{aggregate_id}/state")
    async def api_aggregates_state(aggregate_id: str) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        agg = aggregate_registry.get(aggregate_id)
        if agg is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "aggregate_id": agg.aggregate_id,
            "version": agg.version,
            "state": agg.get_state(),
        })

    @app.get("/api/v1/aggregates/{aggregate_id}/events")
    async def api_aggregates_events(aggregate_id: str, request: Request) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        agg = aggregate_registry.get(aggregate_id)
        if agg is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            since = int(request.query_params.get("since_version", 0))
        except (TypeError, ValueError):
            since = 0
        events = agg.get_events(since_version=since)
        return JSONResponse({
            "aggregate_id": agg.aggregate_id,
            "events": [e.to_dict() for e in events],
        })

    @app.delete("/api/v1/aggregates/{aggregate_id}")
    async def api_aggregates_delete(aggregate_id: str) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = aggregate_registry.delete(aggregate_id)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if 'app.get("/api/v1/aggregates")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
