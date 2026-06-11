"""Patch sovereign_web.py for Phase 62: RouterRegistry import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.tag_index import TagIndex  # Phase 61"
NEW_IMPORT = (
    "from pradyos.core.tag_index import TagIndex  # Phase 61\n"
    "from pradyos.core.event_router import RouterRegistry  # Phase 62"
)
if "from pradyos.core.event_router import RouterRegistry" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 61 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: POST /{name}/route literal BEFORE DELETE /{name} so the literal
# suffix isn't captured as part of the name param.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/routers")
    async def api_routers_list() -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"routers": [], "total": 0})
        names = router_registry.list_names()
        return JSONResponse({"routers": names, "total": len(names)})

    @app.post("/api/v1/routers")
    async def api_routers_create(request: Request) -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"error": "no router registry configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        name = str(body["name"])
        default_dest = body.get("default_destination")
        routes_raw = body.get("routes") or []
        try:
            router = router_registry.create(
                name=name,
                default_destination=default_dest,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        added = 0
        for r in routes_raw:
            if not isinstance(r, dict):
                continue
            try:
                router.add_route(
                    name=str(r.get("name", "")),
                    predicates=r.get("predicates") or [],
                    destination=str(r.get("destination", "")),
                )
                added += 1
            except ValueError:
                # duplicate route name in same payload — skip
                continue
        return JSONResponse({
            "created": True,
            "name": name,
            "route_count": added,
            "default_destination": default_dest,
        })

    @app.post("/api/v1/routers/{name}/route")
    async def api_routers_route(name: str, request: Request) -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        router = router_registry.get(name)
        if router is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        destinations = router.route(event)
        return JSONResponse({
            "name": name,
            "destinations": destinations,
            "matched": len(destinations),
        })

    @app.delete("/api/v1/routers/{name}")
    async def api_routers_delete(name: str) -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = router_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if 'app.get("/api/v1/routers")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
