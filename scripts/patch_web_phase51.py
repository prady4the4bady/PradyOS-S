"""Patch sovereign_web.py for Phase 51: StateSyncManager import + 3 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.pubsub import PubSubBroker  # Phase 50"
NEW_IMPORT = (
    "from pradyos.core.pubsub import PubSubBroker  # Phase 50\n"
    "from pradyos.core.statesync import StateSyncManager  # Phase 51"
)
if "from pradyos.core.statesync import StateSyncManager" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 50 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/statesync/sessions")
    async def api_statesync_list(request: Request) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"sessions": [], "count": 0})
        flag = (request.query_params.get("active_only") or "").lower()
        active_only = flag in ("true", "1", "yes")
        sessions = statesync.list_sessions(active_only=active_only)
        return JSONResponse({
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions),
        })

    @app.post("/api/v1/statesync/sessions")
    async def api_statesync_create(request: Request) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"error": "no statesync configured"}, status_code=400)
        body = await request.json()
        for key in ("broker_a", "broker_b", "topics_a", "topics_b"):
            if key not in body:
                return JSONResponse(
                    {"error": f"missing required key: {key}"},
                    status_code=400,
                )
        try:
            session = statesync.create_session(
                broker_a_name=str(body["broker_a"]),
                broker_b_name=str(body["broker_b"]),
                topics_a=list(body["topics_a"]),
                topics_b=list(body["topics_b"]),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(session.to_dict())

    @app.delete("/api/v1/statesync/sessions/{session_id}")
    async def api_statesync_stop(session_id: str) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = statesync.stop_session(session_id)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"stopped": True})

'''

if 'app.get("/api/v1/statesync/sessions")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
