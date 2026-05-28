"""Patch sovereign_web.py for Phase 42A: on_event → lifespan migration.

Four edits in order:
1. Add `from contextlib import asynccontextmanager` import.
2. Inject `_lifespan` async context manager before `app = FastAPI(...)`.
3. Add `lifespan=_lifespan` to the FastAPI() call.
4. Delete both `@app.on_event` blocks.
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add asynccontextmanager import ─────────────────────────────────────────
if "from contextlib import asynccontextmanager" not in src:
    anchor = "from fastapi import FastAPI, Request, Response"
    assert anchor in src, "Could not find FastAPI import anchor"
    src = src.replace(
        anchor,
        "from contextlib import asynccontextmanager\n" + anchor,
        1,
    )

# ── 2. Inject _lifespan + 3. Change FastAPI() call (atomic replacement) ──────
OLD_APP_LINE = '    app = FastAPI(title="PRADY OS -- Sovereign Dashboard", version="5.0", docs_url="/docs")'
NEW_APP_BLOCK = (
    '    @asynccontextmanager\n'
    '    async def _lifespan(app):\n'
    '        if heartbeat is not None:\n'
    '            await heartbeat.start()\n'
    '        yield\n'
    '        if heartbeat is not None:\n'
    '            await heartbeat.stop()\n'
    '\n'
    '    app = FastAPI(title="PRADY OS -- Sovereign Dashboard", version="5.0", docs_url="/docs", lifespan=_lifespan)'
)
if "lifespan=_lifespan" not in src:
    assert OLD_APP_LINE in src, "Could not find FastAPI() instantiation anchor"
    src = src.replace(OLD_APP_LINE, NEW_APP_BLOCK, 1)

# ── 4. Delete both @app.on_event blocks ──────────────────────────────────────
OLD_STARTUP = (
    '    @app.on_event("startup")\n'
    '    async def _heartbeat_startup() -> None:\n'
    '        if heartbeat is not None:\n'
    '            await heartbeat.start()\n'
    '\n'
)
OLD_SHUTDOWN = (
    '    @app.on_event("shutdown")\n'
    '    async def _heartbeat_shutdown() -> None:\n'
    '        if heartbeat is not None:\n'
    '            await heartbeat.stop()\n'
    '\n'
)

if "@app.on_event" in src:
    if OLD_STARTUP in src:
        src = src.replace(OLD_STARTUP, "", 1)
    if OLD_SHUTDOWN in src:
        src = src.replace(OLD_SHUTDOWN, "", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
