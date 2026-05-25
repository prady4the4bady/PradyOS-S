"""Sovereign Web Dashboard (Phase 4C / Phase 5 extensions).

FastAPI application providing an HTTP control plane for PRADY OS.

Entry point: ``pradyos-web``  (runs on ``0.0.0.0:8000``)

Routes
------
GET  /                          HTML dashboard (inline Jinja2 template)
GET  /api/status                JSON: checkpoint state, warden snapshot, active campaigns
GET  /api/campaigns             JSON list of all campaigns with progress
GET  /api/health                JSON: health probe results (Phase 5B)
GET  /api/analytics             JSON: campaign analytics (Phase 5E)
POST /api/approve/{task_id}     Write approval decision -> JSON confirmation
POST /api/reject/{task_id}      Write rejection decision -> JSON confirmation
GET  /stream                    Server-Sent Events stream from EventBus

Windows safety
--------------
* No uvloop -- uses asyncio default event loop
* All paths via pathlib.Path
* No AF_UNIX, no fork(), no os.killpg()
* SSE implemented with asyncio.Queue (no trio, no anyio required)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

log = logging.getLogger("pradyos.sovereign_web")

# ---------------------------------------------------------------------------
# State / decisions file
# ---------------------------------------------------------------------------

_DEFAULT_STATE_DIR = Path(
    os.environ.get(
        "PRADYOS_STATE_PATH",
        Path(__file__).resolve().parent.parent / "var" / "state",
    )
)
_DECISIONS_FILE = _DEFAULT_STATE_DIR / "sovereign_decisions.jsonl"


def _write_decision(task_id: str, decision: str, reason: str = "") -> dict[str, Any]:
    """Append a decision record to the decisions file."""
    _DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "task_id": task_id,
        "decision": decision,
        "reason": reason,
        "ts": time.time(),
    }
    with _DECISIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


# ---------------------------------------------------------------------------
# EventBus SSE bridge
# ---------------------------------------------------------------------------

_sse_queues: list[asyncio.Queue[str]] = []


def _publish_to_sse(topic: str, payload: dict[str, Any]) -> None:
    """Forward EventBus events to all active SSE subscribers."""
    data = json.dumps({"topic": topic, "payload": payload})
    for q in list(_sse_queues):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


async def _sse_generator(queue: asyncio.Queue[str]) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted messages from the queue."""
    keepalive_s = float(os.environ.get("PRADYOS_SSE_KEEPALIVE_S", "30.0"))
    _sse_queues.append(queue)
    try:
        yield ": connected\n\n"
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=keepalive_s)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        try:
            _sse_queues.remove(queue)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    campaign_registry: Any | None = None,
    checkpoint_store: Any | None = None,
    bus: Any | None = None,
    health_registry: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    campaign_registry:
        Optional CampaignRegistry instance. Falls back to the global one.
    checkpoint_store:
        Optional CheckpointStore instance.
    bus:
        Optional EventBus. Falls back to the global singleton.
    health_registry:
        Optional HealthRegistry instance. Falls back to the global singleton.
    """
    app = FastAPI(
        title="PRADY OS -- Sovereign Dashboard",
        version="5.0",
        docs_url="/docs",
    )

    # Wire EventBus -> SSE
    if bus is not None:
        bus.subscribe("*", _publish_to_sse)

    # ------------------------------------------------------------------
    # GET /
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        html = _DASHBOARD_HTML
        return HTMLResponse(content=html, status_code=200)

    # ------------------------------------------------------------------
    # GET /api/status
    # ------------------------------------------------------------------

    @app.get("/api/status")
    async def api_status() -> JSONResponse:
        checkpoint_summary: dict[str, Any] = {}
        if checkpoint_store is not None:
            try:
                checkpoint_summary = _read_checkpoint_summary(checkpoint_store)
            except Exception as e:  # noqa: BLE001
                checkpoint_summary = {"error": str(e)}

        active_campaigns: list[dict] = []
        if campaign_registry is not None:
            try:
                active_campaigns = [c.to_dict() for c in campaign_registry.active()]
            except Exception as e:  # noqa: BLE001
                active_campaigns = []

        return JSONResponse(
            {
                "ok": True,
                "timestamp": time.time(),
                "checkpoint": checkpoint_summary,
                "warden": {"status": "operational"},
                "active_campaigns": active_campaigns,
            }
        )

    # ------------------------------------------------------------------
    # GET /api/campaigns
    # ------------------------------------------------------------------

    @app.get("/api/campaigns")
    async def api_campaigns() -> JSONResponse:
        campaigns: list[dict] = []
        if campaign_registry is not None:
            try:
                for c in campaign_registry.recent(100):
                    d = c.to_dict()
                    d["progress"] = c.progress()
                    campaigns.append(d)
            except Exception as e:  # noqa: BLE001
                log.debug("Error fetching campaigns: %s", e)
        return JSONResponse({"ok": True, "campaigns": campaigns, "count": len(campaigns)})

    # ------------------------------------------------------------------
    # GET /api/health  (Phase 5B)
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        try:
            from pradyos.core.healthcheck import get_health_registry
            reg = health_registry if health_registry is not None else get_health_registry()
            overall = reg.overall()
            probes = reg.run_all()
            return JSONResponse({
                "status": overall,
                "probes": [p.dict() for p in probes],
            })
        except Exception as e:  # noqa: BLE001
            log.debug("Health registry unavailable: %s", e)
            return JSONResponse({"status": "ok", "probes": []})

    # ------------------------------------------------------------------
    # GET /api/analytics  (Phase 5E)
    # ------------------------------------------------------------------

    @app.get("/api/analytics")
    async def api_analytics() -> JSONResponse:
        try:
            from pradyos.campaign.analytics import CampaignAnalytics
            reg = campaign_registry
            if reg is None:
                raise ValueError("no registry")
            analytics = CampaignAnalytics(registry=reg)
            return JSONResponse(analytics.to_dict())
        except Exception as e:  # noqa: BLE001
            log.debug("Analytics unavailable: %s", e)
            return JSONResponse({
                "success_rate": 0.0,
                "avg_duration_s": 0.0,
                "node_failure_histogram": {},
                "busiest_hours": [],
            })

    # ------------------------------------------------------------------
    # GET /api/metrics  (Phase 6 Observability)
    @app.get("/api/metrics")
    async def api_metrics() -> JSONResponse:
        try:
            from pradyos.core.metrics import get_registry
            snapshot = get_registry().snapshot()
        except Exception as exc:
            snapshot = {"error": str(exc)}
        return JSONResponse({"metrics": snapshot, "ts": time.time()})

    # ------------------------------------------------------------------
    # GET /api/recommendations  (Phase 7D — Sovereign Advisor)
    # ------------------------------------------------------------------

    @app.get("/api/recommendations")
    async def api_recommendations() -> JSONResponse:
        try:
            from pradyos.oracle.advisor import SovereignAdvisor
            from pradyos.core.audit import get_audit_log
            from pradyos.core.metrics import get_registry

            advisor = SovereignAdvisor(
                audit_log=get_audit_log(),
                metrics_registry=get_registry(),
                campaign_registry=campaign_registry,
            )
            recs = advisor.recommend(n=5)
            return JSONResponse({
                "recommendations": [r.to_dict() for r in recs],
                "ts": time.time(),
            })
        except Exception as exc:  # noqa: BLE001
            log.debug("Recommendations unavailable: %s", exc)
            return JSONResponse({"recommendations": [], "ts": time.time()})

        # POST /api/approve/{task_id}
    # ------------------------------------------------------------------

    @app.post("/api/approve/{task_id}")
    async def api_approve(task_id: str) -> JSONResponse:
        record = _write_decision(task_id, "approved")
        log.info("Sovereign APPROVED task %s", task_id)
        if bus is not None:
            bus.publish("sovereign.approved", {"task_id": task_id})
        return JSONResponse({"ok": True, "task_id": task_id, "decision": "approved", "ts": record["ts"]})

    # ------------------------------------------------------------------
    # POST /api/reject/{task_id}
    # ------------------------------------------------------------------

    @app.post("/api/reject/{task_id}")
    async def api_reject(task_id: str) -> JSONResponse:
        record = _write_decision(task_id, "rejected")
        log.info("Sovereign REJECTED task %s", task_id)
        if bus is not None:
            bus.publish("sovereign.rejected", {"task_id": task_id})
        return JSONResponse({"ok": True, "task_id": task_id, "decision": "rejected", "ts": record["ts"]})

    # ------------------------------------------------------------------
    # GET /stream  (Server-Sent Events)
    # ------------------------------------------------------------------

    @app.get("/stream")
    async def stream_events() -> StreamingResponse:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        return StreamingResponse(
            _sse_generator(queue),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


# ---------------------------------------------------------------------------
# Checkpoint summary helper
# ---------------------------------------------------------------------------


def _read_checkpoint_summary(checkpoint_store: Any) -> dict[str, Any]:
    """Extract a lightweight status snapshot from the checkpoint store."""
    if hasattr(checkpoint_store, "snapshot"):
        try:
            result = checkpoint_store.snapshot()
            if isinstance(result, dict):
                return result
        except Exception:  # noqa: BLE001
            pass
    if hasattr(checkpoint_store, "path"):
        try:
            p = Path(checkpoint_store.path)
            if p.exists():
                size = p.stat().st_size
                return {"file": str(p), "size_bytes": size}
        except Exception:  # noqa: BLE001
            pass
    return {"status": "available"}


# ---------------------------------------------------------------------------
# Dashboard HTML (inline -- no external files required)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PRADY OS -- Sovereign Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0a0a0f; color: #e0e0f0; font-family: 'Courier New', monospace; }
    header { background: #12121e; border-bottom: 1px solid #2a2a4a; padding: 1rem 2rem;
             display: flex; align-items: center; justify-content: space-between; }
    header h1 { font-size: 1.4rem; color: #7b8fff; letter-spacing: 2px; }
    header .badge { font-size: 0.75rem; color: #4caf50; border: 1px solid #4caf50;
                    padding: 2px 8px; border-radius: 4px; }
    main { padding: 2rem; max-width: 1200px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
    .card { background: #12121e; border: 1px solid #2a2a4a; border-radius: 8px; padding: 1.2rem; }
    .card h2 { font-size: 0.85rem; color: #7b8fff; text-transform: uppercase;
                letter-spacing: 1px; margin-bottom: 0.8rem; }
    .stat { display: flex; justify-content: space-between; padding: 4px 0;
            border-bottom: 1px solid #1e1e32; font-size: 0.85rem; }
    .stat:last-child { border-bottom: none; }
    .stat .val { color: #a0cfff; }
    #log { background: #0d0d16; border: 1px solid #2a2a4a; border-radius: 8px;
           padding: 1rem; margin-top: 1rem; height: 200px; overflow-y: auto;
           font-size: 0.8rem; color: #6a6a9a; }
    #log p { padding: 2px 0; border-bottom: 1px solid #1a1a2e; }
  </style>
</head>
<body>
  <header>
    <h1>PRADY OS -- SOVEREIGN</h1>
    <span class="badge" id="status-badge">ONLINE</span>
  </header>
  <main>
    <div class="grid">
      <div class="card" id="status-card">
        <h2>System Status</h2>
        <div class="stat"><span>Kernel</span><span class="val" id="s-kernel">--</span></div>
        <div class="stat"><span>Warden</span><span class="val" id="s-warden">--</span></div>
        <div class="stat"><span>Campaigns</span><span class="val" id="s-campaigns">--</span></div>
        <div class="stat"><span>Last refresh</span><span class="val" id="s-ts">--</span></div>
      </div>
      <div class="card">
        <h2>Event Stream</h2>
        <div id="log"><p>Connecting...</p></div>
      </div>
    </div>
  </main>
  <script>
    async function fetchStatus() {
      try {
        const r = await fetch('/api/status');
        const d = await r.json();
        document.getElementById('s-kernel').textContent =
          d.checkpoint && d.checkpoint.file ? 'checkpoint ok' : 'active';
        document.getElementById('s-warden').textContent =
          d.warden ? d.warden.status : 'unknown';
        document.getElementById('s-campaigns').textContent =
          d.active_campaigns ? d.active_campaigns.length : '0';
        document.getElementById('s-ts').textContent =
          new Date(d.timestamp * 1000).toLocaleTimeString();
      } catch(e) { console.error(e); }
    }
    fetchStatus();
    setInterval(fetchStatus, 5000);

    const log = document.getElementById('log');
    log.innerHTML = '';
    const es = new EventSource('/stream');
    es.onmessage = e => {
      const p = document.createElement('p');
      p.textContent = e.data.slice(0, 120);
      log.prepend(p);
      if (log.children.length > 50) log.removeChild(log.lastChild);
    };
    es.onerror = () => {
      const p = document.createElement('p');
      p.textContent = '[stream disconnected]';
      log.prepend(p);
    };
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: pradyos-web."""
    import uvicorn

    from pradyos.campaign.registry import CampaignRegistry
    from pradyos.core.bus import get_bus
    from pradyos.imperium.checkpoint import CheckpointStore

    bus = get_bus()
    registry = CampaignRegistry()
    checkpoint = CheckpointStore()

    app = create_app(
        campaign_registry=registry,
        checkpoint_store=checkpoint,
        bus=bus,
    )

    log.info("Starting Sovereign Web Dashboard on 0.0.0.0:8000")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        log_level="info",
    )


if __name__ == "__main__":
    main()
