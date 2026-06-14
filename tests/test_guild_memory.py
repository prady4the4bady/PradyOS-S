"""GUILD memory tests — continual learning (recall-before-act, store-after)."""

from __future__ import annotations

import pytest

from pradyos.guild import ExperienceStore, GuildError, GuildOrg, memory_tool


class _Worker:
    def __init__(self) -> None:
        self.seen: dict[str, list[str]] = {}

    def __call__(self, role, objective, context) -> str:
        self.seen[role.name] = [c["role"] for c in context]
        return f"{role.name} did: {objective}"


# ── ExperienceStore ─────────────────────────────────────────────────────────────


def test_store_remember_and_recall_by_overlap():
    s = ExperienceStore()
    s.remember("design a rate limiter", "use a token bucket with redis", tags=["engineer"])
    s.remember("bake sourdough bread", "long cold ferment", tags=["chef"])
    hits = s.recall("rate limiter design for the api", limit=3)
    assert len(hits) == 1 and hits[0]["objective"] == "design a rate limiter"
    assert hits[0]["tags"] == ["engineer"]


def test_recall_ranks_overlap_then_recency():
    s = ExperienceStore()
    s.remember("async runtime in rust", "tokio", tags=[])
    s.remember("rust async web framework", "axum on tokio", tags=[])
    s.remember("python typing", "pep 484", tags=[])
    hits = s.recall("rust async", limit=3)
    assert [h["objective"] for h in hits] == [
        "rust async web framework",  # overlap 2, newer
        "async runtime in rust",  # overlap 2, older
    ]


def test_recall_no_overlap_is_empty():
    s = ExperienceStore()
    s.remember("design a rate limiter", "token bucket", tags=[])
    assert s.recall("quantum chromodynamics") == []


def test_store_validation():
    s = ExperienceStore()
    with pytest.raises(GuildError):
        s.remember("", "x")
    with pytest.raises(GuildError):
        s.remember("obj", 5)
    with pytest.raises(GuildError):
        s.recall("q", limit=0)


def test_store_stats_and_reset():
    s = ExperienceStore()
    s.remember("a", "b")
    assert s.stats()["experiences"] == 1
    s.reset()
    assert s.stats()["experiences"] == 0


# ── memory_tool ─────────────────────────────────────────────────────────────────


def test_memory_tool_surfaces_past_work():
    s = ExperienceStore()
    s.remember("design a rate limiter", "use a token bucket", tags=[])
    tool = memory_tool(s)
    out = tool.run("build a rate limiter for the gateway")
    assert tool.name == "memory" and "token bucket" in out and "past work" in out.lower()


def test_memory_tool_empty_when_nothing_relevant():
    assert memory_tool(ExperienceStore()).run("anything") == ""


# ── GuildOrg integration: store-after + recall-before-act ──────────────────────


def test_guild_stores_synthesis_after_run():
    store = ExperienceStore()
    org = GuildOrg(worker=_Worker(), memory=store)
    org.run("ship a CLI tool")
    assert store.stats()["experiences"] == 1
    assert org.stats()["memory"] == 1 and org.stats()["memory_wired"] is True
    # the stored content is the project synthesis
    assert "ship a CLI tool" in store.all()[-1]["content"]


def test_guild_recall_returns_past_work():
    store = ExperienceStore()
    org = GuildOrg(worker=_Worker(), memory=store)
    org.run("design a rate limiter")
    assert org.recall("rate limiter")[0]["objective"] == "design a rate limiter"


def test_planner_recalls_before_acting():
    # First project seeds memory; the second project's planner sees it via the tool.
    store = ExperienceStore()
    worker = _Worker()
    org = GuildOrg(
        worker=worker,
        toolbox=[memory_tool(store)],
        role_tools={"planner": ["memory"]},
        memory=store,
    )
    org.run("design a rate limiter")  # seeds memory
    proj = org.run("build a rate limiter for the api")  # planner should recall it
    assert {"role": "planner", "tool": "memory"} in proj["tool_uses"]
    # the recalled past work is on the blackboard the planner saw
    assert "tool:memory" in worker.seen["planner"]


def test_guild_without_memory_recall_is_empty_and_stats_zero():
    org = GuildOrg(worker=_Worker())
    org.run("x")
    assert org.recall("x") == []
    assert org.stats()["memory_wired"] is False and org.stats()["memory"] == 0
