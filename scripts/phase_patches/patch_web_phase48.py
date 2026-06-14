"""Patch sovereign_web.py for Phase 48: EventStore import + 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.memory_graph import MemoryGraph as Phase47MemoryGraph  # Phase 47"
NEW_IMPORT = (
    "from pradyos.core.memory_graph import MemoryGraph as Phase47MemoryGraph  # Phase 47\n"
    "from pradyos.core.event_store import EventStore  # Phase 48"
)
if "EventStore" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 47 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 endpoints before `    return app` ────────────────────────────────
# Order matters: POST /{stream}/project must be registered BEFORE POST /{stream}
# so the literal /project doesn't get captured by the {stream} path param.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/events/{stream}")
    async def api_events_read(stream: str, request: Request) -> JSONResponse:
        if event_store is None:
            return JSONResponse({"stream": stream, "events": [], "count": 0})
        try:
            from_seq = int(request.query_params.get("from_seq", 0))
        except (ValueError, TypeError):
            from_seq = 0
        events = event_store.read(stream, from_seq=from_seq)
        return JSONResponse({
            "stream": stream,
            "events": [e.to_dict() for e in events],
            "count": len(events),
        })

    @app.post("/api/v1/events/{stream}/project")
    async def api_events_project(stream: str, request: Request) -> JSONResponse:
        if event_store is None:
            return JSONResponse({"stream": stream, "state": {}})
        body = await request.json()
        if "reducer_steps" not in body:
            return JSONResponse({"error": "missing 'reducer_steps' key"}, status_code=400)
        initial = body.get("initial") or {}
        steps = body["reducer_steps"]

        def _reducer(state: dict, event) -> dict:
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if step.get("match_type") == event.event_type:
                    state.update(step.get("updates") or {})
                    break
            return state

        state = event_store.project(stream, _reducer, initial=initial)
        return JSONResponse({"stream": stream, "state": state})

    @app.post("/api/v1/events/{stream}")
    async def api_events_append(stream: str, request: Request) -> JSONResponse:
        if event_store is None:
            return JSONResponse({"error": "no event store configured"}, status_code=400)
        body = await request.json()
        if "event_type" not in body:
            return JSONResponse({"error": "missing 'event_type' key"}, status_code=400)
        event = event_store.append(
            stream=stream,
            event_type=str(body["event_type"]),
            payload=body.get("payload") or {},
        )
        return JSONResponse(event.to_dict())

'''

if "/api/v1/events/" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
