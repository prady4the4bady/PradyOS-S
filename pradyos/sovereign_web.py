"""Sovereign Web Dashboard (Phase 4C / Phase 5 extensions)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from pradyos.core.anomaly_watch import SourceNotFoundError  # Phase 71
from pradyos.core.approval_queue import ApprovalStatus  # Phase 43
from pradyos.core.bulkhead_pool import BulkheadRejectedError  # Phase 55
from pradyos.core.control_plane import VERSION as OS_VERSION
from pradyos.core.countminsketch import CountMinSketch  # Phase 76
from pradyos.core.dependency_graph import CycleError  # Phase 70
from pradyos.core.event_filter import FilterRule  # Phase 58
from pradyos.core.guardrail import RiskLevel  # Phase 43
from pradyos.core.hash_ring import NodeNotFoundError  # Phase 73
from pradyos.core.pipeline_chain import PipelineChain, Step, StepError  # Phase 60
from pradyos.core.semaphore_gate import SemaphoreNotFoundError  # Phase 57
from pradyos.core.tdigest import TDigest  # Phase 79
from pradyos.core.timeout_guard import TimeoutExpiredError  # Phase 56
from pradyos.core.vectorclock import VectorClock  # Phase 75
from pradyos.sovereign.audit_ui import build_audit_html
from pradyos.web.aether_shell_web import register_aether_routes  # Plane 10 — AETHER SHELL
from pradyos.web.aho_corasick_web import register_ahocorasick_routes  # Phase 142
from pradyos.web.ams_web import register_ams_routes  # Phase 130
from pradyos.web.ascent_web import register_ascent_routes  # ASCENT — self-improvement loop
from pradyos.web.augmentedsketch_web import register_augmentedsketch_routes  # Phase 104
from pradyos.web.avl_tree_web import register_avl_routes  # Phase 155
from pradyos.web.b_tree_web import register_btree_routes  # Phase 156
from pradyos.web.bastion_web import register_bastion_routes  # Plane 7 — BASTION
from pradyos.web.bbit_minhash_web import register_bbitminhash_routes  # Phase 122
from pradyos.web.binary_fuse_web import register_binaryfuse_routes  # Phase 108
from pradyos.web.binary_lifting_web import register_binarylifting_routes  # Phase 161
from pradyos.web.binomial_heap_web import register_binomial_routes  # Phase 160
from pradyos.web.bloomier_web import register_bloomier_routes  # Phase 114
from pradyos.web.cartesian_tree_web import register_cartesiantree_routes  # Phase 145
from pradyos.web.chronicle_sage_web import register_chronicle_routes  # Agent 7 — CHRONICLE SAGE
from pradyos.web.codemap_web import register_codemap_routes  # CODEMAP — code self-knowledge
from pradyos.web.convex_hull_web import register_convexhull_routes  # Phase 167
from pradyos.web.count_sketch_web import register_count_sketch_routes  # Phase 94
from pradyos.web.counting_bloom_web import register_countingbloom_routes  # Phase 107
from pradyos.web.cu_sketch_web import register_cusketch_routes  # Phase 123
from pradyos.web.cuckoo_web import register_cuckoo_routes  # Phase 86
from pradyos.web.cuckoohash_web import register_cuckoohash_routes  # Phase 132
from pradyos.web.ddsketch_web import register_ddsketch_routes  # Phase 96
from pradyos.web.evolve_web import register_evolve_routes  # EVOLVE — self-improvement pipeline
from pradyos.web.exponential_histogram_web import register_exponential_histogram_routes  # Phase 97
from pradyos.web.fenwick2d_web import register_fenwick2d_routes  # Phase 146
from pradyos.web.fibonacci_heap_web import register_fibonacci_routes  # Phase 154
from pradyos.web.fmsketch_web import register_fmsketch_routes  # Phase 129
from pradyos.web.fortify_web import register_fortify_routes  # FORTIFY — self-hardening audit
from pradyos.web.frugal_web import register_frugal_routes  # Phase 125
from pradyos.web.gcs_web import register_gcs_routes  # Phase 128
from pradyos.web.gk_quantile_web import register_gk_quantile_routes  # Phase 91
from pradyos.web.guild_web import register_guild_routes  # GUILD — multi-agent organization
from pradyos.web.heavy_light_web import register_hld_routes  # Phase 165
from pradyos.web.heavykeeper_web import register_heavykeeper_routes  # Phase 102
from pradyos.web.helios_forge_web import register_helios_routes  # Agent 2 — HELIOS FORGE
from pradyos.web.hyper_minhash_web import register_hyperminhash_routes  # Phase 117
from pradyos.web.iblt_web import register_iblt_routes  # Phase 121
from pradyos.web.implicit_treap_web import register_implicittreap_routes  # Phase 162
from pradyos.web.interval_tree_web import register_intervaltree_routes  # Phase 137
from pradyos.web.jump_web import register_jump_routes  # Phase 124
from pradyos.web.kd_tree_web import register_kdtree_routes  # Phase 139
from pradyos.web.kll_sketch_web import register_kll_sketch_routes  # Phase 92
from pradyos.web.lazy_segment_tree_web import register_lazyseg_routes  # Phase 163
from pradyos.web.leftist_heap_web import register_leftist_routes  # Phase 158
from pradyos.web.li_chao_tree_web import register_lichao_routes  # Phase 148
from pradyos.web.licensing_web import register_license_routes  # LICENSING — tiers + entitlements
from pradyos.web.system_web import register_system_routes  # SYSTEM — real OS telemetry + filesystem
from pradyos.web.foresight_web import register_foresight_routes  # FORESIGHT — predict/act/compare/learn
from pradyos.web.linear_counter_web import register_linearcounting_routes  # Phase 112
from pradyos.web.lossy_count_web import register_lossy_count_routes  # Phase 95
from pradyos.web.lru_web import register_lru_routes  # Phase 84
from pradyos.web.maglev_web import register_maglev_routes  # Phase 120
from pradyos.web.min_max_heap_web import register_minmaxheap_routes  # Phase 144
from pradyos.web.minhash_lsh_web import register_minhashlsh_routes  # Phase 115
from pradyos.web.minhash_web import register_minhash_routes  # Phase 88
from pradyos.web.misra_gries_web import register_misra_gries_routes  # Phase 99
from pradyos.web.moment_sketch_web import register_momentsketch_routes  # Phase 106
from pradyos.web.morris_web import register_morris_routes  # Phase 111
from pradyos.web.nexus_weave_web import register_nexus_routes  # Agent 4 — NEXUS WEAVE
from pradyos.web.night_citadel_web import register_citadel_routes  # Plane 9 — NIGHT CITADEL
from pradyos.web.pairing_heap_web import register_pairingheap_routes  # Phase 150
from pradyos.web.persistent_segment_tree_web import register_perseg_routes  # Phase 149
from pradyos.web.polygon_web import register_polygon_routes  # Phase 168
from pradyos.web.pr_quadtree_web import register_pr_quadtree_routes  # Phase 153
from pradyos.web.priority_sampling_web import register_prioritysample_routes  # Phase 131
from pradyos.web.prism_web import register_prism_routes  # PRISM — creative artifact production
from pradyos.web.qdigest_web import register_qdigest_routes  # Phase 105
from pradyos.web.quasar_web import register_quasar_routes  # Plane 8 — QUASAR GATE
from pradyos.web.quotient_web import register_quotient_routes  # Phase 90
from pradyos.web.radix_tree_web import register_radixtree_routes  # Phase 140
from pradyos.web.random_projection_web import register_randomprojection_routes  # Phase 127
from pradyos.web.range_tree_web import register_rangetree_routes  # Phase 157
from pradyos.web.rank_select_web import register_rankselect_routes  # Phase 134
from pradyos.web.rendezvous_web import register_rendezvous_routes  # Phase 119
from pradyos.web.research_web import register_research_routes  # RESEARCH — intelligence gathering
from pradyos.web.reservoir_web import register_reservoir_routes  # Phase 85
from pradyos.web.review_web import register_review_routes  # REVIEW GATE — safe self-modification
from pradyos.web.ribbon_web import register_ribbon_routes  # Phase 101
from pradyos.web.scalable_bloom_web import register_scalablebloom_routes  # Phase 118
from pradyos.web.scapegoat_tree_web import register_scapegoat_routes  # Phase 159
from pradyos.web.sentinel_watch_web import register_sentinel_routes  # Agent 5 — SENTINEL WATCH
from pradyos.web.simhash_lsh_web import register_simhashlsh_routes  # Phase 126
from pradyos.web.simhash_web import register_simhash_routes  # Phase 89
from pradyos.web.skew_heap_web import register_skewheap_routes  # Phase 136
from pradyos.web.skills_web import register_skills_routes  # SKILL LIBRARY — learn from experience
from pradyos.web.sparse_segment_tree_web import register_sparseseg_routes  # Phase 166
from pradyos.web.sparse_table_web import register_sparsetable_routes  # Phase 138
from pradyos.web.specter_web import register_specter_routes  # SPECTER — web-action executor
from pradyos.web.spectralbloom_web import register_spectralbloom_routes  # Phase 103
from pradyos.web.splay_tree_web import register_splaytree_routes  # Phase 133
from pradyos.web.sqrt_decomposition_web import register_sqrtdecomp_routes  # Phase 147
from pradyos.web.stable_bloom_web import register_stablebloom_routes  # Phase 110
from pradyos.web.starmap_web import register_starmap_routes  # Plane 6 — STARMAP
from pradyos.web.suffix_array_web import register_suffixarray_routes  # Phase 141
from pradyos.web.suffix_automaton_web import register_suffixautomaton_routes  # Phase 151
from pradyos.web.synaptic_mind_web import register_synaptic_routes  # Agent 6 — SYNAPTIC MIND
from pradyos.web.ternary_search_tree_web import register_tst_routes  # Phase 164
from pradyos.web.theta_sketch_web import register_theta_sketch_routes  # Phase 93
from pradyos.web.tiny_lfu_web import register_tinylfu_routes  # Phase 116
from pradyos.web.topk_web import register_topk_routes  # Phase 87
from pradyos.web.treap_web import register_treap_routes  # Phase 113
from pradyos.web.trie_web import register_trie_routes  # Phase 83
from pradyos.web.vacuum_web import register_vacuum_routes  # Phase 109
from pradyos.web.van_emde_boas_web import register_veb_routes  # Phase 152
from pradyos.web.wavelet_tree_web import register_wavelet_routes  # Phase 135
from pradyos.web.weighted_reservoir_web import register_weighted_reservoir_routes  # Phase 98
from pradyos.web.xor_filter_web import register_xor_filter_routes  # Phase 100
from pradyos.web.xor_trie_web import register_xortrie_routes  # Phase 143

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
    throttle_map: Any | None = None,
    pipeline_registry: Any | None = None,
    tag_index: Any | None = None,
    router_registry: Any | None = None,
    aggregate_registry: Any | None = None,
    command_bus: Any | None = None,
    query_bus: Any | None = None,
    saga_orchestrator: Any | None = None,
    process_manager: Any | None = None,
    job_scheduler: Any | None = None,
    anomaly_detector: Any | None = None,
    dependency_graph: Any | None = None,
    anomaly_watch: Any | None = None,
    bloom_filter: Any | None = None,
    hash_ring: Any | None = None,
    hyperloglog: Any | None = None,
    vectorclock: Any | None = None,
    countminsketch: Any | None = None,
    merkle_tree: Any | None = None,
    skiplist: Any | None = None,
    tdigest: Any | None = None,
    fenwick: Any | None = None,
    segtree: Any | None = None,
    unionfind: Any | None = None,
    trie: Any | None = None,
    lru_cache: Any | None = None,
    reservoir: Any | None = None,
    cuckoo: Any | None = None,
    space_saving: Any | None = None,
    minhash: Any | None = None,
    simhash: Any | None = None,
    quotient: Any | None = None,
    gk_quantile: Any | None = None,
    kll: Any | None = None,
    theta: Any | None = None,
    count_sketch: Any | None = None,
    lossy: Any | None = None,
    ddsketch: Any | None = None,
    exp_histogram: Any | None = None,
    weighted_reservoir: Any | None = None,
    misra_gries: Any | None = None,
    xor_filter: Any | None = None,
    ribbon_filter: Any | None = None,
    heavykeeper: Any | None = None,
    spectral_bloom: Any | None = None,
    augmented_sketch: Any | None = None,
    qdigest: Any | None = None,
    moment_sketch: Any | None = None,
    counting_bloom: Any | None = None,
    binary_fuse: Any | None = None,
    vacuum_filter: Any | None = None,
    stable_bloom: Any | None = None,
    morris_counter: Any | None = None,
    linear_counter: Any | None = None,
    treap: Any | None = None,
    bloomier: Any | None = None,
    minhash_lsh: Any | None = None,
    tiny_lfu: Any | None = None,
    hyper_minhash: Any | None = None,
    scalable_bloom: Any | None = None,
    rendezvous: Any | None = None,
    maglev: Any | None = None,
    iblt: Any | None = None,
    bbit_minhash: Any | None = None,
    cu_sketch: Any | None = None,
    jump_hash: Any | None = None,
    frugal: Any | None = None,
    simhash_lsh: Any | None = None,
    random_projection: Any | None = None,
    gcs: Any | None = None,
    fm_sketch: Any | None = None,
    ams: Any | None = None,
    priority_sample: Any | None = None,
    cuckoo_hashtable: Any | None = None,
    splay_tree: Any | None = None,
    rank_select: Any | None = None,
    wavelet_tree: Any | None = None,
    skew_heap: Any | None = None,
    interval_tree: Any | None = None,
    sparse_table: Any | None = None,
    kd_tree: Any | None = None,
    radix_tree: Any | None = None,
    suffix_array: Any | None = None,
    aho_corasick: Any | None = None,
    xor_trie: Any | None = None,
    min_max_heap: Any | None = None,
    cartesian_tree: Any | None = None,
    fenwick2d: Any | None = None,
    sqrt_decomposition: Any | None = None,
    li_chao_tree: Any | None = None,
    persistent_segment_tree: Any | None = None,
    pairing_heap: Any | None = None,
    suffix_automaton: Any | None = None,
    van_emde_boas: Any | None = None,
    pr_quadtree: Any | None = None,
    fibonacci_heap: Any | None = None,
    avl_tree: Any | None = None,
    b_tree: Any | None = None,
    range_tree: Any | None = None,
    leftist_heap: Any | None = None,
    scapegoat_tree: Any | None = None,
    binomial_heap: Any | None = None,
    binary_lifting: Any | None = None,
    implicit_treap: Any | None = None,
    lazy_segment_tree: Any | None = None,
    ternary_search_tree: Any | None = None,
    heavy_light: Any | None = None,
    sparse_segment_tree: Any | None = None,
    convex_hull: Any | None = None,
    polygon: Any | None = None,
    quasar: Any | None = None,
    starmap: Any | None = None,
    bastion: Any | None = None,
    helios: Any | None = None,
    citadel: Any | None = None,
    sentinel: Any | None = None,
    synaptic: Any | None = None,
    nexus: Any | None = None,
    chronicle: Any | None = None,
    specter: Any | None = None,
    prism: Any | None = None,
    aether: Any | None = None,
    research: Any | None = None,
    skills: Any | None = None,
    codemap: Any | None = None,
    review: Any | None = None,
    fortify: Any | None = None,
    evolve: Any | None = None,
    ascent: Any | None = None,
    guild: Any | None = None,
    licensing: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def _lifespan(app):
        if heartbeat is not None:
            await heartbeat.start()
        # ASCENT autonomous driver — started only if main() attached one, so the
        # default create_app() used by tests stays deterministic/offline.
        ascent_driver = getattr(app.state, "ascent_driver", None)
        if ascent_driver is not None:
            ascent_driver.start()
        yield
        if ascent_driver is not None:
            await ascent_driver.stop()
        if heartbeat is not None:
            await heartbeat.stop()

    app = FastAPI(
        title="PRADY OS -- Sovereign Dashboard", version="5.0", docs_url="/docs", lifespan=_lifespan
    )

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
        return JSONResponse(
            {
                "ok": True,
                "timestamp": time.time(),
                "checkpoint": checkpoint_summary,
                "warden": {"status": "operational"},
                "active_campaigns": active_campaigns,
            }
        )

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
            return JSONResponse(
                {
                    "success_rate": 0.0,
                    "avg_duration_s": 0.0,
                    "node_failure_histogram": {},
                    "busiest_hours": [],
                }
            )

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
            from pradyos.core.audit import get_audit_log
            from pradyos.core.metrics import get_registry
            from pradyos.oracle.advisor import SovereignAdvisor

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
        _zero = {
            "bus_events": [],
            "quarantine": [],
            "system_health": {
                "status": "ok",
                "active_tasks": 0,
                "dead_letter_count": 0,
                "last_event_ts": None,
            },
        }
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
                {
                    "job_id": None,
                    "cron_expr": None,
                    "campaign_spec": {},
                    "priority": 5,
                    "sla_seconds": None,
                    "next_run": 0.0,
                    "enabled": True,
                },
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
        capped = nodes[: max(1, limit)]
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
        return JSONResponse(
            {"ok": True, "task_id": task_id, "decision": "approved", "ts": record["ts"]}
        )

    @app.post("/api/reject/{task_id}")
    async def api_reject(task_id: str) -> JSONResponse:
        record = _write_decision(task_id, "rejected")
        log.info("Sovereign REJECTED task %s", task_id)
        if bus is not None:
            bus.publish("sovereign.rejected", {"task_id": task_id})
        return JSONResponse(
            {"ok": True, "task_id": task_id, "decision": "rejected", "ts": record["ts"]}
        )

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
    async def api_v1_metrics() -> JSONResponse:
        if metrics is None:
            return JSONResponse({})
        return JSONResponse(metrics.get_all())

    @app.get("/api/v1/ratelimit/status")
    async def api_ratelimit_status() -> JSONResponse:
        if rate_limiter is None:
            return JSONResponse(
                {
                    "active_clients": 0,
                    "total_hits": 0,
                    "rules": {},
                    "default_limit": 0,
                    "default_window": 0,
                }
            )
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
            return JSONResponse(
                {
                    "allowed": True,
                    "client_id": client_id,
                    "endpoint": endpoint,
                    "limit": 0,
                    "window_secs": 0,
                    "current": 0,
                    "retry_after": None,
                }
            )
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
            return JSONResponse({"at": ts, "entries": [], "state": {}, "event_count": 0})
        return JSONResponse(replay_engine.replay(ts).to_dict())

    @app.get("/api/v1/plugins")
    async def api_plugins_list() -> JSONResponse:
        if plugin_sandbox is None:
            return JSONResponse({"plugins": [], "status": {}})
        return JSONResponse(
            {
                "plugins": [p.to_dict() for p in plugin_sandbox.get_plugins()],
                "status": plugin_sandbox.status(),
            }
        )

    @app.post("/api/v1/plugins/reload")
    async def api_plugins_reload() -> JSONResponse:
        if plugin_sandbox is None:
            return JSONResponse({"reloaded": 0, "plugins": []})
        result = plugin_sandbox.reload_all()
        return JSONResponse(
            {
                "reloaded": len(result),
                "plugins": [p.to_dict() for p in result.values()],
            }
        )

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
            return JSONResponse({"total_events": 0, "buffer_size": 0, "max_size": 0, "topics": {}})
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
            limit=limit,
            offset=offset,
            agent_id=agent_id,
            decision_type=decision_type,
        )
        total = decision_journal.count()
        return JSONResponse(
            {
                "entries": [e.to_dict() for e in entries],
                "count": len(entries),
                "total": total,
            }
        )

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
        return JSONResponse(
            {
                "capabilities": [c.to_dict() for c in capability_registry.list_all()],
                "summary": capability_registry.summary(),
            }
        )

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
        return JSONResponse(
            {
                "watchpoints": [w.to_dict() for w in watchpoint_system.get_watchpoints()],
                "status": watchpoint_system.status(),
            }
        )

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
        return JSONResponse(
            {
                "name": name,
                "points": [pt.to_dict() for pt in points],
                "count": len(points),
                "stats": signal_aggregator.stats(name),
            }
        )

    @app.get("/api/v1/snapshots/{namespace}")
    async def api_snapshots_list(namespace: str) -> JSONResponse:
        if snapshot_store is None:
            return JSONResponse({"namespace": namespace, "keys": []})
        return JSONResponse(
            {
                "namespace": namespace,
                "keys": snapshot_store.list_keys(namespace),
            }
        )

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
        return JSONResponse(
            {
                "reactions": [r.to_dict() for r in reactor_engine.get_log(limit)],
            }
        )

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
        return JSONResponse(
            {
                "module": module,
                "keys": state_manager._store.list_keys(module),
            }
        )

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
            return JSONResponse(
                {
                    "store_connected": False,
                    "registered_modules": [],
                    "hook_count": 0,
                }
            )
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
        return JSONResponse(
            {
                "events": [e.to_dict() for e in healing_monitor.get_log(limit)],
            }
        )

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
        return JSONResponse(
            {
                "entries": [e.to_dict() for e in memory_store.search(tag)],
            }
        )

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
            return JSONResponse(
                {
                    "os_version": OS_VERSION,
                    "uptime_seconds": 0,
                    "modules": {},
                }
            )
        return JSONResponse(control_plane.status())

    @app.post("/api/v1/os/tick")
    async def api_os_tick() -> JSONResponse:
        if control_plane is None:
            return JSONResponse({"ticks": [], "healed": [], "reactions": []})
        return JSONResponse(control_plane.tick())

    @app.get("/api/v1/heartbeat/status")
    async def api_heartbeat_status() -> JSONResponse:
        if heartbeat is None:
            return JSONResponse(
                {
                    "running": False,
                    "tick_count": 0,
                    "interval_seconds": 0,
                }
            )
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
            return JSONResponse(
                {
                    "allowlist": [],
                    "total_runs": 0,
                    "last_status": None,
                }
            )
        return JSONResponse(execution_engine.status())

    @app.get("/api/v1/execute/history")
    async def api_execute_history(request: Request) -> JSONResponse:
        if execution_engine is None:
            return JSONResponse({"results": []})
        try:
            limit = int(request.query_params.get("limit", 50))
        except (ValueError, TypeError):
            limit = 50
        return JSONResponse(
            {
                "results": [r.to_dict() for r in execution_engine.history(limit)],
            }
        )

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
            return JSONResponse(
                {
                    "cache_enabled": False,
                    "guardrail_enabled": False,
                    "max_age": 3600,
                    "timeout": 10,
                }
            )
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
        return JSONResponse(
            {
                "nodes": [n.to_dict() for n in memory_graph._nodes.values()],
                "count": memory_graph.node_count(),
            }
        )

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
        return JSONResponse(
            {
                "name": name,
                "neighbors": [n.to_dict() for n in neighbors],
            }
        )

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
        return JSONResponse(
            {
                "stream": stream,
                "events": [e.to_dict() for e in events],
                "count": len(events),
            }
        )

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
        return JSONResponse(
            {
                "tasks": [t.to_dict() for t in tasks],
                "count": len(tasks),
            }
        )

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
        return JSONResponse(
            {
                "topic": topic,
                "subscriber_count": pubsub.count_subscribers(topic),
            }
        )

    @app.post("/api/v1/pubsub/{topic}")
    async def api_pubsub_publish(topic: str, request: Request) -> JSONResponse:
        if pubsub is None:
            return JSONResponse({"error": "no pubsub configured"}, status_code=400)
        body = await request.json()
        if "message" not in body:
            return JSONResponse({"error": "missing 'message' key"}, status_code=400)
        message = (
            body["message"] if isinstance(body["message"], dict) else {"value": body["message"]}
        )
        notified = pubsub.publish(topic, message)
        return JSONResponse({"topic": topic, "notified": notified})

    @app.get("/api/v1/statesync/sessions")
    async def api_statesync_list(request: Request) -> JSONResponse:
        if statesync is None:
            return JSONResponse({"sessions": [], "count": 0})
        flag = (request.query_params.get("active_only") or "").lower()
        active_only = flag in ("true", "1", "yes")
        sessions = statesync.list_sessions(active_only=active_only)
        return JSONResponse(
            {
                "sessions": [s.to_dict() for s in sessions],
                "count": len(sessions),
            }
        )

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
        return JSONResponse(
            {
                "breakers": circuit_breaker.list_breakers(),
                "count": circuit_breaker.count(),
            }
        )

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
        return JSONResponse(
            {
                "names": retry_policy.list_names(),
                "count": retry_policy.count(),
            }
        )

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
        return JSONResponse(
            {
                "name": name,
                "result": result,
                "attempts": attempts,
                "error": error,
            }
        )

    @app.get("/api/v1/retry/{name}/history")
    async def api_retry_history(name: str) -> JSONResponse:
        if retry_policy is None:
            return JSONResponse({"name": name, "history": []})
        return JSONResponse(
            {
                "name": name,
                "history": retry_policy.get_history(name),
            }
        )

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
        return JSONResponse(
            {
                "name": name,
                "submitted": True,
                "stats": pool.get_stats().to_dict(),
            }
        )

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
        return JSONResponse(
            {
                "names": timeout_guard.list_names(),
                "total": timeout_guard.count(),
            }
        )

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
            result = timeout_guard.execute(name, _no_op, timeout=timeout_v)  # noqa: F841
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
        return JSONResponse(
            {
                "name": name,
                "outcome": "success",
                "elapsed": last_record["elapsed"] if last_record else 0.0,
                "record": last_record,
            }
        )

    @app.get("/api/v1/timeouts/{name}/history")
    async def api_timeouts_history(name: str) -> JSONResponse:
        if timeout_guard is None:
            return JSONResponse({"name": name, "records": []})
        records = timeout_guard.get_history(name)
        return JSONResponse(
            {
                "name": name,
                "records": [r.to_dict() for r in records],
            }
        )

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
        return JSONResponse(
            {
                "name": name,
                "acquired": bool(ok),
                "stats": stats.to_dict(),
            }
        )

    @app.post("/api/v1/semaphores/{name}/release")
    async def api_semaphores_release(name: str) -> JSONResponse:
        if semaphore_gate is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            semaphore_gate.release(name)
            stats = semaphore_gate.get_stats(name)
        except SemaphoreNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(
            {
                "name": name,
                "released": True,
                "stats": stats.to_dict(),
            }
        )

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
            rules.append(
                FilterRule(
                    field=str(r.get("field", "")),
                    op=str(r.get("op", "")),
                    value=r.get("value"),
                )
            )
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
        return JSONResponse(
            {
                "name": name,
                "matched": len(matched),
                "events": matched,
            }
        )

    @app.delete("/api/v1/filters/{name}")
    async def api_filters_delete(name: str) -> JSONResponse:
        if event_filter_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = event_filter_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/throttle")
    async def api_throttle_list() -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"keys": [], "count": 0})
        keys = throttle_map.list_keys()
        return JSONResponse({"keys": keys, "count": len(keys)})

    @app.post("/api/v1/throttle/check")
    async def api_throttle_check(request: Request) -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"error": "no throttle map configured"})
        body = await request.json()
        for k in ("key", "limit", "window"):
            if k not in body:
                return JSONResponse(
                    {"error": f"missing required key: {k}"},
                    status_code=400,
                )
        key = str(body["key"])
        try:
            limit = int(body["limit"])
            window = float(body["window"])
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "limit must be int and window must be float"},
                status_code=400,
            )
        allowed = throttle_map.allow(key, limit, window)
        return JSONResponse({"key": key, "allowed": bool(allowed)})

    @app.get("/api/v1/throttle/{key}")
    async def api_throttle_stats(key: str, request: Request) -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        limit_q = request.query_params.get("limit")
        window_q = request.query_params.get("window")
        if limit_q is None or window_q is None:
            return JSONResponse(
                {"error": "limit and window query params required"},
                status_code=400,
            )
        try:
            limit = int(limit_q)
            window = float(window_q)
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "limit must be int and window must be float"},
                status_code=400,
            )
        stats = throttle_map.stats(key, limit, window)
        if stats is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(stats)

    @app.delete("/api/v1/throttle/{key}")
    async def api_throttle_delete(key: str) -> JSONResponse:
        if throttle_map is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = throttle_map.delete(key)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/pipelines")
    async def api_pipelines_list() -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"pipelines": [], "count": 0})
        names = pipeline_registry.list_chains()
        return JSONResponse({"pipelines": names, "count": len(names)})

    @app.post("/api/v1/pipelines")
    async def api_pipelines_create(request: Request) -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"error": "no pipeline registry configured"})
        body = await request.json()
        if "name" not in body or "steps" not in body:
            return JSONResponse(
                {"error": "missing required keys: name, steps"},
                status_code=400,
            )
        name = str(body["name"])
        steps_raw = body["steps"]
        if not isinstance(steps_raw, list):
            return JSONResponse({"error": "steps must be a list"}, status_code=400)
        steps = []
        for s in steps_raw:
            if not isinstance(s, dict):
                continue
            steps.append(
                Step(
                    name=str(s.get("name", "")),
                    transform_type=str(s.get("transform_type", "")),
                    params=dict(s.get("params") or {}),
                )
            )
        chain = PipelineChain(name=name, steps=steps)
        pipeline_registry.register(chain)
        return JSONResponse(
            {
                "registered": True,
                "name": name,
                "step_count": len(steps),
            }
        )

    @app.post("/api/v1/pipelines/{name}/run")
    async def api_pipelines_run(name: str, request: Request) -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        if "event" not in body:
            return JSONResponse(
                {"error": "missing required key: event"},
                status_code=400,
            )
        event = body["event"] if isinstance(body["event"], dict) else {}
        try:
            result = pipeline_registry.run(name, event)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        except StepError as exc:
            return JSONResponse(
                {"error": exc.message, "step": exc.step_name},
                status_code=422,
            )
        return JSONResponse({"name": name, "result": result})

    @app.delete("/api/v1/pipelines/{name}")
    async def api_pipelines_delete(name: str) -> JSONResponse:
        if pipeline_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = pipeline_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/tags")
    async def api_tags_list() -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"tags": [], "total": 0})
        all_tags = tag_index.list_tags()
        return JSONResponse({"tags": all_tags, "total": len(all_tags)})

    @app.post("/api/v1/tags/tag")
    async def api_tags_tag(request: Request) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"error": "no tag index configured"})
        body = await request.json()
        item_id = str(body.get("item_id", ""))
        tags = body.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tag_index.tag(item_id, *[str(t) for t in tags])
        return JSONResponse({"tagged": True, "item_id": item_id, "tags": list(tags)})

    @app.post("/api/v1/tags/untag")
    async def api_tags_untag(request: Request) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"error": "no tag index configured"})
        body = await request.json()
        item_id = str(body.get("item_id", ""))
        tags = body.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tag_index.untag(item_id, *[str(t) for t in tags])
        return JSONResponse({"untagged": True, "item_id": item_id, "tags": list(tags)})

    @app.get("/api/v1/tags/items/{tag}")
    async def api_tags_items_for(tag: str) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"tag": tag, "items": []})
        return JSONResponse({"tag": tag, "items": tag_index.items(tag)})

    @app.get("/api/v1/tags/search")
    async def api_tags_search(request: Request) -> JSONResponse:
        raw = request.query_params.get("tags", "")
        mode = request.query_params.get("mode", "all")
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        if tag_index is None:
            return JSONResponse({"tags": tags, "mode": mode, "results": []})
        results = tag_index.search(*tags, mode=mode)
        return JSONResponse({"tags": tags, "mode": mode, "results": results})

    @app.delete("/api/v1/tags/items/{item_id}")
    async def api_tags_delete_item(item_id: str) -> JSONResponse:
        if tag_index is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = tag_index.delete_item(item_id)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/routers")
    async def api_routers_list() -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"routers": [], "total": 0})
        names = router_registry.list_names()
        return JSONResponse({"routers": names, "total": len(names)})

    @app.post("/api/v1/routers")
    async def api_routers_create(request: Request) -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"error": "no router registry configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing required key: name"}, status_code=400)
        name = str(body["name"])
        default_dest = body.get("default_destination")
        routes_raw = body.get("routes") or []
        try:
            router = router_registry.create(
                name=name,
                default_destination=default_dest,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        added = 0
        for r in routes_raw:
            if not isinstance(r, dict):
                continue
            try:
                router.add_route(
                    name=str(r.get("name", "")),
                    predicates=r.get("predicates") or [],
                    destination=str(r.get("destination", "")),
                )
                added += 1
            except ValueError:
                # duplicate route name in same payload — skip
                continue
        return JSONResponse(
            {
                "created": True,
                "name": name,
                "route_count": added,
                "default_destination": default_dest,
            }
        )

    @app.post("/api/v1/routers/{name}/route")
    async def api_routers_route(name: str, request: Request) -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        router = router_registry.get(name)
        if router is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        destinations = router.route(event)
        return JSONResponse(
            {
                "name": name,
                "destinations": destinations,
                "matched": len(destinations),
            }
        )

    @app.delete("/api/v1/routers/{name}")
    async def api_routers_delete(name: str) -> JSONResponse:
        if router_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = router_registry.delete(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    @app.get("/api/v1/aggregates")
    async def api_aggregates_list() -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"aggregates": []})
        return JSONResponse({"aggregates": aggregate_registry.list_aggregates()})

    @app.post("/api/v1/aggregates/{aggregate_id}/events")
    async def api_aggregates_apply(aggregate_id: str, request: Request) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "no aggregate registry configured"})
        body = await request.json()
        if "event_type" not in body:
            return JSONResponse({"error": "missing required key: event_type"}, status_code=400)
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        agg = aggregate_registry.get_or_create(aggregate_id)
        event = agg.apply(str(body["event_type"]), payload)
        return JSONResponse(event.to_dict())

    @app.get("/api/v1/aggregates/{aggregate_id}/state")
    async def api_aggregates_state(aggregate_id: str) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        agg = aggregate_registry.get(aggregate_id)
        if agg is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(
            {
                "aggregate_id": agg.aggregate_id,
                "version": agg.version,
                "state": agg.get_state(),
            }
        )

    @app.get("/api/v1/aggregates/{aggregate_id}/events")
    async def api_aggregates_events(aggregate_id: str, request: Request) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        agg = aggregate_registry.get(aggregate_id)
        if agg is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            since = int(request.query_params.get("since_version", 0))
        except (TypeError, ValueError):
            since = 0
        events = agg.get_events(since_version=since)
        return JSONResponse(
            {
                "aggregate_id": agg.aggregate_id,
                "events": [e.to_dict() for e in events],
            }
        )

    @app.delete("/api/v1/aggregates/{aggregate_id}")
    async def api_aggregates_delete(aggregate_id: str) -> JSONResponse:
        if aggregate_registry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = aggregate_registry.delete(aggregate_id)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": True})

    # ── Phase 64: Command Bus ────────────────────────────────────────────────

    @app.get("/api/v1/commands/handlers")
    async def api_commands_handlers() -> JSONResponse:
        if command_bus is None:
            return JSONResponse({"handlers": []})
        return JSONResponse({"handlers": command_bus.list_handlers()})

    @app.post("/api/v1/commands/dispatch")
    async def api_commands_dispatch(request: Request) -> JSONResponse:
        if command_bus is None:
            return JSONResponse({"error": "no command bus configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse(
                {"error": "missing required key: name"},
                status_code=400,
            )
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        result = command_bus.dispatch(str(body["name"]), payload)
        return JSONResponse(result.to_dict())

    @app.get("/api/v1/commands/history")
    async def api_commands_history(request: Request) -> JSONResponse:
        if command_bus is None:
            return JSONResponse({"history": []})
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(0, min(200, limit))
        results = command_bus.history(limit=limit)
        return JSONResponse({"history": [r.to_dict() for r in results]})

    @app.delete("/api/v1/commands/handlers/{name}")
    async def api_commands_unregister(name: str) -> JSONResponse:
        if command_bus is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = command_bus.unregister(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"unregistered": True})

    # ── Phase 65: Query Bus ──────────────────────────────────────────────────

    @app.get("/api/v1/queries/handlers")
    async def api_queries_handlers() -> JSONResponse:
        if query_bus is None:
            return JSONResponse({"handlers": []})
        return JSONResponse({"handlers": query_bus.list_handlers()})

    @app.post("/api/v1/queries/execute")
    async def api_queries_execute(request: Request) -> JSONResponse:
        if query_bus is None:
            return JSONResponse({"error": "no query bus configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse(
                {"error": "missing required key: name"},
                status_code=400,
            )
        params = body.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        result = query_bus.query(str(body["name"]), params)
        return JSONResponse(result.to_dict())

    @app.get("/api/v1/queries/history")
    async def api_queries_history(request: Request) -> JSONResponse:
        if query_bus is None:
            return JSONResponse({"history": []})
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(0, min(200, limit))
        results = query_bus.history(limit=limit)
        return JSONResponse({"history": [r.to_dict() for r in results]})

    @app.delete("/api/v1/queries/handlers/{name}")
    async def api_queries_unregister(name: str) -> JSONResponse:
        if query_bus is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = query_bus.unregister(name)
        if not ok:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"unregistered": True})

    # ── Phase 66: Saga Orchestrator ──────────────────────────────────────────

    @app.post("/api/v1/sagas/run")
    async def api_sagas_run(request: Request) -> JSONResponse:
        if saga_orchestrator is None:
            return JSONResponse({"error": "no saga orchestrator configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse(
                {"error": "missing required key: name"},
                status_code=400,
            )
        if "steps" not in body or not isinstance(body["steps"], list):
            return JSONResponse(
                {"error": "missing or invalid 'steps' (must be a list)"},
                status_code=400,
            )
        steps = [str(s) for s in body["steps"]]
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        saga_run = saga_orchestrator.run(
            saga_name=str(body["name"]),
            steps=steps,
            initial_payload=payload,
        )
        return JSONResponse(saga_run.to_dict())

    @app.get("/api/v1/sagas")
    async def api_sagas_list(request: Request) -> JSONResponse:
        if saga_orchestrator is None:
            return JSONResponse({"runs": []})
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(0, min(200, limit))
        runs = saga_orchestrator.list_runs(limit=limit)
        return JSONResponse({"runs": [r.to_dict() for r in runs]})

    @app.get("/api/v1/sagas/{saga_id}")
    async def api_sagas_get(saga_id: str) -> JSONResponse:
        if saga_orchestrator is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        run = saga_orchestrator.get(saga_id)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(run.to_dict())

    # ── Phase 67: Process Manager ────────────────────────────────────────────

    @app.post("/api/v1/processes")
    async def api_processes_create(request: Request) -> JSONResponse:
        if process_manager is None:
            return JSONResponse({"error": "no process manager configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse(
                {"error": "missing required key: name"},
                status_code=400,
            )
        if "state" not in body:
            return JSONResponse(
                {"error": "missing required key: state"},
                status_code=400,
            )
        context = body.get("context") or {}
        if not isinstance(context, dict):
            context = {}
        inst = process_manager.create(
            name=str(body["name"]),
            initial_state=str(body["state"]),
            context=context,
        )
        return JSONResponse(inst.to_dict())

    @app.post("/api/v1/processes/{process_id}/transition")
    async def api_processes_transition(process_id: str, request: Request) -> JSONResponse:
        if process_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        if "trigger" not in body:
            return JSONResponse(
                {"error": "missing required key: trigger"},
                status_code=400,
            )
        if "state" not in body:
            return JSONResponse(
                {"error": "missing required key: state"},
                status_code=400,
            )
        patch = body.get("context_patch") or {}
        if not isinstance(patch, dict):
            patch = {}
        inst = process_manager.transition(
            process_id=process_id,
            trigger=str(body["trigger"]),
            new_state=str(body["state"]),
            context_patch=patch,
        )
        if inst is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(inst.to_dict())

    @app.get("/api/v1/processes/{process_id}")
    async def api_processes_get(process_id: str) -> JSONResponse:
        if process_manager is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        inst = process_manager.get(process_id)
        if inst is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(inst.to_dict())

    @app.get("/api/v1/processes")
    async def api_processes_list(request: Request) -> JSONResponse:
        if process_manager is None:
            return JSONResponse({"processes": []})
        state = request.query_params.get("state")
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(0, min(500, limit))
        instances = process_manager.list_processes(state=state, limit=limit)
        return JSONResponse({"processes": [i.to_dict() for i in instances]})

    # ── Phase 68: Sovereign Scheduler ────────────────────────────────────────
    # Distinct from Phase 15 (/api/v1/scheduler/jobs) and Phase 38
    # (/api/v1/scheduler/tasks + /tick). This is the time-based job queue
    # with one-shot and repeating interval semantics.

    @app.post("/api/v1/jobs")
    async def api_jobs_schedule(request: Request) -> JSONResponse:
        if job_scheduler is None:
            return JSONResponse({"error": "no scheduler configured"})
        body = await request.json()
        if "name" not in body:
            return JSONResponse(
                {"error": "missing required key: name"},
                status_code=400,
            )
        if "run_at" not in body:
            return JSONResponse(
                {"error": "missing required key: run_at"},
                status_code=400,
            )
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        interval = body.get("interval_seconds")
        if interval is not None:
            try:
                interval = float(interval)
            except (TypeError, ValueError):
                interval = None
        try:
            run_at = float(body["run_at"])
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "run_at must be numeric"},
                status_code=400,
            )
        job = job_scheduler.schedule(
            name=str(body["name"]),
            run_at=run_at,
            payload=payload,
            interval_seconds=interval,
        )
        return JSONResponse(job.to_dict())

    @app.post("/api/v1/jobs/tick")
    async def api_jobs_tick(request: Request) -> JSONResponse:
        if job_scheduler is None:
            return JSONResponse({"executed": []})
        try:
            body = await request.json()
        except Exception:
            body = {}
        now_v = body.get("now") if isinstance(body, dict) else None
        if now_v is not None:
            try:
                now_v = float(now_v)
            except (TypeError, ValueError):
                now_v = None
        executed = job_scheduler.tick(now=now_v)
        return JSONResponse({"executed": [j.to_dict() for j in executed]})

    @app.get("/api/v1/jobs")
    async def api_jobs_list(request: Request) -> JSONResponse:
        if job_scheduler is None:
            return JSONResponse({"jobs": []})
        status = request.query_params.get("status")
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(0, min(1000, limit))
        jobs = job_scheduler.list_jobs(status=status, limit=limit)
        return JSONResponse({"jobs": [j.to_dict() for j in jobs]})

    @app.get("/api/v1/jobs/{job_id}")
    async def api_jobs_get(job_id: str) -> JSONResponse:
        if job_scheduler is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        job = job_scheduler.get(job_id)
        if job is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(job.to_dict())

    @app.delete("/api/v1/jobs/{job_id}")
    async def api_jobs_cancel(job_id: str) -> JSONResponse:
        if job_scheduler is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        ok = job_scheduler.cancel(job_id)
        if not ok:
            return JSONResponse(
                {"error": "not found or not pending"},
                status_code=404,
            )
        return JSONResponse({"cancelled": True})

    @app.get("/api/v1/anomaly")
    async def api_anomaly_get(request: Request) -> JSONResponse:
        if anomaly_detector is None:
            return JSONResponse({"error": "no anomaly detector configured"})
        signal = request.query_params.get("signal")
        if not signal:
            return JSONResponse({"error": "signal is required"})
        try:
            window = float(request.query_params.get("window", 3600))
        except (ValueError, TypeError):
            window = 3600.0
        use_cache = request.query_params.get("use_cache", "").lower() in ("1", "true", "yes")
        if use_cache:
            cached = anomaly_detector.get_cached(signal, window)
            if cached is not None:
                d = cached.to_dict()
                d["cached"] = True
                return JSONResponse(d)
        result = anomaly_detector.detect(signal, window=window)
        if use_cache:
            anomaly_detector.cache_result(result)
        d = result.to_dict()
        d["cached"] = False
        return JSONResponse(d)

    @app.post("/api/v1/anomaly")
    async def api_anomaly_post(request: Request) -> JSONResponse:
        if anomaly_detector is None:
            return JSONResponse({"error": "no anomaly detector configured"})
        body = await request.json()
        signal = body.get("signal")
        if not signal:
            return JSONResponse({"error": "signal is required"})
        try:
            window = float(body.get("window", 3600))
        except (ValueError, TypeError):
            window = 3600.0
        use_cache = bool(body.get("use_cache", False))
        if use_cache:
            cached = anomaly_detector.get_cached(signal, window)
            if cached is not None:
                d = cached.to_dict()
                d["cached"] = True
                return JSONResponse(d)
        result = anomaly_detector.detect(signal, window=window)
        if use_cache:
            anomaly_detector.cache_result(result)
        d = result.to_dict()
        d["cached"] = False
        return JSONResponse(d)

    @app.get("/api/v1/deps/{node}")
    async def api_deps_get(node: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        return JSONResponse(dependency_graph.describe(node))

    @app.post("/api/v1/deps")
    async def api_deps_post(request: Request) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        body = await request.json()
        frm = body.get("from")
        to = body.get("to")
        if not frm or not to:
            return JSONResponse({"error": "both 'from' and 'to' are required"}, status_code=422)
        dependency_graph.add_dependency(frm, to)
        return JSONResponse({"from": frm, "to": to, "added": True})

    @app.delete("/api/v1/deps/{frm}/{to}")
    async def api_deps_delete(frm: str, to: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        removed = dependency_graph.remove_dependency(frm, to)
        return JSONResponse({"from": frm, "to": to, "removed": removed})

    @app.get("/api/v1/deps/{node}/sort")
    async def api_deps_sort(node: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        try:
            order = dependency_graph.topological_sort(node)
        except CycleError as exc:
            return JSONResponse({"error": "cycle detected", "cycle": exc.cycle}, status_code=409)
        return JSONResponse({"node": node, "order": order})

    @app.get("/api/v1/deps/{node}/impact")
    async def api_deps_impact(node: str) -> JSONResponse:
        if dependency_graph is None:
            return JSONResponse({"error": "no dependency graph configured"})
        return JSONResponse({"node": node, "impact_score": dependency_graph.impact_score(node)})

    @app.get("/api/v1/anomaly/sources")
    async def api_anomaly_sources_list() -> JSONResponse:
        if anomaly_watch is None:
            return JSONResponse({"error": "no anomaly watch configured"})
        return JSONResponse({"sources": anomaly_watch.sources()})

    @app.post("/api/v1/anomaly/sources")
    async def api_anomaly_sources_register(request: Request) -> JSONResponse:
        if anomaly_watch is None:
            return JSONResponse({"error": "no anomaly watch configured"})
        body = await request.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=422)
        raw = body.get("baseline", [])
        try:
            baseline = [float(v) for v in raw]
        except (TypeError, ValueError):
            return JSONResponse({"error": "baseline must be a list of numbers"}, status_code=422)
        last = baseline[-1] if baseline else 0.0
        anomaly_watch.register_source(name, lambda last=last: last, baseline=baseline)
        return JSONResponse({"name": name, "registered": True, "samples": len(baseline)})

    @app.get("/api/v1/anomaly/status")
    async def api_anomaly_status() -> JSONResponse:
        if anomaly_watch is None:
            return JSONResponse({"error": "no anomaly watch configured"})
        return JSONResponse({"results": anomaly_watch.tick()})

    @app.delete("/api/v1/anomaly/sources/{name}")
    async def api_anomaly_sources_delete(name: str) -> JSONResponse:
        if anomaly_watch is None:
            return JSONResponse({"error": "no anomaly watch configured"})
        try:
            anomaly_watch.deregister(name)
        except SourceNotFoundError:
            return JSONResponse({"error": f"no such source: {name}"}, status_code=404)
        return JSONResponse({"name": name, "removed": True})

    @app.get("/api/v1/bloom")
    async def api_bloom_stats() -> JSONResponse:
        if bloom_filter is None:
            return JSONResponse({"error": "no bloom filter configured"})
        return JSONResponse(bloom_filter.stats())

    @app.post("/api/v1/bloom/add")
    async def api_bloom_add(request: Request) -> JSONResponse:
        if bloom_filter is None:
            return JSONResponse({"error": "no bloom filter configured"})
        body = await request.json()
        if "items" in body:
            items = body.get("items")
            if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                return JSONResponse({"error": "items must be a list of strings"}, status_code=422)
        elif "item" in body:
            item = body.get("item")
            if not isinstance(item, str):
                return JSONResponse({"error": "item must be a string"}, status_code=422)
            items = [item]
        else:
            return JSONResponse({"error": "item or items is required"}, status_code=422)
        added = bloom_filter.add_many(items)
        return JSONResponse({"added": added, "count": len(bloom_filter)})

    @app.get("/api/v1/bloom/contains/{item}")
    async def api_bloom_contains(item: str) -> JSONResponse:
        if bloom_filter is None:
            return JSONResponse({"error": "no bloom filter configured"})
        return JSONResponse({"item": item, "contains": bloom_filter.contains(item)})

    @app.delete("/api/v1/bloom")
    async def api_bloom_clear() -> JSONResponse:
        if bloom_filter is None:
            return JSONResponse({"error": "no bloom filter configured"})
        bloom_filter.clear()
        return JSONResponse({"cleared": True})

    @app.get("/api/v1/hashring")
    async def api_hashring_stats() -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        return JSONResponse(hash_ring.stats())

    @app.post("/api/v1/hashring/nodes")
    async def api_hashring_add(request: Request) -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        body = await request.json()
        node = body.get("node")
        if not node or not isinstance(node, str):
            return JSONResponse({"error": "node is required"}, status_code=422)
        hash_ring.add_node(node)
        return JSONResponse({"node": node, "added": True, "nodes": hash_ring.nodes()})

    @app.get("/api/v1/hashring/node/{key}")
    async def api_hashring_get(key: str) -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        return JSONResponse({"key": key, "node": hash_ring.get_node(key)})

    @app.delete("/api/v1/hashring/nodes/{node}")
    async def api_hashring_remove(node: str) -> JSONResponse:
        if hash_ring is None:
            return JSONResponse({"error": "no hash ring configured"})
        try:
            hash_ring.remove_node(node)
        except NodeNotFoundError:
            return JSONResponse({"error": f"no such node: {node}"}, status_code=404)
        return JSONResponse({"node": node, "removed": True})

    @app.get("/api/v1/cardinality")
    async def api_cardinality_stats() -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        return JSONResponse(hyperloglog.stats())

    @app.post("/api/v1/cardinality/add")
    async def api_cardinality_add(request: Request) -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        body = await request.json()
        if "items" in body:
            items = body.get("items")
            if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                return JSONResponse({"error": "items must be a list of strings"}, status_code=422)
        elif "item" in body:
            item = body.get("item")
            if not isinstance(item, str):
                return JSONResponse({"error": "item must be a string"}, status_code=422)
            items = [item]
        else:
            return JSONResponse({"error": "item or items is required"}, status_code=422)
        hyperloglog.add_many(items)
        return JSONResponse({"added": len(items), "estimate": hyperloglog.estimate()})

    @app.get("/api/v1/cardinality/estimate")
    async def api_cardinality_estimate() -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        return JSONResponse({"estimate": hyperloglog.estimate()})

    @app.delete("/api/v1/cardinality")
    async def api_cardinality_clear() -> JSONResponse:
        if hyperloglog is None:
            return JSONResponse({"error": "no cardinality estimator configured"})
        hyperloglog.clear()
        return JSONResponse({"cleared": True})

    @app.get("/api/v1/clocks")
    async def api_clocks_state() -> JSONResponse:
        if vectorclock is None:
            return JSONResponse({"error": "no vector clock configured"})
        return JSONResponse(vectorclock.stats())

    @app.post("/api/v1/clocks/tick")
    async def api_clocks_tick(request: Request) -> JSONResponse:
        if vectorclock is None:
            return JSONResponse({"error": "no vector clock configured"})
        body = await request.json()
        actor = body.get("actor")
        if not actor or not isinstance(actor, str):
            return JSONResponse({"error": "actor is required"}, status_code=422)
        value = vectorclock.tick(actor)
        return JSONResponse({"actor": actor, "value": value, "clock": vectorclock.to_dict()})

    @app.post("/api/v1/clocks/merge")
    async def api_clocks_merge(request: Request) -> JSONResponse:
        if vectorclock is None:
            return JSONResponse({"error": "no vector clock configured"})
        body = await request.json()
        incoming = body.get("clock")
        if not isinstance(incoming, dict):
            return JSONResponse({"error": "clock object is required"}, status_code=422)
        try:
            vectorclock.merge(VectorClock(incoming))
        except (ValueError, TypeError):
            return JSONResponse(
                {"error": "clock must map actors to non-negative integers"}, status_code=422
            )
        return JSONResponse({"clock": vectorclock.to_dict()})

    @app.post("/api/v1/clocks/compare")
    async def api_clocks_compare(request: Request) -> JSONResponse:
        if vectorclock is None:
            return JSONResponse({"error": "no vector clock configured"})
        body = await request.json()
        incoming = body.get("clock")
        if not isinstance(incoming, dict):
            return JSONResponse({"error": "clock object is required"}, status_code=422)
        try:
            relation = vectorclock.compare(VectorClock(incoming))
        except (ValueError, TypeError):
            return JSONResponse(
                {"error": "clock must map actors to non-negative integers"}, status_code=422
            )
        return JSONResponse({"relation": relation})

    @app.get("/api/v1/frequency")
    async def api_frequency_stats() -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        return JSONResponse(countminsketch.stats())

    @app.post("/api/v1/frequency/add")
    async def api_frequency_add(request: Request) -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        count = body.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return JSONResponse({"error": "count must be a positive integer"}, status_code=422)
        countminsketch.add(item, count)
        return JSONResponse(
            {"item": item, "count": count, "estimate": countminsketch.estimate(item)}
        )

    @app.post("/api/v1/frequency/estimate")
    async def api_frequency_estimate(request: Request) -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        return JSONResponse({"item": item, "estimate": countminsketch.estimate(item)})

    @app.post("/api/v1/frequency/merge")
    async def api_frequency_merge(request: Request) -> JSONResponse:
        if countminsketch is None:
            return JSONResponse({"error": "no frequency sketch configured"})
        body = await request.json()
        items = body.get("items")
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            return JSONResponse({"error": "items must be a list of strings"}, status_code=422)
        other = CountMinSketch(countminsketch.width, countminsketch.depth)
        for entry in items:
            other.add(entry)
        merged = countminsketch.merge(other)
        result = {"merged": True, "total": merged.stats()["total"]}
        query = body.get("item")
        if isinstance(query, str) and query:
            result["estimate"] = merged.estimate(query)
        return JSONResponse(result)

    @app.get("/api/v1/merkle")
    async def api_merkle_stats() -> JSONResponse:
        if merkle_tree is None:
            return JSONResponse({"error": "no merkle tree configured"})
        return JSONResponse(merkle_tree.stats())

    @app.post("/api/v1/merkle/add")
    async def api_merkle_add(request: Request) -> JSONResponse:
        if merkle_tree is None:
            return JSONResponse({"error": "no merkle tree configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        merkle_tree.add(item)
        return JSONResponse({"item": item, "leaves": len(merkle_tree), "root": merkle_tree.root})

    @app.post("/api/v1/merkle/verify")
    async def api_merkle_verify(request: Request) -> JSONResponse:
        if merkle_tree is None:
            return JSONResponse({"error": "no merkle tree configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        return JSONResponse({"item": item, "verified": merkle_tree.verify(item)})

    @app.post("/api/v1/merkle/proof")
    async def api_merkle_proof(request: Request) -> JSONResponse:
        if merkle_tree is None:
            return JSONResponse({"error": "no merkle tree configured"})
        body = await request.json()
        item = body.get("item")
        if not isinstance(item, str) or not item:
            return JSONResponse({"error": "item is required"}, status_code=422)
        try:
            path = merkle_tree.proof(item)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse({"item": item, "proof": path, "root": merkle_tree.root})

    @app.get("/api/v1/skiplist")
    async def api_skiplist_stats() -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        return JSONResponse(skiplist.stats())

    @app.post("/api/v1/skiplist/insert")
    async def api_skiplist_insert(request: Request) -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        body = await request.json()
        key = body.get("key")
        if not isinstance(key, str) or not key:
            return JSONResponse({"error": "key is required"}, status_code=422)
        skiplist.insert(key, body.get("value"))
        return JSONResponse({"key": key, "value": body.get("value"), "size": len(skiplist)})

    @app.post("/api/v1/skiplist/search")
    async def api_skiplist_search(request: Request) -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        body = await request.json()
        key = body.get("key")
        if not isinstance(key, str) or not key:
            return JSONResponse({"error": "key is required"}, status_code=422)
        value = skiplist.search(key)
        return JSONResponse({"key": key, "value": value, "found": key in skiplist})

    @app.post("/api/v1/skiplist/range")
    async def api_skiplist_range(request: Request) -> JSONResponse:
        if skiplist is None:
            return JSONResponse({"error": "no skip list configured"})
        body = await request.json()
        lo = body.get("lo")
        hi = body.get("hi")
        if not isinstance(lo, str) or not isinstance(hi, str):
            return JSONResponse({"error": "lo and hi are required strings"}, status_code=422)
        pairs = skiplist.range_query(lo, hi)
        return JSONResponse(
            {"lo": lo, "hi": hi, "results": [[k, v] for k, v in pairs], "count": len(pairs)}
        )

    @app.get("/api/v1/tdigest")
    async def api_tdigest_stats() -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        return JSONResponse(tdigest.stats())

    @app.post("/api/v1/tdigest/add")
    async def api_tdigest_add(request: Request) -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        body = await request.json()
        value = body.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            return JSONResponse({"error": "value must be a number"}, status_code=422)
        weight = body.get("weight", 1)
        if not isinstance(weight, int | float) or isinstance(weight, bool) or weight <= 0:
            return JSONResponse({"error": "weight must be a positive number"}, status_code=422)
        tdigest.add(value, weight)
        return JSONResponse({"value": value, "weight": weight, "count": tdigest.count})

    @app.post("/api/v1/tdigest/percentile")
    async def api_tdigest_percentile(request: Request) -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        body = await request.json()
        q = body.get("q")
        if not isinstance(q, int | float) or isinstance(q, bool) or not 0.0 <= q <= 100.0:
            return JSONResponse({"error": "q must be a number in [0, 100]"}, status_code=422)
        try:
            value = tdigest.percentile(q)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"q": q, "value": value})

    @app.post("/api/v1/tdigest/merge")
    async def api_tdigest_merge(request: Request) -> JSONResponse:
        if tdigest is None:
            return JSONResponse({"error": "no t-digest configured"})
        body = await request.json()
        values = body.get("values")
        if not isinstance(values, list) or not all(
            isinstance(x, int | float) and not isinstance(x, bool) for x in values
        ):
            return JSONResponse({"error": "values must be a list of numbers"}, status_code=422)
        other = TDigest()
        for entry in values:
            other.add(entry)
        merged = tdigest.merge(other)
        result = {"merged": True, "count": merged.count}
        q = body.get("q")
        if (
            isinstance(q, int | float)
            and not isinstance(q, bool)
            and 0.0 <= q <= 100.0
            and merged.count > 0
        ):
            result["percentile"] = merged.percentile(q)
        return JSONResponse(result)

    @app.get("/api/v1/fenwick")
    async def api_fenwick_stats() -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        return JSONResponse(fenwick.stats())

    @app.post("/api/v1/fenwick/update")
    async def api_fenwick_update(request: Request) -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        body = await request.json()
        try:
            fenwick.update(body.get("index"), body.get("delta"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(
            {
                "index": body.get("index"),
                "delta": body.get("delta"),
                "total": fenwick.stats()["total"],
            }
        )

    @app.post("/api/v1/fenwick/query")
    async def api_fenwick_query(request: Request) -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        body = await request.json()
        try:
            total = fenwick.range_sum(body.get("lo"), body.get("hi"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"lo": body.get("lo"), "hi": body.get("hi"), "sum": total})

    @app.post("/api/v1/fenwick/point")
    async def api_fenwick_point(request: Request) -> JSONResponse:
        if fenwick is None:
            return JSONResponse({"error": "no fenwick tree configured"})
        body = await request.json()
        try:
            value = fenwick.point_query(body.get("index"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"index": body.get("index"), "value": value})

    @app.get("/api/v1/segtree")
    async def api_segtree_stats() -> JSONResponse:
        if segtree is None:
            return JSONResponse({"error": "no segment tree configured"})
        return JSONResponse(segtree.stats())

    @app.post("/api/v1/segtree/update")
    async def api_segtree_update(request: Request) -> JSONResponse:
        if segtree is None:
            return JSONResponse({"error": "no segment tree configured"})
        body = await request.json()
        try:
            segtree.update(body.get("index"), body.get("value"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(
            {
                "index": body.get("index"),
                "value": body.get("value"),
                "aggregate": segtree.stats()["aggregate"],
            }
        )

    @app.post("/api/v1/segtree/query")
    async def api_segtree_query(request: Request) -> JSONResponse:
        if segtree is None:
            return JSONResponse({"error": "no segment tree configured"})
        body = await request.json()
        try:
            result = segtree.query(body.get("lo"), body.get("hi"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(
            {"lo": body.get("lo"), "hi": body.get("hi"), "mode": segtree.mode, "result": result}
        )

    @app.post("/api/v1/segtree/point")
    async def api_segtree_point(request: Request) -> JSONResponse:
        if segtree is None:
            return JSONResponse({"error": "no segment tree configured"})
        body = await request.json()
        try:
            value = segtree.point_query(body.get("index"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"index": body.get("index"), "value": value})

    @app.get("/api/v1/unionfind")
    async def api_unionfind_stats() -> JSONResponse:
        if unionfind is None:
            return JSONResponse({"error": "no union-find configured"})
        return JSONResponse(unionfind.stats())

    @app.post("/api/v1/unionfind/union")
    async def api_unionfind_union(request: Request) -> JSONResponse:
        if unionfind is None:
            return JSONResponse({"error": "no union-find configured"})
        body = await request.json()
        try:
            united = unionfind.union(body.get("a"), body.get("b"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(
            {
                "a": body.get("a"),
                "b": body.get("b"),
                "united": united,
                "components": unionfind.component_count(),
            }
        )

    @app.post("/api/v1/unionfind/find")
    async def api_unionfind_find(request: Request) -> JSONResponse:
        if unionfind is None:
            return JSONResponse({"error": "no union-find configured"})
        body = await request.json()
        try:
            root = unionfind.find(body.get("a"))
            csize = unionfind.component_size(body.get("a"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"a": body.get("a"), "root": root, "component_size": csize})

    @app.post("/api/v1/unionfind/connected")
    async def api_unionfind_connected(request: Request) -> JSONResponse:
        if unionfind is None:
            return JSONResponse({"error": "no union-find configured"})
        body = await request.json()
        try:
            result = unionfind.connected(body.get("a"), body.get("b"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"a": body.get("a"), "b": body.get("b"), "connected": result})

    register_trie_routes(app, trie)

    register_lru_routes(app, lru_cache)

    register_reservoir_routes(app, reservoir)

    register_cuckoo_routes(app, cuckoo)

    register_topk_routes(app, space_saving)

    register_minhash_routes(app, minhash)

    register_simhash_routes(app, simhash)

    register_quotient_routes(app, quotient)

    register_gk_quantile_routes(app, gk_quantile)

    register_kll_sketch_routes(app, kll)

    register_theta_sketch_routes(app, theta)

    register_count_sketch_routes(app, count_sketch)

    register_lossy_count_routes(app, lossy)

    register_ddsketch_routes(app, ddsketch)

    register_exponential_histogram_routes(app, exp_histogram)

    register_weighted_reservoir_routes(app, weighted_reservoir)

    register_misra_gries_routes(app, misra_gries)

    register_xor_filter_routes(app, xor_filter)

    register_ribbon_routes(app, ribbon_filter)

    register_heavykeeper_routes(app, heavykeeper)

    register_spectralbloom_routes(app, spectral_bloom)

    register_augmentedsketch_routes(app, augmented_sketch)

    register_qdigest_routes(app, qdigest)

    register_momentsketch_routes(app, moment_sketch)

    register_countingbloom_routes(app, counting_bloom)

    register_binaryfuse_routes(app, binary_fuse)

    register_vacuum_routes(app, vacuum_filter)

    register_stablebloom_routes(app, stable_bloom)

    register_morris_routes(app, morris_counter)

    register_linearcounting_routes(app, linear_counter)

    register_treap_routes(app, treap)

    register_bloomier_routes(app, bloomier)

    register_minhashlsh_routes(app, minhash_lsh)

    register_tinylfu_routes(app, tiny_lfu)

    register_hyperminhash_routes(app, hyper_minhash)

    register_scalablebloom_routes(app, scalable_bloom)

    register_rendezvous_routes(app, rendezvous)

    register_maglev_routes(app, maglev)

    register_iblt_routes(app, iblt)

    register_bbitminhash_routes(app, bbit_minhash)

    register_cusketch_routes(app, cu_sketch)

    register_jump_routes(app, jump_hash)

    register_frugal_routes(app, frugal)

    register_simhashlsh_routes(app, simhash_lsh)

    register_randomprojection_routes(app, random_projection)

    register_gcs_routes(app, gcs)

    register_fmsketch_routes(app, fm_sketch)

    register_ams_routes(app, ams)

    register_prioritysample_routes(app, priority_sample)

    register_cuckoohash_routes(app, cuckoo_hashtable)

    register_splaytree_routes(app, splay_tree)

    register_rankselect_routes(app, rank_select)

    register_wavelet_routes(app, wavelet_tree)

    register_skewheap_routes(app, skew_heap)

    register_intervaltree_routes(app, interval_tree)

    register_sparsetable_routes(app, sparse_table)

    register_kdtree_routes(app, kd_tree)

    register_radixtree_routes(app, radix_tree)

    register_suffixarray_routes(app, suffix_array)

    register_ahocorasick_routes(app, aho_corasick)

    register_xortrie_routes(app, xor_trie)

    register_minmaxheap_routes(app, min_max_heap)

    register_cartesiantree_routes(app, cartesian_tree)

    register_fenwick2d_routes(app, fenwick2d)

    register_sqrtdecomp_routes(app, sqrt_decomposition)

    register_lichao_routes(app, li_chao_tree)

    register_perseg_routes(app, persistent_segment_tree)

    register_pairingheap_routes(app, pairing_heap)

    register_suffixautomaton_routes(app, suffix_automaton)

    register_veb_routes(app, van_emde_boas)

    register_pr_quadtree_routes(app, pr_quadtree)

    register_fibonacci_routes(app, fibonacci_heap)

    register_avl_routes(app, avl_tree)

    register_btree_routes(app, b_tree)

    register_rangetree_routes(app, range_tree)

    register_leftist_routes(app, leftist_heap)

    register_scapegoat_routes(app, scapegoat_tree)

    register_binomial_routes(app, binomial_heap)

    register_binarylifting_routes(app, binary_lifting)

    register_implicittreap_routes(app, implicit_treap)

    register_lazyseg_routes(app, lazy_segment_tree)

    register_tst_routes(app, ternary_search_tree)

    register_hld_routes(app, heavy_light)

    register_sparseseg_routes(app, sparse_segment_tree)

    register_convexhull_routes(app, convex_hull)

    register_polygon_routes(app, polygon)

    register_quasar_routes(app, quasar)  # Plane 8 — QUASAR GATE inference router

    register_starmap_routes(app, starmap)  # Plane 6 — STARMAP knowledge graph

    register_bastion_routes(app, bastion)  # Plane 7 — BASTION security shield

    register_helios_routes(app, helios)  # Agent 2 — HELIOS FORGE build engine

    register_citadel_routes(app, citadel)  # Plane 9 — NIGHT CITADEL self-improvement

    register_sentinel_routes(app, sentinel)  # Agent 5 — SENTINEL WATCH adversarial defense

    register_synaptic_routes(app, synaptic)  # Agent 6 — SYNAPTIC MIND model management

    register_nexus_routes(app, nexus)  # Agent 4 — NEXUS WEAVE A2A orchestration

    register_chronicle_routes(app, chronicle)  # Agent 7 — CHRONICLE SAGE institutional memory

    register_specter_routes(app, specter)  # SPECTER — web-action executor

    register_prism_routes(app, prism)  # PRISM — creative artifact production

    register_aether_routes(app, aether)  # Plane 10 — AETHER SHELL experience layer

    register_research_routes(app, research)  # RESEARCH — autonomous intelligence gathering

    register_skills_routes(app, skills)  # SKILL LIBRARY — learn-from-experience self-improvement

    register_codemap_routes(app, codemap)  # CODEMAP — structural self-knowledge of own code

    register_review_routes(app, review)  # REVIEW GATE — vet self-modifications before commit

    register_fortify_routes(app, fortify)  # FORTIFY — self-hardening audit of own code

    register_evolve_routes(app, evolve)  # EVOLVE — autonomous self-improvement pipeline

    register_ascent_routes(app, ascent)  # ASCENT — autonomous self-improvement loop (orchestrator)

    register_guild_routes(app, guild)  # GUILD — organization of specialist agents

    register_license_routes(app, licensing)  # LICENSING — signed offline tiers + entitlements

    register_system_routes(app)  # SYSTEM — real CPU/RAM/disk/net + processes + filesystem (the OS shell's live data)

    register_foresight_routes(app)  # FORESIGHT — predict/act/compare/learn (metacognition autonomy layer)

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


# The Sovereign Command Console (the glassmorphic OS face: dual SOVEREIGN/MANUAL
# views + four time-of-day themes). Kept in its own module so this string-heavy
# UI doesn't bloat the web app; served verbatim at "/".
from pradyos.web.console import CONSOLE_HTML as _DASHBOARD_HTML


def main() -> None:
    """Entry point: pradyos-web."""
    import uvicorn

    from pradyos.ascent import AscentApplier, AscentDriver, AscentLoop, OwnModuleSource
    from pradyos.campaign.registry import CampaignRegistry
    from pradyos.core.audit import get_audit_log
    from pradyos.core.bus import get_bus
    from pradyos.core.llm import resolve_provider
    from pradyos.core.web_agent import WebAgent
    from pradyos.evolve import EvolveEngine, LLMProposer
    from pradyos.guild import ExperienceStore, GuildOrg, LLMGuildWorker, memory_tool, research_tool
    from pradyos.imperium.checkpoint import CheckpointStore
    from pradyos.research import (
        ArxivSource,
        GitHubSource,
        HackerNewsSource,
        ResearchEngine,
        RssSource,
        WebAgentSource,
    )

    bus = get_bus()
    registry = CampaignRegistry()
    checkpoint = CheckpointStore()
    # Live intelligence gathering: the default create_app() used by tests
    # registers no source and stays deterministic/offline; production wires the
    # full breadth below.
    web_agent = WebAgent()
    github_token = os.environ.get("PRADYOS_GITHUB_TOKEN") or None  # optional, higher rate limit
    # Live intelligence breadth: open web + feeds + code hosts + the developer
    # zeitgeist (Hacker News) + scientific papers (arXiv). web/rss/arxiv share ONE
    # WebAgent (single guardrail/cache); github + hackernews use their own JSON fetch.
    research = ResearchEngine(
        sources=[
            WebAgentSource(web_agent=web_agent),
            RssSource(web_agent=web_agent),
            GitHubSource(token=github_token),
            HackerNewsSource(),
            ArxivSource(web_agent=web_agent),
        ]
    )
    # One pluggable LLM provider for ALL agents — defaults to local, free Ollama;
    # switchable to a stronger model via PRADYOS_LLM_* env (the Sovereign opts in
    # to spend). EVOLVE + the GUILD share it, so one config change makes every
    # agent smarter. If the model is absent, callers degrade gracefully.
    llm = resolve_provider()
    evolve = EvolveEngine(proposer=LLMProposer(llm))
    # Close the loop: ASCENT shares the live EVOLVE engine, so its autonomous
    # cycles flow through the same local-LLM proposer + gate. The default
    # create_app() used by tests wires no loop (survey/decide stays deterministic).
    # The apply-gate: a Sovereign-approved promote is STAGED (re-gated + audited)
    # into a writable dir — the OS never overwrites its own running source (and
    # can't, under ProtectSystem=strict); a privileged deploy step promotes it.
    apply_root = (
        Path(os.environ.get("PRADYOS_STATE_PATH") or "/var/lib/pradyos/state") / "ascent-applied"
    )
    ascent = AscentLoop(
        evolve=evolve,
        applier=AscentApplier(apply_root=apply_root, audit=get_audit_log()),
    )
    # A working organization of specialist agents (planner/researcher/engineer/
    # analyst/critic/synthesizer) on the same shared LLM provider, equipped with
    # OS tools: the researcher runs LIVE RESEARCH on the objective and posts its
    # findings to the team's blackboard — agents that act, not just talk. Tests
    # wire neither worker nor tools.
    # Continual learning: a long-term experience store lets the guild recall
    # relevant past work before it starts (planner uses the memory tool) and
    # remember each project's synthesis after — so the team improves with use.
    guild_memory = ExperienceStore()
    guild = GuildOrg(
        worker=LLMGuildWorker(llm),
        toolbox=[research_tool(research), memory_tool(guild_memory)],
        role_tools={"researcher": ["research"], "planner": ["memory"]},
        memory=guild_memory,
    )
    # Licensing: verify a signed license against the shipped public key and gate
    # premium tiers. No key/license on disk ⇒ free tier (the OS still runs).
    from pradyos.licensing import Ed25519Verifier, LicenseVault

    licensing = LicenseVault()
    pub_key = Path("/etc/pradyos/license.pub")
    if pub_key.exists():
        try:
            licensing = LicenseVault(verifier=Ed25519Verifier(pub_key.read_text(encoding="utf-8")))
            key_file = Path("/etc/pradyos/license.key")
            if key_file.exists():
                licensing.install(key_file.read_text(encoding="utf-8").strip())
        except Exception as exc:  # noqa: BLE001 — a bad license must not block boot
            log.warning("license not activated (running free tier): %s", exc)
    app = create_app(
        campaign_registry=registry,
        checkpoint_store=checkpoint,
        bus=bus,
        research=research,
        evolve=evolve,
        ascent=ascent,
        guild=guild,
        licensing=licensing,
    )
    # Make the loop AUTONOMOUS: a background heartbeat surveys the OS's own
    # modules and runs ASCENT cycles in real time (read-only; promotes only queue
    # for the Sovereign). The lifespan starts/stops it; tests attach no driver.
    raw_ascent_interval = os.environ.get("PRADYOS_ASCENT_INTERVAL")
    try:
        ascent_interval = float(raw_ascent_interval) if raw_ascent_interval else 300.0
    except (TypeError, ValueError):
        log.warning(
            "Invalid PRADYOS_ASCENT_INTERVAL=%r; falling back to 300.0s", raw_ascent_interval
        )
        ascent_interval = 300.0
    ascent_driver = AscentDriver(ascent, OwnModuleSource(), interval_s=ascent_interval)
    app.state.ascent_driver = ascent_driver

    @app.get("/api/v1/ascent/driver", include_in_schema=True)
    async def _api_ascent_driver_status() -> JSONResponse:
        return JSONResponse(ascent_driver.status())

    @app.get("/api/v1/llm/info", include_in_schema=True)
    async def _api_llm_info() -> JSONResponse:
        # The active model the agents run on (no API key — never exposed).
        info = llm.info() if hasattr(llm, "info") else {"provider": getattr(llm, "name", "unknown")}
        return JSONResponse(info)

    log.info("Starting Sovereign Web Dashboard on 0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, loop="asyncio", log_level="info")


if __name__ == "__main__":
    main()
