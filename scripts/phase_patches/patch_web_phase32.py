"""Patch sovereign_web.py for Phase 32: add snapshot_store param and 4 endpoints."""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.signal_aggregator import SignalAggregator  # Phase 31"
NEW_IMPORT = (
    "from pradyos.core.signal_aggregator import SignalAggregator  # Phase 31\n"
    "from pradyos.core.snapshot_store import SnapshotStore  # Phase 32"
)
if "SnapshotStore" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 31 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 4 new endpoints before `    return app` ────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/snapshots/{namespace}")
    async def api_snapshots_list(namespace: str) -> JSONResponse:
        if snapshot_store is None:
            return JSONResponse({"namespace": namespace, "keys": []})
        return JSONResponse({
            "namespace": namespace,
            "keys": snapshot_store.list_keys(namespace),
        })

    @app.post("/api/v1/snapshots/{namespace}/{key}")
    async def api_snapshots_save(namespace: str, key: str, request: Request) -> JSONResponse:
        if snapshot_store is None:
            return JSONResponse({"error": "no snapshot store configured"})
        body = await request.json()
        snap = snapshot_store.save(namespace=namespace, key=key, data=body["data"])
        return JSONResponse(snap.to_dict())

    @app.get("/api/v1/snapshots/{namespace}/{key}")
    async def api_snapshots_get(namespace: str, key: str, request: Request) -> JSONResponse:
        if snapshot_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        raw = request.query_params.get("version")
        version = int(raw) if raw is not None else None
        snap = snapshot_store.get(namespace=namespace, key=key, version=version)
        if snap is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(snap.to_dict())

    @app.delete("/api/v1/snapshots/{namespace}/{key}")
    async def api_snapshots_delete(namespace: str, key: str) -> JSONResponse:
        if snapshot_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = snapshot_store.delete(namespace=namespace, key=key)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

'''

if "/api/v1/snapshots" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
