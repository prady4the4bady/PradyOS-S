#!/usr/bin/env python3
"""Phase 27 patch: wire BusInspector into sovereign_web.py.

Adds:
  - bus_inspector param to create_app()
  - GET /api/v1/bus/events
  - GET /api/v1/bus/stats
"""
import re
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "pradyos" / "sovereign_web.py"


def patch(src: str) -> str:
    # ------------------------------------------------------------------ #
    # 1. Add import for BusInspector after the existing Phase-25 import   #
    # ------------------------------------------------------------------ #
    old_import = "from pradyos.core.audit_replay import AuditReplayEngine  # Phase 25"
    new_import = (
        "from pradyos.core.audit_replay import AuditReplayEngine  # Phase 25\n"
        "from pradyos.core.bus_inspector import BusInspector  # Phase 27"
    )
    if "from pradyos.core.bus_inspector import BusInspector" not in src:
        src = src.replace(old_import, new_import, 1)

    # ------------------------------------------------------------------ #
    # 2. Add bus_inspector parameter to create_app() signature            #
    # ------------------------------------------------------------------ #
    old_sig_end = "    plugin_sandbox: Any | None = None,\n) -> FastAPI:"
    new_sig_end = (
        "    plugin_sandbox: Any | None = None,\n"
        "    bus_inspector: Any | None = None,\n"
        ") -> FastAPI:"
    )
    if "bus_inspector: Any | None = None" not in src:
        src = src.replace(old_sig_end, new_sig_end, 1)

    # ------------------------------------------------------------------ #
    # 3. Add the two new endpoints just before `return app`               #
    # ------------------------------------------------------------------ #
    new_endpoints = '''
    @app.get("/api/v1/bus/events")
    async def api_bus_events(
        topic: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> JSONResponse:
        if bus_inspector is None:
            return JSONResponse({"events": [], "count": 0})
        events = bus_inspector.get_events(topic=topic, limit=limit, offset=offset)
        return JSONResponse({"events": [e.to_dict() for e in events], "count": len(events)})

    @app.get("/api/v1/bus/stats")
    async def api_bus_stats() -> JSONResponse:
        if bus_inspector is None:
            return JSONResponse(
                {"total_events": 0, "buffer_size": 0, "max_size": 0, "topics": {}}
            )
        return JSONResponse(bus_inspector.get_stats())

'''
    marker = "\n    return app\n"
    if "/api/v1/bus/events" not in src:
        src = src.replace(marker, new_endpoints + marker, 1)

    return src


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    patched = patch(original)
    if patched == original:
        print("Nothing to patch — already up to date.")
        return 0
    TARGET.write_text(patched, encoding="utf-8")
    print(f"Patched {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
