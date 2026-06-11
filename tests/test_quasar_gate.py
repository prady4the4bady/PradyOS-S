"""QUASAR GATE router tests — policy is verified against explicit ground truth.

Each scenario registers a known set of backends and asserts that route() returns
exactly the backend the documented policy dictates (capability → privacy →
latency → health → throttle, then local-first / cost / latency / name ordering).
"""

from __future__ import annotations

import threading

import pytest

from pradyos.quasar_gate import (
    Backend,
    NoRouteError,
    QuasarGate,
    QuasarGateError,
    RouteRequest,
    UnknownBackendError,
)


def _gate_with_pool() -> QuasarGate:
    g = QuasarGate()
    # local code model: cheapest + fastest for "code"
    g.register("ollama-local", "local", {"code", "chat"}, latency_ms=200, cost=0.0)
    # remote frontier: serves code + research, higher cost/latency
    g.register("frontier-remote", "remote", {"code", "research"}, latency_ms=900, cost=1.0)
    # remote fast chat
    g.register("groq-remote", "remote", {"chat"}, latency_ms=120, cost=0.3)
    return g


# ── registration & validation ────────────────────────────────────────────────


def test_register_and_list():
    g = _gate_with_pool()
    names = sorted(b.name for b in g.backends())
    assert names == ["frontier-remote", "groq-remote", "ollama-local"]


def test_register_replaces_by_name():
    g = QuasarGate()
    g.register("x", "local", {"code"}, latency_ms=100)
    g.register("x", "remote", {"chat"}, latency_ms=50)
    assert len(g.backends()) == 1
    assert g.describe("x")["location"] == "remote"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "location": "local", "capabilities": {"c"}, "latency_ms": 1},
        {"name": "n", "location": "edge", "capabilities": {"c"}, "latency_ms": 1},
        {"name": "n", "location": "local", "capabilities": set(), "latency_ms": 1},
        {"name": "n", "location": "local", "capabilities": {"c"}, "latency_ms": 0},
        {"name": "n", "location": "local", "capabilities": {"c"}, "latency_ms": -5},
    ],
)
def test_backend_validation(kwargs):
    with pytest.raises(QuasarGateError):
        Backend(
            name=kwargs["name"],
            location=kwargs["location"],
            capabilities=frozenset(kwargs["capabilities"]),
            latency_ms=kwargs["latency_ms"],
        )


def test_request_validation():
    with pytest.raises(QuasarGateError):
        RouteRequest(task_class="")
    with pytest.raises(QuasarGateError):
        RouteRequest(task_class="code", max_latency_ms=0)
    with pytest.raises(QuasarGateError):
        RouteRequest(task_class="code", priority="urgent")


# ── core routing policy ───────────────────────────────────────────────────────


def test_local_first_for_code():
    g = _gate_with_pool()
    # both ollama-local and frontier-remote serve "code"; local wins.
    assert g.route(RouteRequest("code")).name == "ollama-local"


def test_capability_filter():
    g = _gate_with_pool()
    # only frontier-remote serves "research".
    assert g.route(RouteRequest("research")).name == "frontier-remote"


def test_no_route_for_unknown_class():
    g = _gate_with_pool()
    with pytest.raises(NoRouteError):
        g.route(RouteRequest("speech"))


def test_local_only_excludes_remote():
    g = _gate_with_pool()
    # "chat" is served by local ollama + remote groq; local_only keeps ollama.
    assert g.route(RouteRequest("chat", local_only=True)).name == "ollama-local"
    # "research" is remote-only → local_only has no route.
    with pytest.raises(NoRouteError):
        g.route(RouteRequest("research", local_only=True))


def test_latency_budget_excludes_slow():
    g = _gate_with_pool()
    # code: ollama-local(200) vs frontier-remote(900). Budget 300 keeps only local.
    assert g.route(RouteRequest("code", max_latency_ms=300)).name == "ollama-local"
    # Budget 150 excludes both code backends.
    with pytest.raises(NoRouteError):
        g.route(RouteRequest("code", max_latency_ms=150))


