"""Sovereign Web Dashboard (Phase 4C / Phase 5 extensions)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from pradyos.core.ledger import EventLedger
from pradyos.core.audit_replay import AuditReplayEngine  # Phase 25
from pradyos.sovereign.audit_ui import build_audit_html

log = logging.getLogger("pradyos.sovereign_web")

_DEFAULT_STATE_DIR = Path(
    os.environ.get(
        "PRADYOS_STATE_PATH",
        Path(__file__).resolve().parent.parent / "var" / "state",
    )
)
_DECISIONS_FILE = _DEFAULT_STATE_DIR / "sovereign_decisions.jsonl"


def _write_decision(task_id: str, decision: str, reason: str = "") -> dict[str, Any]:
    _DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"task_id": task_id, "decision": decision, "reason": reason, "ts": time.time()}
    with _DECISIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


_sse_queues: list[asyncio.Queue[str]] = []


def _publish_to_sse(topic: str, payload: dict[str, Any]) -> None:
    data = json.dumps({"topic": topic, "payload": payload})
    for q in list(_sse_queues):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


async def _sse_generator(queue: asyncio.Queue[str]) -> AsyncGenerator[str, None]:
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


def create_app(
    campaign_registry: Any | None = None,
    checkpoint_store: Any | None = None,
    bus: Any | None = None,
    health_registry: Any | None = None,
    observability_dashboard: Any | None = None,
    campaign_monitor: Any | None = None,
    policy_engine: Any | None = None,
    scheduler: Any | None = None,
    telemetry: Any | None = None,
    graph: Any | None = None,
    ledger: Any | None = None,
    intent: Any | None = None,
    config_reloader: Any | None = None,
    metrics: Any | None = None,
    rate_limiter: Any | None = None,
    scorecard: Any | None = None,
    replay_engine: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="PRADY OS -- Sovereign Dashboard", version="5.0", docs_url="/docs")

    if bus is not None:
        bus.subscribe("*", _publish_to_sse)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(content=_DASHBOARD_HTML, status_code=200)

    @app.get("/api/status")
    async def api_status() -> JSONResponse:
        checkpoint_summary: dict[str, Any] = {}
        if checkpoint_store is not None:
            try:
                checkpoint_summary = _read_checkpoint_summary(checkpoint_store)
            except Exception as e:
                checkpoint_summary = {"error": str(e)}
        active_campaigns: list[dict] = []
        if campaign_registry is not None:
            try:
                active_campaigns = [c.to_dict() for c in campaign_registry.active()]
            except Exception:
                active_campaigns = []
        return JSONResponse({
            "ok": True, "timestamp": time.time(),
            "checkpoint": checkpoint_summary,
            "warden": {"status": "operational"},
            "active_campaigns": active_campaigns,
        })

    @app.get("/api/campaigns")
    async def api_campaigns() -> JSONResponse:
        campaigns: list[dict] = []
        if campaign_registry is not None:
            try:
                for c in campaign_registry.recent(100):
                    d = c.to_dict()
                    d["progress"] = c.progress()
                    campaigns.append(d)
            except Exception as e:
                log.debug("Error fetching campaigns: %s", e)
        return JSONResponse({"ok": True, "campaigns": campaigns, "count": len(campaigns)})

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        try:
            from pradyos.core.healthcheck import get_health_registry
            reg = health_registry if health_registry is not None else get_health_registry()
            overall = reg.overall()
            probes = reg.run_all()
            return JSONResponse({"status": overall, "probes": [p.dict() for p in probes]})
        except Exception as e:
            log.debug("Health registry unavailable: %s", e)
            return JSONResponse({"status": "ok", "probes": []})

    @app.get("/api/analytics")
    async def api_analytics() -> JSONResponse:
        try:
            from pradyos.campaign.analytics import CampaignAnalytics
            reg = campaign_registry
            if reg is None:
                raise ValueError("no registry")
            analytics = CampaignAnalytics(registry=reg)
            return JSONResponse(analytics.to_dict())
        except Exception as e:
            log.debug("Analytics unavailable: %s", e)
            return JSONResponse({"success_rate": 0.0, "avg_duration_s": 0.0,
                                 "node_failure_histogram": {}, "busiest_hours": []})

    @app.get("/api/metrics")
    async def api_metrics() -> JSONResponse:
        try:
            from pradyos.core.metrics import get_registry
            snapshot = get_registry().snapshot()
        except Exception as exc:
            snapshot = {"error": str(exc)}
        return JSONResponse({"metrics": snapshot, "ts": time.time()})

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
            return JSONResponse({"recommendations": [r.to_dict() for r in recs], "ts": time.time()})
        except Exception as exc:
            log.debug("Recommendations unavailable: %s", exc)
            return JSONResponse({"recommendations": [], "ts": time.time()})

    @app.get("/api/v1/dashboard")
    async def api_dashboard() -> JSONResponse:
        _zero = {"bus_events": [], "quarantine": [], "system_health": {
            "status": "ok", "active_tasks": 0, "dead_letter_count": 0, "last_event_ts": None}}
        if observability_dashboard is None:
            return JSONResponse(_zero, status_code=200)
        try:
            snap = observability_dashboard.get_live_snapshot()
            return JSONResponse(snap.to_dict(), status_code=200)
        except Exception as exc:
            log.debug("ObservabilityDashboard.get_live_snapshot failed: %s", exc)
            return JSONResponse(_zero, status_code=200)

    @app.get("/api/v1/campaigns/monitor")
    async def api_campaigns_monitor() -> JSONResponse:
        _zero = {"active_campaigns": [], "step_timeline": [], "titan_ops_feed": []}
        if campaign_monitor is None:
            return JSONResponse(_zero, status_code=200)
        try:
            snap = campaign_monitor.get_snapshot()
            return JSONResponse(snap.to_dict(), status_code=200)
        except Exception as exc:
            log.debug("CampaignMonitor.get_snapshot failed: %s", exc)
            return JSONResponse(_zero, status_code=200)

    @app.get("/api/v1/policy/rules")
    async def api_policy_get_rules() -> JSONResponse:
        if policy_engine is None:
            return JSONResponse({"rules": []}, status_code=200)
        return JSONResponse({"rules": policy_engine.get_rules()}, status_code=200)

    @app.post("/api/v1/policy/rules")
    async def api_policy_set_rules(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        rules = body.get("rules", []) if isinstance(body, dict) else []
        if policy_engine is not None:
            policy_engine.load(rules)
        return JSONResponse({"loaded": len(rules)}, status_code=200)

    # ------------------------------------------------------------------
    # Phase 15 -- Sovereign Scheduler endpoints
    # ------------------------------------------------------------------

    @app.get("/api/v1/scheduler/jobs")
    async def api_scheduler_get_jobs() -> JSONResponse:
        if scheduler is None:
            return JSONResponse({"jobs": []}, status_code=200)
        return JSONResponse({"jobs": scheduler.get_jobs()}, status_code=200)

    @app.post("/api/v1/scheduler/jobs")
    async def api_scheduler_add_job(request: Request) -> JSONResponse:
        if scheduler is None:
            return JSONResponse(
                {"job_id": None, "cron_expr": None, "campaign_spec": {},
                 "priority": 5, "sla_seconds": None, "next_run": 0.0, "enabled": True},
                status_code=200,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        job = scheduler.add_job(
            job_id=body.get("job_id", ""),
            cron_expr=body.get("cron_expr", "* * * * *"),
            campaign_spec=body.get("campaign_spec", {}),
            priority=body.get("priority", 5),
            sla_seconds=body.get("sla_seconds", None),
        )
        return JSONResponse(job, status_code=200)

    @app.delete("/api/v1/scheduler/jobs/{job_id}")
    async def api_scheduler_remove_job(job_id: str) -> JSONResponse:
        if scheduler is None:
            return JSONResponse({"removed": False}, status_code=200)
        removed = scheduler.remove_job(job_id)
        return JSONResponse({"removed": removed}, status_code=200)

    @app.post("/api/v1/scheduler/jobs/{job_id}/enable")
    async def api_scheduler_enable_job(job_id: str) -> JSONResponse:
        if scheduler is None:
            return JSONResponse({"enabled": True}, status_code=200)
        scheduler.enable_job(job_id)
        return JSONResponse({"enabled": True}, status_code=200)

    @app.post("/api/v1/scheduler/jobs/{job_id}/disable")
    async def api_scheduler_disable_job(job_id: str) -> JSONResponse:
        if scheduler is None:
            return JSONResponse({"disabled": True}, status_code=200)
        scheduler.disable_job(job_id)
        return JSONResponse({"disabled": True}, status_code=200)

    # ------------------------------------------------------------------
    # Phase 16 -- Telemetry endpoint
    # ------------------------------------------------------------------

    @app.get("/api/v1/telemetry")
    async def api_telemetry(
        limit: int = 100,
        service: str | None = None,
        status: str | None = None,
    ) -> JSONResponse:
        if telemetry is None:
            return JSONResponse({"spans": [], "count": 0}, status_code=200)
        effective_limit = min(max(1, limit), 500)
        spans = telemetry.get_spans(
            limit=effective_limit,
            service=service if service else None,
            status=status if status else None,
        )
        data = [s.to_dict() for s in spans]
        return JSONResponse({"spans": data, "count": len(data)}, status_code=200)


    # ------------------------------------------------------------------
    # Phase 17 -- Memory Graph endpoints
    # ------------------------------------------------------------------

    @app.get("/api/v1/graph/stats")
    async def api_graph_stats() -> JSONResponse:
        if graph is None:
            return JSONResponse({"nodes": 0, "edges": 0}, status_code=200)
        return JSONResponse(graph.stats(), status_code=200)

    @app.get("/api/v1/graph/nodes")
    async def api_graph_nodes(
        kind: str | None = None,
        label: str | None = None,
        limit: int = 100,
    ) -> JSONResponse:
        if graph is None:
            return JSONResponse({"nodes": [], "count": 0}, status_code=200)
        nodes = graph.query_nodes(
            kind=kind if kind else None,
            label=label if label else None,
        )
        capped = nodes[:max(1, limit)]
        data = [n.to_dict() for n in capped]
        return JSONResponse({"nodes": data, "count": len(data)}, status_code=200)

    @app.post("/api/v1/graph/nodes")
    async def api_graph_add_node(request: Request) -> JSONResponse:
        if graph is None:
            return JSONResponse({"nodes": [], "count": 0}, status_code=200)
        try:
            body = await request.json()
        except Exception:
            body = {}
        node = graph.add_node(
            kind=body.get("kind", ""),
            label=body.get("label", ""),
            node_id=body.get("node_id") or None,
            attributes=body.get("attributes") or None,
        )
        return JSONResponse(node.to_dict(), status_code=200)

    @app.get("/api/v1/graph/nodes/{node_id}/neighbours")
    async def api_graph_neighbours(
        node_id: str,
        relation: str | None = None,
    ) -> JSONResponse:
        if graph is None:
            return JSONResponse({"neighbours": [], "count": 0}, status_code=200)
        neighbours = graph.neighbours(
            node_id=node_id,
            relation=relation if relation else None,
        )
        data = [n.to_dict() for n in neighbours]
        return JSONResponse({"neighbours": data, "count": len(data)}, status_code=200)

    @app.post("/api/approve/{task_id}")
    async def api_approve(task_id: str) -> JSONResponse:
        record = _write_decision(task_id, "approved")
        log.info("Sovereign APPROVED task %s", task_id)
        if bus is not None:
            bus.publish("sovereign.approved", {"task_id": task_id})
        return JSONResponse({"ok": True, "task_id": task_id, "decision": "approved", "ts": record["ts"]})

    @app.post("/api/reject/{task_id}")
    async def api_reject(task_id: str) -> JSONResponse:
        record = _write_decision(task_id, "rejected")
        log.info("Sovereign REJECTED task %s", task_id)
        if bus is not None:
            bus.publish("sovereign.rejected", {"task_id": task_id})
        return JSONResponse({"ok": True, "task_id": task_id, "decision": "rejected", "ts": record["ts"]})

    @app.get("/stream")
    async def stream_events() -> StreamingResponse:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        return StreamingResponse(
            _sse_generator(queue),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


    # ── Phase 18: Sovereign Event Ledger endpoints ──────────────────────────

    @app.get("/api/v1/ledger")
    async def api_ledger_entries(
        limit: int = 100,
        service: str | None = None,
        event: str | None = None,
    ) -> JSONResponse:
        if ledger is None:
            return JSONResponse({"entries": [], "count": 0})
        entries = ledger.get_entries(limit=limit, service=service, event=event)
        return JSONResponse({"entries": [e.to_dict() for e in entries], "count": len(entries)})

    @app.get("/api/v1/ledger/verify")
    async def api_ledger_verify() -> JSONResponse:
        if ledger is None:
            return JSONResponse({"valid": True, "count": 0})
        valid = ledger.verify()
        count = len(ledger)
        return JSONResponse({"valid": valid, "count": count})

    # ── Phase 19: Sovereign Intent Engine endpoints ─────────────────────────

    @app.get("/api/v1/intent/rules")
    async def api_intent_get_rules() -> JSONResponse:
        if intent is None:
            return JSONResponse({"rules": [], "count": 0}, status_code=200)
        rules = intent.get_rules()
        return JSONResponse({"rules": rules, "count": len(rules)}, status_code=200)

    @app.post("/api/v1/intent/rules")
    async def api_intent_load_rules(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        rules = body.get("rules", []) if isinstance(body, dict) else []
        if intent is not None:
            intent.load_rules(rules)
        return JSONResponse({"loaded": len(rules)}, status_code=200)

    @app.post("/api/v1/intent/suggest")
    async def api_intent_suggest(request: Request) -> JSONResponse:
        if intent is None:
            return JSONResponse({"suggestions": [], "count": 0}, status_code=200)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        suggestions = intent.suggest(
            graph_stats=body.get("graph_stats"),
            active_campaigns=body.get("active_campaigns"),
            recent_spans=body.get("recent_spans"),
            recent_entries=body.get("recent_entries"),
        )
        data = [s.to_dict() for s in suggestions]
        return JSONResponse({"suggestions": data, "count": len(data)}, status_code=200)



    # ── Phase 20: Sovereign Audit Trail UI ──────────────────────────────────

    @app.get("/audit", response_class=HTMLResponse, include_in_schema=False)
    async def audit_trail() -> HTMLResponse:
        return HTMLResponse(content=build_audit_html(), status_code=200)

    # ── Phase 21: Sovereign Config Hot-Reload ───────────────────────────────

    @app.get("/api/v1/config/status")
    async def config_status() -> JSONResponse:
        if config_reloader is not None:
            return JSONResponse(config_reloader.status(), status_code=200)
        return JSONResponse(
            {
                "running": False,
                "config_path": None,
                "last_reload": None,
                "poll_interval": None,
            },
            status_code=200,
        )

    @app.post("/api/v1/config/reload")
    async def config_reload() -> JSONResponse:
        import time as _time
        if config_reloader is not None:
            result = config_reloader.load()
            return JSONResponse(result.to_dict(), status_code=200)
        return JSONResponse(
            {
                "success": False,
                "error": "no reloader configured",
                "changes": [],
                "timestamp": _time.time(),
            },
            status_code=200,
        )

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> PlainTextResponse:
        if metrics is None:
            return PlainTextResponse(
                "",
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
        return PlainTextResponse(
            metrics.render_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/api/v1/metrics")
    async def api_metrics() -> JSONResponse:
        if metrics is None:
            return JSONResponse({})
        return JSONResponse(metrics.get_all())

    @app.get("/api/v1/ratelimit/status")
    async def api_ratelimit_status() -> JSONResponse:
        if rate_limiter is None:
            return JSONResponse({
                "active_clients": 0,
                "total_hits": 0,
                "rules": {},
                "default_limit": 0,
                "default_window": 0,
            })
        return JSONResponse(rate_limiter.status())

    @app.post("/api/v1/ratelimit/rules")
    async def api_ratelimit_set_rules(request: Request) -> JSONResponse:
        if rate_limiter is None:
            return JSONResponse({"set": False})
        body = await request.json()
        rate_limiter.set_rule(
            endpoint=body["endpoint"],
            limit=int(body["limit"]),
            window=float(body["window"]),
        )
        return JSONResponse({"set": True})

    @app.post("/api/v1/ratelimit/check")
    async def api_ratelimit_check(request: Request) -> JSONResponse:
        body = await request.json()
        client_id = body["client_id"]
        endpoint = body["endpoint"]
        if rate_limiter is None:
            return JSONResponse({
                "allowed": True,
                "client_id": client_id,
                "endpoint": endpoint,
                "limit": 0,
                "window_secs": 0,
                "current": 0,
                "retry_after": None,
            })
        result = rate_limiter.check(client_id=client_id, endpoint=endpoint)
        return JSONResponse(result.to_dict())

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

    @app.get("/api/v1/audit/replay")
    async def api_audit_replay(at: float | None = None) -> JSONResponse:
        import time as _time
        ts = at if at is not None else _time.time()
        if replay_engine is None:
            return JSONResponse(
                {"at": ts, "entries": [], "state": {}, "event_count": 0}
            )
        return JSONResponse(replay_engine.replay(ts).to_dict())

    return app


def _read_checkpoint_summary(checkpoint_store: Any) -> dict[str, Any]:
    if hasattr(checkpoint_store, "snapshot"):
        try:
            result = checkpoint_store.snapshot()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    if hasattr(checkpoint_store, "path"):
        try:
            p = Path(checkpoint_store.path)
            if p.exists():
                return {"file": str(p), "size_bytes": p.stat().st_size}
        except Exception:
            pass
    return {"status": "available"}



_DASHBOARD_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>PRADY OS -- Sovereign Dashboard</title>\n  <style>\n    * { box-sizing: border-box; margin: 0; padding: 0; }\n    body { background: #0a0a0f; color: #e0e0f0; font-family: \'Courier New\', monospace; }\n    header { background: #12121e; border-bottom: 1px solid #2a2a4a; padding: 1rem 2rem;\n             display: flex; align-items: center; justify-content: space-between; }\n    header h1 { font-size: 1.4rem; color: #7b8fff; letter-spacing: 2px; }\n    header .badge { font-size: 0.75rem; color: #4caf50; border: 1px solid #4caf50;\n                    padding: 2px 8px; border-radius: 4px; }\n    main { padding: 2rem; max-width: 1200px; margin: 0 auto; }\n    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }\n    .card { background: #12121e; border: 1px solid #2a2a4a; border-radius: 8px; padding: 1.2rem; }\n    .card h2 { font-size: 0.85rem; color: #7b8fff; text-transform: uppercase;\n                letter-spacing: 1px; margin-bottom: 0.8rem; }\n    .stat { display: flex; justify-content: space-between; padding: 4px 0;\n            border-bottom: 1px solid #1e1e32; font-size: 0.85rem; }\n    .stat:last-child { border-bottom: none; }\n    .stat .val { color: #a0cfff; }\n    #log { background: #0d0d16; border: 1px solid #2a2a4a; border-radius: 8px;\n           padding: 1rem; margin-top: 1rem; height: 200px; overflow-y: auto;\n           font-size: 0.8rem; color: #6a6a9a; }\n    #log p { padding: 2px 0; border-bottom: 1px solid #1a1a2e; }\n  </style>\n</head>\n<body>\n  <header>\n    <h1>PRADY OS -- SOVEREIGN</h1>\n    <span class="badge" id="status-badge">ONLINE</span>\n  </header>\n  <main>\n    <div class="grid">\n      <div class="card" id="status-card">\n        <h2>System Status</h2>\n        <div class="stat"><span>Kernel</span><span class="val" id="s-kernel">--</span></div>\n        <div class="stat"><span>Warden</span><span class="val" id="s-warden">--</span></div>\n        <div class="stat"><span>Campaigns</span><span class="val" id="s-campaigns">--</span></div>\n        <div class="stat"><span>Last refresh</span><span class="val" id="s-ts">--</span></div>\n      </div>\n      <div class="card">\n        <h2>Event Stream</h2>\n        <div id="log"><p>Connecting...</p></div>\n      </div>\n    </div>\n  </main>\n  <script>\n    async function fetchStatus() {\n      try {\n        const r = await fetch(\'/api/status\');\n        const d = await r.json();\n        document.getElementById(\'s-kernel\').textContent =\n          d.checkpoint && d.checkpoint.file ? \'checkpoint ok\' : \'active\';\n        document.getElementById(\'s-warden\').textContent =\n          d.warden ? d.warden.status : \'unknown\';\n        document.getElementById(\'s-campaigns\').textContent =\n          d.active_campaigns ? d.active_campaigns.length : \'0\';\n        document.getElementById(\'s-ts\').textContent =\n          new Date(d.timestamp * 1000).toLocaleTimeString();\n      } catch(e) { console.error(e); }\n    }\n    fetchStatus();\n    setInterval(fetchStatus, 5000);\n    const log = document.getElementById(\'log\');\n    log.innerHTML = \'\';\n    const es = new EventSource(\'/stream\');\n    es.onmessage = e => {\n      const p = document.createElement(\'p\');\n      p.textContent = e.data.slice(0, 120);\n      log.prepend(p);\n      if (log.children.length > 50) log.removeChild(log.lastChild);\n    };\n    es.onerror = () => {\n      const p = document.createElement(\'p\');\n      p.textContent = \'[stream disconnected]\';\n      log.prepend(p);\n    };\n  </script>\n</body>\n</html>'

def main() -> None:
    """Entry point: pradyos-web."""
    import uvicorn
    from pradyos.campaign.registry import CampaignRegistry
    from pradyos.core.bus import get_bus
    from pradyos.imperium.checkpoint import CheckpointStore
    bus = get_bus()
    registry = CampaignRegistry()
    checkpoint = CheckpointStore()
    app = create_app(campaign_registry=registry, checkpoint_store=checkpoint, bus=bus)
    log.info("Starting Sovereign Web Dashboard on 0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, loop="asyncio", log_level="info")


if __name__ == "__main__":
    main()
