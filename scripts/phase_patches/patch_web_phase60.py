"""Patch sovereign_web.py for Phase 60: PipelineRegistry import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.throttle_map import ThrottleMap  # Phase 59"
NEW_IMPORT = (
    "from pradyos.core.throttle_map import ThrottleMap  # Phase 59\n"
    "from pradyos.core.pipeline_chain import PipelineRegistry, PipelineChain, Step, StepError  # Phase 60"
)
if "from pradyos.core.pipeline_chain import PipelineRegistry" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 59 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: register POST /{name}/run BEFORE GET /{name} (there is no plain GET
# on /{name}, but DELETE /{name} could otherwise capture the literal "run").
NEW_ENDPOINTS = '''
    @app.get("/api/v1/pipelines")
    async def api_pipelines_list() -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"pipelines": [], "count": 0})
        names = pipeline_registry.list_chains()
        return JSONResponse({"pipelines": names, "count": len(names)})

    @app.post("/api/v1/pipelines")
    async def api_pipelines_create(request: Request) -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"error": "no pipeline registry configured"})
        body = await request.json()
        if "name" not in body or "steps" not in body:
            return JSONResponse(
                {"error": "missing required keys: name, steps"},
                status_code=400,
            )
        name = str(body["name"])
        steps_raw = body["steps"]
        if not isinstance(steps_raw, list):
            return JSONResponse({"error": "steps must be a list"}, status_code=400)
        steps = []
        for s in steps_raw:
            if not isinstance(s, dict):
                continue
            steps.append(Step(
                name=str(s.get("name", "")),
                transform_type=str(s.get("transform_type", "")),
                params=dict(s.get("params") or {}),
            ))
        chain = PipelineChain(name=name, steps=steps)
        pipeline_registry.register(chain)
        return JSONResponse({
            "registered": True,
            "name": name,
            "step_count": len(steps),
        })

    @app.post("/api/v1/pipelines/{name}/run")
    async def api_pipelines_run(name: str, request: Request) -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        if "event" not in body:
            return JSONResponse(
                {"error": "missing required key: event"},
                status_code=400,
            )
        event = body["event"] if isinstance(body["event"], dict) else {}
        try:
            result = pipeline_registry.run(name, event)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        except StepError as exc:
            return JSONResponse(
                {"error": exc.message, "step": exc.step_name},
                status_code=422,
            )
        return JSONResponse({"name": name, "result": result})

    @app.delete("/api/v1/pipelines/{name}")
    async def api_pipelines_delete(name: str) -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = pipeline_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if 'app.get("/api/v1/pipelines")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
