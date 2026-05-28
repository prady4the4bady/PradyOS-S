"""Sovereign Web Dashboard (Phase 4C / Phase 5 extensions)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from pradyos.core.ledger import EventLedger
from pradyos.core.audit_replay import AuditReplayEngine  # Phase 25
from pradyos.core.bus_inspector import BusInspector  # Phase 27
from pradyos.core.decision_journal import DecisionJournal  # Phase 28
from pradyos.core.capability_registry import CapabilityRegistry  # Phase 29
from pradyos.core.watchpoint import WatchpointSystem  # Phase 30
from pradyos.core.signal_aggregator import SignalAggregator  # Phase 31
from pradyos.core.snapshot_store import SnapshotStore  # Phase 32
from pradyos.core.correlation_engine import CorrelationEngine  # Phase 33
from pradyos.core.integration_bus import SovereignBus  # Phase 34
from pradyos.core.reactor import ReactorEngine  # Phase 35
from pradyos.core.state_manager import StateManager  # Phase 36
from pradyos.core.healing_monitor import HealingMonitor  # Phase 37
from pradyos.core.scheduler import TaskScheduler as CoreTaskScheduler  # Phase 38
from pradyos.core.memory_store import MemoryStore  # Phase 39
from pradyos.core.control_plane import ControlPlane, VERSION as OS_VERSION  # Phase 40
from pradyos.core.heartbeat import HeartbeatLoop  # Phase 41
from pradyos.core.guardrail import GuardrailGate, RiskLevel  # Phase 43
from pradyos.core.approval_queue import ApprovalQueue, ApprovalStatus  # Phase 43
from pradyos.core.execution_engine import ExecutionEngine, ExecutionStatus  # Phase 44
from pradyos.core.reasoning_engine import ReasoningEngine  # Phase 45
from pradyos.core.web_agent import WebAgent  # Phase 46
from pradyos.core.memory_graph import MemoryGraph as Phase47MemoryGraph  # Phase 47
from pradyos.core.event_store import EventStore  # Phase 48
from pradyos.core.task_queue import TaskQueue  # Phase 49
from pradyos.core.pubsub import PubSubBroker  # Phase 50
from pradyos.core.statesync import StateSyncManager  # Phase 51
from pradyos.core.distributed_lock import LockManager  # Phase 52
from pradyos.core.circuit_breaker import CircuitBreaker, BreakerState  # Phase 53
from pradyos.core.retry_policy import RetryPolicy  # Phase 54
from pradyos.core.bulkhead_pool import BulkheadManager, BulkheadRejectedError  # Phase 55
from pradyos.core.timeout_guard import TimeoutGuard, TimeoutExpiredError  # Phase 56
from pradyos.core.semaphore_gate import SemaphoreGate, SemaphoreNotFoundError  # Phase 57
from pradyos.core.event_filter import EventFilterRegistry, FilterRule  # Phase 58
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
    plugin_sandbox: Any | None = None,
    bus_inspector: Any | None = None,
    decision_journal: Any | None = None,
    capability_registry: Any | None = None,
    watchpoint_system: Any | None = None,
    signal_aggregator: Any | None = None,
    snapshot_store: Any | None = None,
    correlation_engine: Any | None = None,
    integration_bus: Any | None = None,
    reactor_engine: Any | None = None,
    state_manager: Any | None = None,
    healing_monitor: Any | None = None,
    task_scheduler: Any | None = None,
    memory_store: Any | None = None,
    control_plane: Any | None = None,
    heartbeat: Any | None = None,
    guardrail_gate: Any | None = None,
    approval_queue: Any | None = None,
    execution_engine: Any | None = None,
    reasoning_engine: Any | None = None,
    web_agent: Any | None = None,
    memory_graph: Any | None = None,
    event_store: Any | None = None,
    task_queue: Any | None = None,
    pubsub: Any | None = None,
    statesync: Any | None = None,
    lock_manager: Any | None = None,
    circuit_breaker: Any | None = None,
    retry_policy: Any | None = None,
    bulkhead_manager: Any | None = None,
    timeout_guard: Any | None = None,
    semaphore_gate: Any | None = None,
    event_filter_registry: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    @asynccontextmanager
    async def _lifespan(app):
        if heartbeat is not None:
            await heartbeat.start()
        yield
        if heartbeat is not None:
            await heartbeat.stop()

    app = FastAPI(title="PRADY OS -- Sovereign Dashboard", version="5.0", docs_url="/docs", lifespan=_lifespan)

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

    @app.get("/api/v1/plugins")
    async def api_plugins_list() -> JSONResponse:
        if plugin_sandbox is None:
            return JSONResponse({"plugins": [], "status": {}})
        return JSONResponse({
            "plugins": [p.to_dict() for p in plugin_sandbox.get_plugins()],
            "status": plugin_sandbox.status(),
        })

    @app.post("/api/v1/plugins/reload")
    async def api_plugins_reload() -> JSONResponse:
        if plugin_sandbox is None:
            return JSONResponse({"reloaded": 0, "plugins": []})
        result = plugin_sandbox.reload_all()
        return JSONResponse({
            "reloaded": len(result),
            "plugins": [p.to_dict() for p in result.values()],
        })

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



    @app.get("/api/v1/watchpoints")
    async def api_watchpoints_get() -> JSONResponse:
        if watchpoint_system is None:
            return JSONResponse({"watchpoints": [], "status": {}})
        return JSONResponse({
            "watchpoints": [w.to_dict() for w in watchpoint_system.get_watchpoints()],
            "status": watchpoint_system.status(),
        })

    @app.post("/api/v1/watchpoints")
    async def api_watchpoints_post(request: Request) -> JSONResponse:
        if watchpoint_system is None:
            return JSONResponse({"error": "no watchpoint system configured"})
        body = await request.json()
        wp = watchpoint_system.register(
            name=body["name"],
            metric=body["metric"],
            operator=body["operator"],
            threshold=float(body["threshold"]),
            severity=body.get("severity", "warn"),
            enabled=bool(body.get("enabled", True)),
        )
        return JSONResponse(wp.to_dict())

    @app.post("/api/v1/watchpoints/check")
    async def api_watchpoints_check(request: Request) -> JSONResponse:
        if watchpoint_system is None:
            return JSONResponse({"alerts": [], "count": 0})
        body = await request.json()
        fired = watchpoint_system.check(
            metric=body["metric"],
            value=float(body["value"]),
        )
        return JSONResponse({"alerts": [a.to_dict() for a in fired], "count": len(fired)})


    @app.get("/api/v1/signals")
    async def api_signals_list() -> JSONResponse:
        if signal_aggregator is None:
            return JSONResponse({"signals": []})
        return JSONResponse({"signals": signal_aggregator.list_signals()})

    @app.post("/api/v1/signals")
    async def api_signals_record(request: Request) -> JSONResponse:
        if signal_aggregator is None:
            return JSONResponse({"error": "no signal aggregator configured"})
        body = await request.json()
        pt = signal_aggregator.record(
            name=body["name"],
            value=float(body["value"]),
            timestamp=body.get("timestamp"),
        )
        return JSONResponse(pt.to_dict())

    @app.get("/api/v1/signals/{name}")
    async def api_signals_get(name: str, request: Request) -> JSONResponse:
        if signal_aggregator is None:
            return JSONResponse({"name": name, "points": [], "count": 0, "stats": None})
        try:
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        points = signal_aggregator.get(name, limit=limit)
        return JSONResponse({
            "name": name,
            "points": [pt.to_dict() for pt in points],
            "count": len(points),
            "stats": signal_aggregator.stats(name),
        })


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


    @app.get("/api/v1/correlate")
    async def api_correlate_get(request: Request) -> JSONResponse:
        if correlation_engine is None:
            return JSONResponse({"error": "no correlation engine configured"})
        sa = request.query_params.get("signal_a")
        sb = request.query_params.get("signal_b")
        if not sa or not sb:
            return JSONResponse({"error": "signal_a and signal_b are required"})
        try:
            window = float(request.query_params.get("window", 3600))
        except (ValueError, TypeError):
            window = 3600.0
        result = correlation_engine.correlate(sa, sb, window_secs=window)
        return JSONResponse(result.to_dict())

    @app.post("/api/v1/correlate")
    async def api_correlate_post(request: Request) -> JSONResponse:
        if correlation_engine is None:
            return JSONResponse({"error": "no correlation engine configured"})
        body = await request.json()
        sa = body.get("signal_a")
        sb = body.get("signal_b")
        if not sa or not sb:
            return JSONResponse({"error": "signal_a and signal_b are required"})
        window = float(body.get("window", 3600))
        result = correlation_engine.correlate(sa, sb, window_secs=window)
        return JSONResponse(result.to_dict())


    @app.get("/api/v1/integration/status")
    async def api_integration_status() -> JSONResponse:
        if integration_bus is None:
            return JSONResponse({"wired": {}, "wire_count": 0})
        return JSONResponse(integration_bus.status())


    @app.get("/api/v1/reactor/rules")
    async def api_reactor_rules_list() -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"rules": []})
        return JSONResponse({"rules": reactor_engine.list_rules()})

    @app.post("/api/v1/reactor/rules")
    async def api_reactor_rules_add(request: Request) -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"error": "no reactor configured"})
        body = await request.json()
        rule = reactor_engine.add_rule(
            decision_type=body["decision_type"],
            action=body["action"],
            context_filter=body.get("context_filter"),
        )
        return JSONResponse(rule.to_dict())

    @app.delete("/api/v1/reactor/rules/{rule_id}")
    async def api_reactor_rules_delete(rule_id: str) -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = reactor_engine.remove_rule(rule_id)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/reactor/log")
    async def api_reactor_log(request: Request) -> JSONResponse:
        if reactor_engine is None:
            return JSONResponse({"reactions": []})
        try:
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        return JSONResponse({
            "reactions": [r.to_dict() for r in reactor_engine.get_log(limit)],
        })


    @app.post("/api/v1/os/shutdown")
    async def api_os_shutdown(request: Request) -> JSONResponse:
        if state_manager is None:
            return JSONResponse({"results": [], "message": "no state manager"})
        results = state_manager.shutdown()
        return JSONResponse({"results": results})

    @app.get("/api/v1/os/state/{module}")
    async def api_os_state_list(module: str) -> JSONResponse:
        if state_manager is None or state_manager._store is None:
            return JSONResponse({"module": module, "keys": []})
        return JSONResponse({
            "module": module,
            "keys": state_manager._store.list_keys(module),
        })

    @app.get("/api/v1/os/state/{module}/{key}")
    async def api_os_state_get(module: str, key: str, request: Request) -> JSONResponse:
        if state_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        raw = request.query_params.get("version")
        version = int(raw) if raw is not None else None
        result = state_manager.load_state(module, key, version=version)
        if result is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(result)

    @app.post("/api/v1/os/state/{module}/{key}")
    async def api_os_state_save(module: str, key: str, request: Request) -> JSONResponse:
        if state_manager is None or state_manager._store is None:
            return JSONResponse({"error": "no state manager configured"})
        body = await request.json()
        result = state_manager.save_state(module, key, body["data"])
        return JSONResponse(result)

    @app.get("/api/v1/os/status")
    async def api_os_status() -> JSONResponse:
        if state_manager is None:
            return JSONResponse({
                "store_connected": False,
                "registered_modules": [],
                "hook_count": 0,
            })
        return JSONResponse(state_manager.status())


    @app.get("/api/v1/healer/components")
    async def api_healer_components() -> JSONResponse:
        if healing_monitor is None:
            return JSONResponse({"components": []})
        return JSONResponse({"components": healing_monitor.list_components()})

    @app.post("/api/v1/healer/check")
    async def api_healer_check() -> JSONResponse:
        if healing_monitor is None:
            return JSONResponse({"healed": []})
        events = healing_monitor.check_and_heal()
        return JSONResponse({"healed": [e.to_dict() for e in events]})

    @app.get("/api/v1/healer/log")
    async def api_healer_log(request: Request) -> JSONResponse:
        if healing_monitor is None:
            return JSONResponse({"events": []})
        try:
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            limit = 100
        return JSONResponse({
            "events": [e.to_dict() for e in healing_monitor.get_log(limit)],
        })


    @app.get("/api/v1/scheduler/tasks")
    async def api_scheduler_tasks_list() -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"tasks": []})
        return JSONResponse({"tasks": task_scheduler.list_tasks()})

    @app.post("/api/v1/scheduler/tasks")
    async def api_scheduler_tasks_add(request: Request) -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"error": "no scheduler configured"})
        body = await request.json()
        task = task_scheduler.register(
            name=body["name"],
            interval_seconds=float(body["interval_seconds"]),
            fn=lambda: None,
        )
        return JSONResponse(task.to_dict())

    @app.delete("/api/v1/scheduler/tasks/{name}")
    async def api_scheduler_tasks_delete(name: str) -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = task_scheduler.unregister(name)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.post("/api/v1/scheduler/tick")
    async def api_scheduler_tick() -> JSONResponse:
        if task_scheduler is None:
            return JSONResponse({"runs": []})
        runs = task_scheduler.tick()
        return JSONResponse({"runs": [r.to_dict() for r in runs]})


    @app.get("/api/v1/memory/search")
    async def api_memory_search(request: Request) -> JSONResponse:
        tag = request.query_params.get("tag")
        if memory_store is None or not tag:
            return JSONResponse({"entries": []})
        return JSONResponse({
            "entries": [e.to_dict() for e in memory_store.search(tag)],
        })

    @app.post("/api/v1/memory/expire")
    async def api_memory_expire() -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"expired": 0})
        return JSONResponse({"expired": memory_store.expire()})

    @app.post("/api/v1/memory/{key}")
    async def api_memory_store(key: str, request: Request) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "no memory store configured"})
        body = await request.json()
        entry = memory_store.store(
            key=key,
            value=body["value"],
            tags=body.get("tags") or [],
            ttl=body.get("ttl"),
        )
        return JSONResponse(entry.to_dict())

    @app.get("/api/v1/memory/{key}")
    async def api_memory_recall(key: str) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        entry = memory_store.recall(key)
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(entry.to_dict())

    @app.delete("/api/v1/memory/{key}")
    async def api_memory_forget(key: str) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        removed = memory_store.forget(key)
        if not removed:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})


    @app.get("/api/v1/os/control")
    async def api_os_control() -> JSONResponse:
        if control_plane is None:
            return JSONResponse({
                "os_version": OS_VERSION,
                "uptime_seconds": 0,
                "modules": {},
            })
        return JSONResponse(control_plane.status())

    @app.post("/api/v1/os/tick")
    async def api_os_tick() -> JSONResponse:
        if control_plane is None:
            return JSONResponse({"ticks": [], "healed": [], "reactions": []})
        return JSONResponse(control_plane.tick())


    @app.get("/api/v1/heartbeat/status")
    async def api_heartbeat_status() -> JSONResponse:
        if heartbeat is None:
            return JSONResponse({
                "running": False,
                "tick_count": 0,
                "interval_seconds": 0,
            })
        return JSONResponse(heartbeat.status())

    @app.post("/api/v1/heartbeat/stop")
    async def api_heartbeat_stop() -> JSONResponse:
        if heartbeat is None:
            return JSONResponse({"stopped": False})
        await heartbeat.stop()
        return JSONResponse({"stopped": True})


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


    @app.get("/api/v1/execute/status")
    async def api_execute_status() -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({
                "allowlist": [],
                "total_runs": 0,
                "last_status": None,
            })
        return JSONResponse(execution_engine.status())

    @app.get("/api/v1/execute/history")
    async def api_execute_history(request: Request) -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({"results": []})
        try:
            limit = int(request.query_params.get("limit", 50))
        except (ValueError, TypeError):
            limit = 50
        return JSONResponse({
            "results": [r.to_dict() for r in execution_engine.history(limit)],
        })

    @app.post("/api/v1/execute/{entry_id}")
    async def api_execute_run(entry_id: str) -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({"error": "no execution engine configured"}, status_code=400)
        if approval_queue is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        entry = approval_queue.get(entry_id)
        if entry is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        result = execution_engine.run(entry)
        return JSONResponse(result.to_dict())


    @app.get("/api/v1/reason/status")
    async def api_reason_status() -> JSONResponse:
        if reasoning_engine is None:
            return JSONResponse({"rule_count": 0, "auto_approve_levels": []})
        return JSONResponse(reasoning_engine.status())

    @app.post("/api/v1/reason/rules")
    async def api_reason_add_rule(request: Request) -> JSONResponse:
        if reasoning_engine is None:
            return JSONResponse({"error": "no reasoning engine configured"}, status_code=400)
        body = await request.json()
        try:
            reasoning_engine.add_rule(body)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"rule_count": reasoning_engine.rule_count()})

    @app.post("/api/v1/reason")
    async def api_reason(request: Request) -> JSONResponse:
        if reasoning_engine is None:
            return JSONResponse({"error": "no reasoning engine configured"}, status_code=400)
        body = await request.json()
        if "goal" not in body:
            return JSONResponse({"error": "missing 'goal' key"}, status_code=400)
        plan = reasoning_engine.plan(
            goal=str(body["goal"]),
            state=body.get("state") or {},
        )
        return JSONResponse(plan.to_dict())


    @app.get("/api/v1/web/status")
    async def api_web_status() -> JSONResponse:
        if web_agent is None:
            return JSONResponse({
                "cache_enabled": False,
                "guardrail_enabled": False,
                "max_age": 3600,
                "timeout": 10,
            })
        return JSONResponse(web_agent.status())

    @app.get("/api/v1/web/fetch")
    async def api_web_fetch(url: str) -> JSONResponse:
        if web_agent is None:
            return JSONResponse({"error": "no web agent configured"}, status_code=400)
        result = web_agent.fetch(url)
        return JSONResponse(result.to_dict())

    @app.post("/api/v1/web/search")
    async def api_web_search(request: Request) -> JSONResponse:
        if web_agent is None:
            return JSONResponse({"error": "no web agent configured"}, status_code=400)
        body = await request.json()
        if "query" not in body:
            return JSONResponse({"error": "missing 'query' key"}, status_code=400)
        max_results = int(body.get("max_results", 5))
        results = web_agent.search(query=str(body["query"]), max_results=max_results)
        return JSONResponse({"results": [r.to_dict() for r in results]})


    @app.get("/api/v1/memgraph/nodes")
    async def api_memgraph_nodes_list() -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"nodes": [], "count": 0})
        return JSONResponse({
            "nodes": [n.to_dict() for n in memory_graph._nodes.values()],
            "count": memory_graph.node_count(),
        })

    @app.post("/api/v1/memgraph/nodes")
    async def api_memgraph_nodes_add(request: Request) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"error": "no memory graph configured"}, status_code=400)
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing 'name' key"}, status_code=400)
        node = memory_graph.add_node(
            name=str(body["name"]),
            metadata=body.get("metadata"),
        )
        return JSONResponse(node.to_dict())

    @app.post("/api/v1/memgraph/edges")
    async def api_memgraph_edges_add(request: Request) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"error": "no memory graph configured"}, status_code=400)
        body = await request.json()
        for key in ("src", "dst", "relation"):
            if key not in body:
                return JSONResponse(
                    {"error": f"missing required key: {key}"},
                    status_code=400,
                )
        edge = memory_graph.add_edge(
            src=str(body["src"]),
            dst=str(body["dst"]),
            relation=str(body["relation"]),
            weight=float(body.get("weight", 1.0)),
        )
        return JSONResponse(edge.to_dict())

    @app.get("/api/v1/memgraph/neighbors/{name}")
    async def api_memgraph_neighbors(name: str, request: Request) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"name": name, "neighbors": []})
        relation = request.query_params.get("relation")
        neighbors = memory_graph.get_neighbors(name, relation=relation)
        return JSONResponse({
            "name": name,
            "neighbors": [n.to_dict() for n in neighbors],
        })

    @app.get("/api/v1/memgraph/path")
    async def api_memgraph_path(src: str, dst: str) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"src": src, "dst": dst, "path": None})
        path = memory_graph.shortest_path(src, dst)
        return JSONResponse({"src": src, "dst": dst, "path": path})


    @app.get("/api/v1/events/{stream}")
    async def api_events_read(stream: str, request: Request) -> JSONResponse:
        if event_store is None:
            return JSONResponse({"stream": stream, "events": [], "count": 0})
        try:
            from_seq = int(request.query_params.get("from_seq", 0))
        except (ValueError, TypeError):
            from_seq = 0
        events = event_store.read(stream, from_seq=from_seq)
        return JSONResponse({
            "stream": stream,
            "events": [e.to_dict() for e in events],
            "count": len(events),
        })

    @app.post("/api/v1/events/{stream}/project")
    async def api_events_project(stream: str, request: Request) -> JSONResponse:
        if event_store is None:
            return JSONResponse({"stream": stream, "state": {}})
        body = await request.json()
        if "reducer_steps" not in body:
            return JSONResponse({"error": "missing 'reducer_steps' key"}, status_code=400)
        initial = body.get("initial") or {}
        steps = body["reducer_steps"]

        def _reducer(state: dict, event) -> dict:
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if step.get("match_type") == event.event_type:
                    state.update(step.get("updates") or {})
                    break
            return state

        state = event_store.project(stream, _reducer, initial=initial)
        return JSONResponse({"stream": stream, "state": state})

    @app.post("/api/v1/events/{stream}")
    async def api_events_append(stream: str, request: Request) -> JSONResponse:
        if event_store is None:
            return JSONResponse({"error": "no event store configured"}, status_code=400)
        body = await request.json()
        if "event_type" not in body:
            return JSONResponse({"error": "missing 'event_type' key"}, status_code=400)
        event = event_store.append(
            stream=stream,
            event_type=str(body["event_type"]),
            payload=body.get("payload") or {},
        )
        return JSONResponse(event.to_dict())


    @app.post("/api/v1/tasks")
    async def api_tasks_submit(request: Request) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"error": "no task queue configured"}, status_code=400)
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing 'name' key"}, status_code=400)
        task = task_queue.submit(
            name=str(body["name"]),
            payload=body.get("payload") or {},
            priority=int(body.get("priority", 5)),
        )
        return JSONResponse(task.to_dict())

    @app.get("/api/v1/tasks")
    async def api_tasks_list(request: Request) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"tasks": [], "count": 0})
        status = request.query_params.get("status")
        tasks = task_queue.list_tasks(status=status)
        return JSONResponse({
            "tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
        })

    @app.get("/api/v1/tasks/{task_id}")
    async def api_tasks_get(task_id: str) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        task = task_queue.get(task_id)
        if task is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(task.to_dict())

    @app.delete("/api/v1/tasks/{task_id}")
    async def api_tasks_cancel(task_id: str) -> JSONResponse:
        if task_queue is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        task = task_queue.get(task_id)
        if task is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        cancelled = task_queue.cancel(task_id)
        if not cancelled:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"cancelled": True})


    @app.get("/api/v1/pubsub/topics")
    async def api_pubsub_topics() -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"topics": [], "count": 0})
        topics = pubsub.list_topics()
        return JSONResponse({"topics": topics, "count": len(topics)})

    @app.get("/api/v1/pubsub/{topic}/subscribers")
    async def api_pubsub_subscribers(topic: str) -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"topic": topic, "subscriber_count": 0})
        return JSONResponse({
            "topic": topic,
            "subscriber_count": pubsub.count_subscribers(topic),
        })

    @app.post("/api/v1/pubsub/{topic}")
    async def api_pubsub_publish(topic: str, request: Request) -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"error": "no pubsub configured"}, status_code=400)
        body = await request.json()
        if "message" not in body:
            return JSONResponse({"error": "missing 'message' key"}, status_code=400)
        message = body["message"] if isinstance(body["message"], dict) else {"value": body["message"]}
        notified = pubsub.publish(topic, message)
        return JSONResponse({"topic": topic, "notified": notified})


    @app.get("/api/v1/statesync/sessions")
    async def api_statesync_list(request: Request) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"sessions": [], "count": 0})
        flag = (request.query_params.get("active_only") or "").lower()
        active_only = flag in ("true", "1", "yes")
        sessions = statesync.list_sessions(active_only=active_only)
        return JSONResponse({
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions),
        })

    @app.post("/api/v1/statesync/sessions")
    async def api_statesync_create(request: Request) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"error": "no statesync configured"}, status_code=400)
        body = await request.json()
        for key in ("broker_a", "broker_b", "topics_a", "topics_b"):
            if key not in body:
                return JSONResponse(
                    {"error": f"missing required key: {key}"},
                    status_code=400,
                )
        try:
            session = statesync.create_session(
                broker_a_name=str(body["broker_a"]),
                broker_b_name=str(body["broker_b"]),
                topics_a=list(body["topics_a"]),
                topics_b=list(body["topics_b"]),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(session.to_dict())

    @app.delete("/api/v1/statesync/sessions/{session_id}")
    async def api_statesync_stop(session_id: str) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = statesync.stop_session(session_id)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"stopped": True})


    @app.get("/api/v1/locks")
    async def api_locks_list() -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"locks": [], "count": 0})
        locks = lock_manager.list_locks()
        return JSONResponse({"locks": locks, "count": len(locks)})

    @app.post("/api/v1/locks")
    async def api_locks_acquire(request: Request) -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"error": "no lock manager configured"}, status_code=400)
        body = await request.json()
        for key in ("name", "holder_id"):
            if key not in body:
                return JSONResponse(
                    {"error": f"missing required key: {key}"},
                    status_code=400,
                )
        ttl = float(body.get("ttl", 30))
        lock = lock_manager.acquire(
            name=str(body["name"]),
            holder_id=str(body["holder_id"]),
            ttl=ttl,
        )
        if lock is None:
            return JSONResponse({"error": "already locked"}, status_code=409)
        return JSONResponse(lock.to_dict())

    @app.post("/api/v1/locks/{name}/refresh")
    async def api_locks_refresh(name: str, request: Request) -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        if "holder_id" not in body:
            return JSONResponse(
                {"error": "missing required key: holder_id"},
                status_code=400,
            )
        ttl = float(body.get("ttl", 30))
        ok = lock_manager.refresh(name=name, holder_id=str(body["holder_id"]), ttl=ttl)
        if not ok:
            return JSONResponse({"error": "not found or wrong holder"}, status_code=404)
        return JSONResponse({"refreshed": True})

    @app.delete("/api/v1/locks/{name}")
    async def api_locks_release(name: str, holder_id: str) -> JSONResponse:
        if lock_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = lock_manager.release(name=name, holder_id=holder_id)
        if not ok:
            return JSONResponse({"error": "not found or wrong holder"}, status_code=404)
        return JSONResponse({"released": True})


    @app.get("/api/v1/breakers")
    async def api_breakers_list() -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"breakers": [], "count": 0})
        return JSONResponse({
            "breakers": circuit_breaker.list_breakers(),
            "count": circuit_breaker.count(),
        })

    @app.post("/api/v1/breakers")
    async def api_breakers_register(request: Request) -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"error": "no circuit breaker configured"}, status_code=400)
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        name = str(body["name"])
        # Ensure breaker state exists by triggering create-or-get.
        with circuit_breaker._lock:
            bs = circuit_breaker._get_or_create_locked(name)
        return JSONResponse(bs.to_dict())

    @app.post("/api/v1/breakers/{name}/reset")
    async def api_breakers_reset(name: str) -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = circuit_breaker.reset(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"reset": True})

    @app.get("/api/v1/breakers/{name}")
    async def api_breakers_get(name: str) -> JSONResponse:
        if circuit_breaker is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        bs = circuit_breaker.get_state(name)
        if bs is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(bs.to_dict())


    @app.get("/api/v1/retry")
    async def api_retry_list() -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"names": [], "count": 0})
        return JSONResponse({
            "names": retry_policy.list_names(),
            "count": retry_policy.count(),
        })

    @app.post("/api/v1/retry/execute")
    async def api_retry_execute(request: Request) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"error": "no retry policy configured"})
        body = await request.json()
        name = str(body.get("name", "default"))
        should_fail = bool(body.get("should_fail", False))
        fail_attempts = int(body.get("fail_attempts", 0))

        # Built-in test fn: fails the first `fail_attempts` calls, then succeeds.
        counter = {"n": 0}

        def _test_fn():
            counter["n"] += 1
            if should_fail and counter["n"] <= fail_attempts:
                raise RuntimeError("simulated failure")
            return "ok"

        result: str | None = None
        error: str | None = None
        try:
            result = retry_policy.execute(name, _test_fn)
        except Exception as exc:
            error = repr(exc)

        attempts = len(retry_policy.get_history(name))
        return JSONResponse({
            "name": name,
            "result": result,
            "attempts": attempts,
            "error": error,
        })

    @app.get("/api/v1/retry/{name}/history")
    async def api_retry_history(name: str) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"name": name, "history": []})
        return JSONResponse({
            "name": name,
            "history": retry_policy.get_history(name),
        })

    @app.delete("/api/v1/retry/{name}/history")
    async def api_retry_clear(name: str) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = retry_policy.clear_history(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"cleared": True})


    @app.get("/api/v1/bulkheads")
    async def api_bulkheads_list() -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"pools": []})
        return JSONResponse({"pools": bulkhead_manager.list_pools()})

    @app.post("/api/v1/bulkheads")
    async def api_bulkheads_create(request: Request) -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"error": "no bulkhead manager configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        try:
            pool = bulkhead_manager.create(
                name=str(body["name"]),
                max_workers=int(body.get("max_workers", 4)),
                queue_depth=int(body.get("queue_depth", 8)),
            )
        except ValueError:
            return JSONResponse({"error": "pool already exists"})
        return JSONResponse(pool.get_stats().to_dict())

    @app.post("/api/v1/bulkheads/{name}/submit")
    async def api_bulkheads_submit(name: str, request: Request) -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        pool = bulkhead_manager.get(name)
        if pool is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        sleep_s = float(body.get("sleep", 0.0))

        import time as _time

        def _no_op() -> str:
            if sleep_s > 0:
                _time.sleep(sleep_s)
            return "ok"

        try:
            pool.submit(_no_op)
        except BulkheadRejectedError:
            return JSONResponse(
                {
                    "name": name,
                    "submitted": False,
                    "error": "BulkheadRejectedError",
                },
                status_code=429,
            )
        return JSONResponse({
            "name": name,
            "submitted": True,
            "stats": pool.get_stats().to_dict(),
        })

    @app.get("/api/v1/bulkheads/{name}")
    async def api_bulkheads_get(name: str) -> JSONResponse:
        if bulkhead_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        pool = bulkhead_manager.get(name)
        if pool is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(pool.get_stats().to_dict())


    @app.get("/api/v1/timeouts")
    async def api_timeouts_list() -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"names": [], "total": 0})
        return JSONResponse({
            "names": timeout_guard.list_names(),
            "total": timeout_guard.count(),
        })

    @app.post("/api/v1/timeouts/execute")
    async def api_timeouts_execute(request: Request) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"error": "no timeout guard configured"})
        body = await request.json()
        name = str(body.get("name", "default"))
        sleep_s = float(body.get("sleep", 0.0))
        should_error = bool(body.get("should_error", False))
        timeout_v = body.get("timeout")
        timeout_v = float(timeout_v) if timeout_v is not None else None

        import time as _time

        def _no_op() -> str:
            if sleep_s > 0:
                _time.sleep(sleep_s)
            if should_error:
                raise RuntimeError("forced")
            return "ok"

        try:
            result = timeout_guard.execute(name, _no_op, timeout=timeout_v)
        except TimeoutExpiredError as exc:
            return JSONResponse(
                {"name": name, "outcome": "timeout", "error": str(exc)},
                status_code=408,
            )
        except Exception as exc:
            return JSONResponse(
                {"name": name, "outcome": "error", "error": str(exc)},
                status_code=500,
            )

        history = timeout_guard.get_history(name)
        last_record = history[-1].to_dict() if history else None
        return JSONResponse({
            "name": name,
            "outcome": "success",
            "elapsed": last_record["elapsed"] if last_record else 0.0,
            "record": last_record,
        })

    @app.get("/api/v1/timeouts/{name}/history")
    async def api_timeouts_history(name: str) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"name": name, "records": []})
        records = timeout_guard.get_history(name)
        return JSONResponse({
            "name": name,
            "records": [r.to_dict() for r in records],
        })

    @app.delete("/api/v1/timeouts/{name}/history")
    async def api_timeouts_clear(name: str) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = timeout_guard.clear_history(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"cleared": True})


    @app.get("/api/v1/semaphores")
    async def api_semaphores_list() -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"names": [], "count": 0})
        names = semaphore_gate.list_names()
        return JSONResponse({"names": names, "count": len(names)})

    @app.post("/api/v1/semaphores")
    async def api_semaphores_create(request: Request) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "no semaphore gate configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        capacity = int(body.get("capacity", 1))
        try:
            stats = semaphore_gate.create(name=str(body["name"]), capacity=capacity)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return JSONResponse(stats.to_dict())

    @app.post("/api/v1/semaphores/{name}/acquire")
    async def api_semaphores_acquire(name: str, request: Request) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        # Default to 5s cap for HTTP safety — never block indefinitely from a web call.
        raw_timeout = body.get("timeout", 5.0)
        timeout_v = None if raw_timeout is None else float(raw_timeout)
        try:
            ok = semaphore_gate.acquire(name, timeout=timeout_v)
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "name": name,
            "acquired": bool(ok),
            "stats": stats.to_dict(),
        })

    @app.post("/api/v1/semaphores/{name}/release")
    async def api_semaphores_release(name: str) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            semaphore_gate.release(name)
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "name": name,
            "released": True,
            "stats": stats.to_dict(),
        })

    @app.get("/api/v1/semaphores/{name}")
    async def api_semaphores_get(name: str) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(stats.to_dict())


    @app.get("/api/v1/filters")
    async def api_filters_list() -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"names": [], "count": 0})
        names = event_filter_registry.list_names()
        return JSONResponse({"names": names, "count": len(names)})

    @app.post("/api/v1/filters")
    async def api_filters_create(request: Request) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "no filter registry configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        mode = str(body.get("mode", "AND"))
        if mode not in ("AND", "OR"):
            return JSONResponse({"error": "mode must be AND or OR"}, status_code=400)
        rules_raw = body.get("rules") or []
        rules = []
        for r in rules_raw:
            if not isinstance(r, dict):
                continue
            rules.append(FilterRule(
                field=str(r.get("field", "")),
                op=str(r.get("op", "")),
                value=r.get("value"),
            ))
        name = str(body["name"])
        filt = event_filter_registry.register(name, rules, mode)
        result = {"name": name}
        result.update(filt.to_dict())
        return JSONResponse(result)

    @app.post("/api/v1/filters/{name}/apply")
    async def api_filters_apply(name: str, request: Request) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        events = body.get("events") or []
        if not isinstance(events, list):
            events = []
        try:
            matched = event_filter_registry.apply(name, events)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "name": name,
            "matched": len(matched),
            "events": matched,
        })

    @app.delete("/api/v1/filters/{name}")
    async def api_filters_delete(name: str) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = event_filter_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

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
