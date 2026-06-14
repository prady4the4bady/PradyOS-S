#!/usr/bin/env python3
"""Phase 28 patch: wire DecisionJournal into sovereign_web.py.

Adds:
  - decision_journal param to create_app()
  - GET  /api/v1/decisions
  - POST /api/v1/decisions
"""
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "pradyos" / "sovereign_web.py"


def patch(src: str) -> str:
    # ------------------------------------------------------------------
    # 1. Add import for DecisionJournal after BusInspector import
    # ------------------------------------------------------------------
    old_import = "from pradyos.core.bus_inspector import BusInspector  # Phase 27"
    new_import = (
        "from pradyos.core.bus_inspector import BusInspector  # Phase 27\n"
        "from pradyos.core.decision_journal import DecisionJournal  # Phase 28"
    )
    if "from pradyos.core.decision_journal import DecisionJournal" not in src:
        src = src.replace(old_import, new_import, 1)

    # ------------------------------------------------------------------
    # 2. Add decision_journal parameter to create_app() signature
    # ------------------------------------------------------------------
    old_sig_end = "    bus_inspector: Any | None = None,\n) -> FastAPI:"
    new_sig_end = (
        "    bus_inspector: Any | None = None,\n"
        "    decision_journal: Any | None = None,\n"
        ") -> FastAPI:"
    )
    if "decision_journal: Any | None = None" not in src:
        src = src.replace(old_sig_end, new_sig_end, 1)

    # ------------------------------------------------------------------
    # 3. Add Request import (needed for POST body parsing)
    # ------------------------------------------------------------------
    # Request is already imported in the original file, so skip.

    # ------------------------------------------------------------------
    # 4. Add two new endpoints just before `return app`
    # ------------------------------------------------------------------
    new_endpoints = '''
    @app.get("/api/v1/decisions")
    async def api_decisions_get(
        limit: int | None = None,
        offset: int = 0,
        agent_id: str | None = None,
        decision_type: str | None = None,
    ) -> JSONResponse:
        if decision_journal is None:
            return JSONResponse({"entries": [], "count": 0, "total": 0})
        entries = decision_journal.get_entries(
            limit=limit, offset=offset,
            agent_id=agent_id, decision_type=decision_type,
        )
        total = decision_journal.count()
        return JSONResponse({
            "entries": [e.to_dict() for e in entries],
            "count": len(entries),
            "total": total,
        })

    @app.post("/api/v1/decisions")
    async def api_decisions_post(request: Request) -> JSONResponse:
        if decision_journal is None:
            return JSONResponse({"error": "no journal configured"})
        body = await request.json()
        entry = decision_journal.record(
            agent_id=body.get("agent_id", ""),
            decision_type=body.get("decision_type", ""),
            rationale=body.get("rationale", ""),
            outcome=body.get("outcome", ""),
        )
        return JSONResponse(entry.to_dict())

'''
    marker = "\n    return app\n"
    if "/api/v1/decisions" not in src:
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
