"""Patch sovereign_web.py for Phase 50: PubSubBroker import + 3 endpoints.

Order matters: register /topics literal BEFORE /{topic}/subscribers
and /{topic} so the literal segment doesn't get captured as a path param.
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.task_queue import TaskQueue  # Phase 49"
NEW_IMPORT = (
    "from pradyos.core.task_queue import TaskQueue  # Phase 49\n"
    "from pradyos.core.pubsub import PubSubBroker  # Phase 50"
)
if "from pradyos.core.pubsub import PubSubBroker" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 49 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 3 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/pubsub/topics")
    async def api_pubsub_topics() -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"topics": [], "count": 0})
        topics = pubsub.list_topics()
        return JSONResponse({"topics": topics, "count": len(topics)})

    @app.get("/api/v1/pubsub/{topic}/subscribers")
    async def api_pubsub_subscribers(topic: str) -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"topic": topic, "subscriber_count": 0})
        return JSONResponse({
            "topic": topic,
            "subscriber_count": pubsub.count_subscribers(topic),
        })

    @app.post("/api/v1/pubsub/{topic}")
    async def api_pubsub_publish(topic: str, request: Request) -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"error": "no pubsub configured"}, status_code=400)
        body = await request.json()
        if "message" not in body:
            return JSONResponse({"error": "missing 'message' key"}, status_code=400)
        message = body["message"] if isinstance(body["message"], dict) else {"value": body["message"]}
        notified = pubsub.publish(topic, message)
        return JSONResponse({"topic": topic, "notified": notified})

'''

if 'app.get("/api/v1/pubsub/topics")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
