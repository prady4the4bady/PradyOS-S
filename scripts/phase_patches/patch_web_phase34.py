"""Patch sovereign_web.py for Phase 34: add integration_bus import and endpoint."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.correlation_engine import CorrelationEngine  # Phase 33"
NEW_IMPORT = (
    "from pradyos.core.correlation_engine import CorrelationEngine  # Phase 33\n"
    "from pradyos.core.integration_bus import SovereignBus  # Phase 34"
)
if "SovereignBus" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 33 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add endpoint before `    return app` ────────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/integration/status")
    async def api_integration_status() -> JSONResponse:
        if integration_bus is None:
            return JSONResponse({"wired": {}, "wire_count": 0})
        return JSONResponse(integration_bus.status())

'''

if "/api/v1/integration/status" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
