"""Phase 24 — patch pradyos/sovereign_web.py (health scorecard endpoints)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "pradyos" / "sovereign_web.py"


def patch() -> None:
    src = WEB.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 1.  Add `scorecard` parameter to create_app() signature             #
    # ------------------------------------------------------------------ #
    OLD_PARAM = "    rate_limiter: Any | None = None,\n) -> FastAPI:"
    NEW_PARAM = (
        "    rate_limiter: Any | None = None,\n"
        "    scorecard: Any | None = None,\n"
        ") -> FastAPI:"
    )
    if "scorecard: Any | None = None" in src:
        print("scorecard param already present — skipping param patch")
    elif OLD_PARAM not in src:
        print("ERROR: could not find rate_limiter param anchor", file=sys.stderr)
        sys.exit(1)
    else:
        src = src.replace(OLD_PARAM, NEW_PARAM, 1)
        print("✓ added scorecard param to create_app()")

    # ------------------------------------------------------------------ #
    # 2.  Insert health endpoints just before `    return app`            #
    # ------------------------------------------------------------------ #
    HEALTH_ENDPOINTS = '''\
    @app.get("/api/v1/health/score")
    async def api_health_score() -> JSONResponse:
        import time as _time
        if scorecard is None:
            return JSONResponse(
                {"score": 100.0, "grade": "A", "components": [], "timestamp": _time.time()},
                status_code=200,
            )
        return JSONResponse(scorecard.get_report().to_dict(), status_code=200)

    @app.post("/api/v1/health/update")
    async def api_health_update(request: Request) -> JSONResponse:
        if scorecard is None:
            return JSONResponse({"updated": False}, status_code=200)
        body = await request.json()
        name = body["name"]
        score = float(body["score"])
        details = body.get("details", {})
        scorecard.update(name, score, details)
        return JSONResponse({"updated": True}, status_code=200)

'''

    RETURN_ANCHOR = "    return app\n"
    if "api/v1/health/score" in src:
        print("health endpoints already present — skipping endpoint patch")
    elif RETURN_ANCHOR not in src:
        print("ERROR: could not find 'return app' anchor", file=sys.stderr)
        sys.exit(1)
    else:
        # Replace only the LAST occurrence of '    return app'
        idx = src.rfind(RETURN_ANCHOR)
        src = src[:idx] + HEALTH_ENDPOINTS + src[idx:]
        print("✓ inserted /api/v1/health/score and /api/v1/health/update endpoints")

    # ------------------------------------------------------------------ #
    # 3.  Safety check: DASHBOARD_HTML line untouched                     #
    # ------------------------------------------------------------------ #
    if "_DASHBOARD_HTML = '" not in src:
        print("ERROR: DASHBOARD_HTML line missing after patch — aborting", file=sys.stderr)
        sys.exit(1)

    WEB.write_text(src, encoding="utf-8")
    print(f"✓ patched {WEB}")


if __name__ == "__main__":
    patch()