def test_ordering_cost_then_latency():
    g = QuasarGate()
    # two remote backends for "chat": pick the cheaper, then the faster.
    g.register("r-cheap-slow", "remote", {"chat"}, latency_ms=800, cost=0.2)
    g.register("r-cheap-fast", "remote", {"chat"}, latency_ms=100, cost=0.2)
    g.register("r-pricey-fast", "remote", {"chat"}, latency_ms=50, cost=0.9)
    # equal cost 0.2 → faster wins among the two cheap ones.
    assert g.route(RouteRequest("chat")).name == "r-cheap-fast"


def test_name_tiebreak():
    g = QuasarGate()
    g.register("bravo", "local", {"x"}, latency_ms=100, cost=0.0)
    g.register("alpha", "local", {"x"}, latency_ms=100, cost=0.0)
    assert g.route(RouteRequest("x")).name == "alpha"


# ── health & fallback ─────────────────────────────────────────────────────────


def test_unhealthy_falls_back():
    g = _gate_with_pool()
    assert g.route(RouteRequest("code")).name == "ollama-local"
    g.mark_unhealthy("ollama-local")
    # local gone → fall back to the remote code backend.
    assert g.route(RouteRequest("code")).name == "frontier-remote"
    g.mark_healthy("ollama-local")
    assert g.route(RouteRequest("code")).name == "ollama-local"


def test_candidates_exposes_fallback_chain():
    g = _gate_with_pool()
    chain = [b.name for b in g.candidates(RouteRequest("code"))]
    assert chain == ["ollama-local", "frontier-remote"]


def test_unknown_backend_errors():
    g = _gate_with_pool()
    with pytest.raises(UnknownBackendError):
        g.mark_unhealthy("does-not-exist")


# ── throttle (acquire / release) ──────────────────────────────────────────────


def test_throttle_blocks_background_over_ceiling():
    g = QuasarGate()
    g.register("solo", "local", {"code"}, latency_ms=100, max_concurrent=1)
    # background fills the single slot...
    assert g.acquire(RouteRequest("code", priority="background")).name == "solo"
    # ...a second background request finds no slot.
    with pytest.raises(NoRouteError):
        g.acquire(RouteRequest("code", priority="background"))
    # ...but an interactive request still gets the +1 headroom slot.
    assert g.acquire(RouteRequest("code", priority="interactive")).name == "solo"
    assert g.inflight("solo") == 2
    g.release("solo")
    assert g.inflight("solo") == 1


def test_release_floor_at_zero():
    g = _gate_with_pool()
    g.release("ollama-local")  # never acquired
    assert g.inflight("ollama-local") == 0


# ── stats & reset ─────────────────────────────────────────────────────────────


def test_stats_track_routes():
    g = _gate_with_pool()
    g.route(RouteRequest("code"))
    g.route(RouteRequest("code"))
    g.route(RouteRequest("chat", local_only=True))
    try:
        g.route(RouteRequest("speech"))
    except NoRouteError:
        pass
    s = g.stats()
    assert s["routes"] == 3
    assert s["no_route"] == 1
    assert s["by_backend"]["ollama-local"] == 3
    assert s["backends"] == 3 and s["healthy"] == 3


def test_reset_clears():
    g = _gate_with_pool()
    g.route(RouteRequest("code"))
    g.reset()
    assert g.backends() == []
    assert g.stats()["routes"] == 0


# ── thread-safety: concurrent acquire/release nets to zero ────────────────────


def test_concurrent_acquire_release_consistent():
    g = QuasarGate()
    g.register("pool", "local", {"code"}, latency_ms=10, max_concurrent=1000)
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(200):
                g.acquire(RouteRequest("code", priority="interactive"))
                g.release("pool")
        except Exception as exc:  # noqa: BLE001 — surface to the assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert g.inflight("pool") == 0
    assert g.stats()["routes"] == 8 * 200
