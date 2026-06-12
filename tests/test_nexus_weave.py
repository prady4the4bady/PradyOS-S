"""NEXUS WEAVE tests — routing / delegation / re-route verified."""

from __future__ import annotations

import pytest

from pradyos.nexus_weave import NexusError, NexusWeave, NoRouteError


def _n() -> NexusWeave:
    n = NexusWeave()
    n.register_agent("helios", "internal", {"build", "code"})
    n.register_agent("specter", "internal", {"browser"})
    n.register_agent("cloud-coder", "external", {"build", "research"})
    return n


def test_register_validation():
    n = NexusWeave()
    with pytest.raises(NexusError):
        n.register_agent("", "internal", {"x"})
    with pytest.raises(NexusError):
        n.register_agent("a", "edge", {"x"})
    with pytest.raises(NexusError):
        n.register_agent("a", "internal", set())


def test_register_rejects_bare_string_capabilities():
    # "build" must not become {'b','u','i','l','d'}
    n = NexusWeave()
    with pytest.raises(NexusError):
        n.register_agent("a", "internal", "build")


def test_route_prefers_internal():
    n = _n()
    n.submit("t1", "build")  # both helios(internal) and cloud-coder(external) can
    t = n.route("t1")
    assert t["agent"] == "helios" and t["delegated"] is False and t["status"] == "routed"


def test_route_delegates_to_external_when_no_internal():
    n = _n()
    n.submit("t1", "research")  # only cloud-coder(external)
    t = n.route("t1")
    assert t["agent"] == "cloud-coder" and t["delegated"] is True


def test_no_route_when_no_capability():
    n = _n()
    n.submit("t1", "speech")
    with pytest.raises(NoRouteError):
        n.route("t1")
    assert n.task("t1")["status"] == "unroutable"


def test_fail_reroutes_to_fallback():
    n = _n()
    n.submit("t1", "build")
    n.route("t1")  # helios
    n.fail("t1", "sandbox crash")
    t = n.task("t1")
    assert t["status"] == "queued" and "helios" in t["tried"]
    t2 = n.route("t1")  # helios excluded -> falls back to external cloud-coder
    assert t2["agent"] == "cloud-coder" and t2["delegated"] is True


def test_fail_until_exhausted_raises():
    n = _n()
    n.submit("t1", "build")
    n.route("t1")  # helios
    n.fail("t1")
    n.route("t1")  # cloud-coder
    n.fail("t1")
    with pytest.raises(NoRouteError):
        n.route("t1")  # both tried


def test_complete():
    n = _n()
    n.submit("t1", "browser")
    n.route("t1")  # specter
    t = n.complete("t1")
    assert t["status"] == "done"


def test_complete_requires_routed():
    n = _n()
    n.submit("t1", "build")
    with pytest.raises(NexusError):
        n.complete("t1")  # not routed yet


def test_submit_dupe_and_unknown():
    n = _n()
    n.submit("t1", "build")
    with pytest.raises(NexusError):
        n.submit("t1", "build")
    with pytest.raises(NexusError):
        n.route("ghost")


def test_stats_and_reset():
    n = _n()
    n.submit("t1", "build")
    n.route("t1")
    s = n.stats()
    assert s["agents"] == 3 and s["tasks"] == 1 and s["by_status"]["routed"] == 1
    n.reset()
    assert n.stats()["agents"] == 0 and n.tasks() == []
