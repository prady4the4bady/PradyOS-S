"""Patch sovereign_web.py for Phase 56: TimeoutGuard import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.bulkhead_pool import BulkheadManager, BulkheadRejectedError  # Phase 55"
NEW_IMPORT = (
    "from pradyos.core.bulkhead_pool import BulkheadManager, BulkheadRejectedError  # Phase 55\n"
    "from pradyos.core.timeout_guard import TimeoutGuard, TimeoutExpiredError  # Phase 56"
)
if "from pradyos.core.timeout_guard import TimeoutGuard" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 55 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: /api/v1/timeouts (literal GET) → /api/v1/timeouts/execute (literal POST)
# → /api/v1/timeouts/{name}/history GET → DELETE. The literal "execute" segment
# must not be captured as a {name} param, so /execute is declared before
# anything that uses {name}.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/timeouts")
    async def api_timeouts_list() -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"names": [], "total": 0})
        return JSONResponse({
            "names": timeout_guard.list_names(),
            "total": timeout_guard.count(),
        })

    @app.post("/api/v1/timeouts/execute")
    async def api_timeouts_execute(request: Request) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"error": "no timeout guard configured"})
        body = await request.json()
        name = str(body.get("name", "default"))
        sleep_s = float(body.get("sleep", 0.0))
        should_error = bool(body.get("should_error", False))
        timeout_v = body.get("timeout")
        timeout_v = float(timeout_v) if timeout_v is not None else None

        import time as _time

        def _no_op() -> str:
            if sleep_s > 0:
                _time.sleep(sleep_s)
            if should_error:
                raise RuntimeError("forced")
            return "ok"

        try:
            result = timeout_guard.execute(name, _no_op, timeout=timeout_v)
        except TimeoutExpiredError as exc:
            return JSONResponse(
                {"name": name, "outcome": "timeout", "error": str(exc)},
                status_code=408,
            )
        except Exception as exc:
            return JSONResponse(
                {"name": name, "outcome": "error", "error": str(exc)},
                status_code=500,
            )

        history = timeout_guard.get_history(name)
        last_record = history[-1].to_dict() if history else None
        return JSONResponse({
            "name": name,
            "outcome": "success",
            "elapsed": last_record["elapsed"] if last_record else 0.0,
            "record": last_record,
        })

    @app.get("/api/v1/timeouts/{name}/history")
    async def api_timeouts_history(name: str) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"name": name, "records": []})
        records = timeout_guard.get_history(name)
        return JSONResponse({
            "name": name,
            "records": [r.to_dict() for r in records],
        })

    @app.delete("/api/v1/timeouts/{name}/history")
    async def api_timeouts_clear(name: str) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = timeout_guard.clear_history(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"cleared": True})

'''

if 'app.get("/api/v1/timeouts")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
