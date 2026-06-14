"""Patch sovereign_web.py for Phase 61: TagIndex import + 6 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.pipeline_chain import PipelineRegistry, PipelineChain, Step, StepError  # Phase 60"
NEW_IMPORT = (
    "from pradyos.core.pipeline_chain import PipelineRegistry, PipelineChain, Step, StepError  # Phase 60\n"
    "from pradyos.core.tag_index import TagIndex  # Phase 61"
)
if "from pradyos.core.tag_index import TagIndex" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 60 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 6 endpoints before `    return app` ────────────────────────────────
# Order: literals (/tag, /untag, /search) and /items/{tag} must be declared
# BEFORE /items/{item_id} (DELETE) since both have the same path pattern but
# different methods (FastAPI dispatches on method too — no conflict).
NEW_ENDPOINTS = '''
    @app.get("/api/v1/tags")
    async def api_tags_list() -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"tags": [], "total": 0})
        all_tags = tag_index.list_tags()
        return JSONResponse({"tags": all_tags, "total": len(all_tags)})

    @app.post("/api/v1/tags/tag")
    async def api_tags_tag(request: Request) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"error": "no tag index configured"})
        body = await request.json()
        item_id = str(body.get("item_id", ""))
        tags = body.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tag_index.tag(item_id, *[str(t) for t in tags])
        return JSONResponse({"tagged": True, "item_id": item_id, "tags": list(tags)})

    @app.post("/api/v1/tags/untag")
    async def api_tags_untag(request: Request) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"error": "no tag index configured"})
        body = await request.json()
        item_id = str(body.get("item_id", ""))
        tags = body.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tag_index.untag(item_id, *[str(t) for t in tags])
        return JSONResponse({"untagged": True, "item_id": item_id, "tags": list(tags)})

    @app.get("/api/v1/tags/items/{tag}")
    async def api_tags_items_for(tag: str) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"tag": tag, "items": []})
        return JSONResponse({"tag": tag, "items": tag_index.items(tag)})

    @app.get("/api/v1/tags/search")
    async def api_tags_search(request: Request) -> JSONResponse:
        raw = request.query_params.get("tags", "")
        mode = request.query_params.get("mode", "all")
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        if tag_index is None:
            return JSONResponse({"tags": tags, "mode": mode, "results": []})
        results = tag_index.search(*tags, mode=mode)
        return JSONResponse({"tags": tags, "mode": mode, "results": results})

    @app.delete("/api/v1/tags/items/{item_id}")
    async def api_tags_delete_item(item_id: str) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = tag_index.delete_item(item_id)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if 'app.get("/api/v1/tags")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
