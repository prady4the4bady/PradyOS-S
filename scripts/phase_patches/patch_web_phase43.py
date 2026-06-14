"""Patch sovereign_web.py for Phase 43: GuardrailGate + ApprovalQueue.

Adds imports + 6 endpoints. The two `create_app()` params (guardrail_gate
and approval_queue) are added via the Edit tool, not here.
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add imports ────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.heartbeat import HeartbeatLoop  # Phase 41"
NEW_IMPORT = (
    "from pradyos.core.heartbeat import HeartbeatLoop  # Phase 41\n"
    "from pradyos.core.guardrail import GuardrailGate, RiskLevel  # Phase 43\n"
    "from pradyos.core.approval_queue import ApprovalQueue, ApprovalStatus  # Phase 43"
)
if "GuardrailGate" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 41 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 6 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/guardrail/status")
    async def api_guardrail_status() -> JSONResponse:
        if guardrail_gate is None:
            return JSONResponse({"auto_approve_levels": [], "queue_size": 0})
        return JSONResponse(guardrail_gate.status())

    @app.post("/api/v1/guardrail/submit")
    async def api_guardrail_submit(request: Request) -> JSONResponse:
        if guardrail_gate is None:
            return JSONResponse({"error": "no guardrail gate configured"}, status_code=400)
        body = await request.json()
        try:
            risk = RiskLevel(body["risk_level"])
        except (KeyError, ValueError):
            return JSONResponse({"error": "invalid risk_level"}, status_code=400)
        try:
            req = guardrail_gate.submit(
                action=body["action"],
                risk_level=risk,
                payload=body.get("payload") or {},
                reason=body.get("reason"),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(req.to_dict())

    @app.get("/api/v1/approvals")
    async def api_approvals_list(request: Request) -> JSONResponse:
        if approval_queue is None:
            return JSONResponse({"entries": []})
        status_param = request.query_params.get("status")
        status_filter = None
        if status_param:
            try:
                status_filter = ApprovalStatus(status_param)
            except ValueError:
                return JSONResponse({"error": "invalid status"}, status_code=400)
        entries = approval_queue.list_by_status(status_filter)
        return JSONResponse({"entries": [e.to_dict() for e in entries]})

    @app.post("/api/v1/approvals/{entry_id}/approve")
    async def api_approvals_approve(entry_id: str, request: Request) -> JSONResponse:
        if approval_queue is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        note = body.get("resolver_note") if isinstance(body, dict) else None
        entry = approval_queue.approve(entry_id, resolver_note=note)
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry.to_dict())

    @app.post("/api/v1/approvals/{entry_id}/reject")
    async def api_approvals_reject(entry_id: str, request: Request) -> JSONResponse:
        if approval_queue is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        note = body.get("resolver_note") if isinstance(body, dict) else None
        entry = approval_queue.reject(entry_id, resolver_note=note)
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry.to_dict())

    @app.post("/api/v1/approvals/expire")
    async def api_approvals_expire() -> JSONResponse:
        if approval_queue is None:
            return JSONResponse({"expired": 0})
        expired = approval_queue.expire_stale()
        return JSONResponse({"expired": len(expired)})

'''

if "/api/v1/guardrail/status" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
