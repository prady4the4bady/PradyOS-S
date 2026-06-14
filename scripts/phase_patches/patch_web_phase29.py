"""Phase 29B: Patch sovereign_web.py — add capability_registry endpoints."""
import re
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "pradyos" / "sovereign_web.py"

src = TARGET.read_text(encoding="utf-8")

# ------------------------------------------------------------------ #
# 1. Add capability_registry import after decision_journal import
# ------------------------------------------------------------------ #
OLD_IMPORT = "from pradyos.core.decision_journal import DecisionJournal  # Phase 28"
NEW_IMPORT = (
    "from pradyos.core.decision_journal import DecisionJournal  # Phase 28\n"
    "from pradyos.core.capability_registry import CapabilityRegistry  # Phase 29"
)
assert OLD_IMPORT in src, "Import anchor not found"
src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ------------------------------------------------------------------ #
# 2. Add capability_registry param to create_app() signature
# ------------------------------------------------------------------ #
OLD_SIG = "    decision_journal: Any | None = None,\n) -> FastAPI:"
NEW_SIG = (
    "    decision_journal: Any | None = None,\n"
    "    capability_registry: Any | None = None,\n"
    ") -> FastAPI:"
)
assert OLD_SIG in src, "Signature anchor not found"
src = src.replace(OLD_SIG, NEW_SIG, 1)

# ------------------------------------------------------------------ #
# 3. Insert 3 new endpoints just before `    return app`
# ------------------------------------------------------------------ #
NEW_ENDPOINTS = '''
    @app.get("/api/v1/capabilities")
    async def api_capabilities_get() -> JSONResponse:
        if capability_registry is None:
            return JSONResponse({"capabilities": [], "summary": {}})
        return JSONResponse({
            "capabilities": [c.to_dict() for c in capability_registry.list_all()],
            "summary": capability_registry.summary(),
        })

    @app.post("/api/v1/capabilities")
    async def api_capabilities_post(request: Request) -> JSONResponse:
        if capability_registry is None:
            return JSONResponse({"error": "no registry configured"})
        body = await request.json()
        cap = capability_registry.register(
            name=body.get("name", ""),
            version=body.get("version", ""),
            provided_apis=body.get("provided_apis", []),
            consumed_apis=body.get("consumed_apis", []),
            status=body.get("status", "active"),
            metadata=body.get("metadata", {}),
        )
        return JSONResponse(cap.to_dict())

    @app.get("/api/v1/capabilities/{cap_name}")
    async def api_capabilities_get_one(cap_name: str) -> JSONResponse:
        if capability_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        cap = capability_registry.get(cap_name)
        if cap is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(cap.to_dict())

'''

OLD_RETURN = "\n    return app\n"
assert OLD_RETURN in src, "return app anchor not found"
src = src.replace(OLD_RETURN, NEW_ENDPOINTS + "\n    return app\n", 1)

TARGET.write_text(src, encoding="utf-8")
print(f"Patched {TARGET} successfully.")

# Quick sanity: make sure DASHBOARD_HTML line is untouched (still one giant line)
lines = TARGET.read_text(encoding="utf-8").splitlines()
dashboard_lines = [i for i, ln in enumerate(lines, 1) if "_DASHBOARD_HTML = " in ln]
assert len(dashboard_lines) == 1, f"DASHBOARD_HTML line count unexpected: {dashboard_lines}"
print(f"  _DASHBOARD_HTML is intact on line {dashboard_lines[0]}")
print("  New endpoints present:", src.count("/api/v1/capabilities"))
