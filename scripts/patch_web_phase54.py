"""Patch sovereign_web.py for Phase 54: RetryPolicy import + 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.circuit_breaker import CircuitBreaker, BreakerState  # Phase 53"
NEW_IMPORT = (
    "from pradyos.core.circuit_breaker import CircuitBreaker, BreakerState  # Phase 53\n"
    "from pradyos.core.retry_policy import RetryPolicy  # Phase 54"
)
if "from pradyos.core.retry_policy import RetryPolicy" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 53 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 endpoints before `    return app` ────────────────────────────────
# Order: /retry/execute literal BEFORE /retry/{name}/history, and the bare
# /retry GET first so each registers cleanly.
NEW_ENDPOINTS = '''
    @app.get("/api/v1/retry")
    async def api_retry_list() -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"names": [], "count": 0})
        return JSONResponse({
            "names": retry_policy.list_names(),
            "count": retry_policy.count(),
        })

    @app.post("/api/v1/retry/execute")
    async def api_retry_execute(request: Request) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"error": "no retry policy configured"})
        body = await request.json()
        name = str(body.get("name", "default"))
        should_fail = bool(body.get("should_fail", False))
        fail_attempts = int(body.get("fail_attempts", 0))

        # Built-in test fn: fails the first `fail_attempts` calls, then succeeds.
        counter = {"n": 0}

        def _test_fn():
            counter["n"] += 1
            if should_fail and counter["n"] <= fail_attempts:
                raise RuntimeError("simulated failure")
            return "ok"

        result: str | None = None
        error: str | None = None
        try:
            result = retry_policy.execute(name, _test_fn)
        except Exception as exc:
            error = repr(exc)

        attempts = len(retry_policy.get_history(name))
        return JSONResponse({
            "name": name,
            "result": result,
            "attempts": attempts,
            "error": error,
        })

    @app.get("/api/v1/retry/{name}/history")
    async def api_retry_history(name: str) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"name": name, "history": []})
        return JSONResponse({
            "name": name,
            "history": retry_policy.get_history(name),
        })

    @app.delete("/api/v1/retry/{name}/history")
    async def api_retry_clear(name: str) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = retry_policy.clear_history(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"cleared": True})

'''

if 'app.get("/api/v1/retry")' not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
