"""GUILD tests — multi-agent orchestration verified deterministically vs a fake worker."""

from __future__ import annotations

import pytest

from pradyos.guild import GuildError, GuildOrg, Role, Tool, research_tool


class _FakeWorker:
    """Records the blackboard each role saw; returns a deterministic contribution."""

    def __init__(self) -> None:
        self.seen: dict[str, list[str]] = {}

    def __call__(self, role: Role, objective: str, context: list[dict]) -> str:
        self.seen[role.name] = [c["role"] for c in context]
        return f"{role.name} handled: {objective}"


def test_roles_returns_default_roster():
    names = [r["name"] for r in GuildOrg().roles()]
    assert names == ["planner", "researcher", "engineer", "analyst", "critic", "synthesizer"]


def test_run_without_worker_is_charter_only():
    proj = GuildOrg().run("ship a feature")
    assert proj["status"] == "charter"
    assert all(c["content"] == "" for c in proj["contributions"])
    assert proj["synthesis"] == "" and proj["id"] == "proj-1"


def test_run_with_worker_each_role_contributes():
    org = GuildOrg(worker=_FakeWorker())
    proj = org.run("design an API")
    assert proj["status"] == "complete"
    assert [c["role"] for c in proj["contributions"]] == [
        "planner",
        "researcher",
        "engineer",
        "analyst",
        "critic",
        "synthesizer",
    ]
    assert all("design an API" in c["content"] for c in proj["contributions"])


def test_blackboard_accumulates_in_order():
    worker = _FakeWorker()
    GuildOrg(worker=worker).run("build X")
    assert worker.seen["planner"] == []  # first sees nothing
    assert worker.seen["researcher"] == ["planner"]
    assert worker.seen["synthesizer"] == [
        "planner",
        "researcher",
        "engineer",
        "analyst",
        "critic",
    ]


def test_synthesis_digests_contributions():
    proj = GuildOrg(worker=_FakeWorker()).run("plan a launch")
    assert "[planner]" in proj["synthesis"] and "[synthesizer]" in proj["synthesis"]
    assert proj["synthesis"].count("\n") == 5  # 6 roles → 6 lines


def test_run_custom_roster_subset_in_order():
    proj = GuildOrg(worker=_FakeWorker()).run("quick take", roster=["critic", "planner"])
    assert [c["role"] for c in proj["contributions"]] == ["critic", "planner"]
    assert proj["roster"] == ["critic", "planner"]


def test_run_unknown_role_raises():
    with pytest.raises(GuildError, match="unknown role"):
        GuildOrg(worker=_FakeWorker()).run("x", roster=["wizard"])


def test_run_empty_roster_raises():
    with pytest.raises(GuildError, match="at least one role"):
        GuildOrg(worker=_FakeWorker()).run("x", roster=[])


@pytest.mark.parametrize("bad", ["", "   ", None, 5])
def test_run_bad_objective_raises(bad):
    with pytest.raises(GuildError):
        GuildOrg().run(bad)


def test_worker_failure_degrades_that_role_only():
    class _Flaky:
        def __call__(self, role, objective, context):
            if role.name == "engineer":
                raise RuntimeError("model down")
            return f"{role.name} ok"

    proj = GuildOrg(worker=_Flaky()).run("resilient run")
    by_role = {c["role"]: c["content"] for c in proj["contributions"]}
    assert by_role["engineer"] == ""  # the one failure is empty
    assert by_role["planner"] == "planner ok"  # others still contribute
    assert proj["status"] == "complete"


def test_worker_non_string_is_coerced_empty():
    proj = GuildOrg(worker=lambda role, objective, context: 123).run("x")
    assert all(c["content"] == "" for c in proj["contributions"])


def test_project_roundtrip_and_unknown():
    org = GuildOrg(worker=_FakeWorker())
    pid = org.run("a")["id"]
    assert org.project(pid)["id"] == pid
    with pytest.raises(GuildError, match="unknown project"):
        org.project("proj-999")


def test_projects_limit_validation():
    org = GuildOrg(worker=_FakeWorker())
    for _ in range(3):
        org.run("obj")
    assert len(org.projects(limit=2)) == 2
    with pytest.raises(GuildError):
        org.projects(limit=0)


def test_stats_and_reset():
    org = GuildOrg(worker=_FakeWorker())
    org.run("a")
    s = org.stats()
    assert s["projects"] == 1 and s["contributions"] == 6 and s["roles"] == 6
    assert s["worker_configured"] is True
    org.reset()
    assert org.stats()["projects"] == 0 and org.run("b")["id"] == "proj-1"


def test_custom_roles_constructor():
    roles = (Role("scout", "recon", "scout it"), Role("boss", "decide", "decide it"))
    org = GuildOrg(worker=_FakeWorker(), roles=roles)
    assert [r["name"] for r in org.roles()] == ["scout", "boss"]
    assert [c["role"] for c in org.run("x")["contributions"]] == ["scout", "boss"]


# ── tools: agents that act, not just talk ──────────────────────────────────────


def test_tool_output_lands_on_blackboard_before_role():
    worker = _FakeWorker()
    spy = Tool("lookup", "a fake tool", lambda objective: f"FACT about {objective}")
    org = GuildOrg(
        worker=worker,
        toolbox=[spy],
        role_tools={"researcher": ["lookup"]},
    )
    proj = org.run("widgets")
    # the researcher's tool ran and its output is recorded
    assert proj["tool_uses"] == [{"role": "researcher", "tool": "lookup"}]
    # the researcher saw the tool output on the blackboard (as 'tool:lookup')
    assert "tool:lookup" in worker.seen["researcher"]
    # and everyone after the researcher also sees it
    assert "tool:lookup" in worker.seen["engineer"]


def test_tools_listed_and_counted():
    org = GuildOrg(toolbox=[Tool("a", "desc-a", lambda o: ""), Tool("b", "desc-b", lambda o: "")])
    names = [t["name"] for t in org.tools()]
    assert names == ["a", "b"] and org.stats()["tools"] == 2


def test_tool_failure_does_not_sink_project():
    def _boom(objective):
        raise RuntimeError("tool down")

    org = GuildOrg(
        worker=_FakeWorker(),
        toolbox=[Tool("flaky", "boom", _boom)],
        role_tools={"planner": ["flaky"]},
    )
    proj = org.run("x")  # must not raise
    assert proj["tool_uses"] == []  # failed tool recorded nothing
    assert proj["status"] == "complete"


def test_tool_empty_output_is_skipped():
    org = GuildOrg(
        worker=_FakeWorker(),
        toolbox=[Tool("quiet", "empty", lambda o: "   ")],
        role_tools={"planner": ["quiet"]},
    )
    assert org.run("x")["tool_uses"] == []


def test_unknown_tool_name_is_ignored():
    org = GuildOrg(worker=_FakeWorker(), role_tools={"planner": ["ghost"]})
    assert org.run("x")["tool_uses"] == []  # no such tool → no-op


def test_research_tool_digests_findings():
    class _Brief:
        @staticmethod
        def to_dict():
            return {"findings": [{"title": "Tokio", "url": "https://tokio.rs"}]}

    class _Engine:
        def research(self, objective):
            return _Brief()

    tool = research_tool(_Engine())
    out = tool.run("rust async")
    assert tool.name == "research" and "tokio.rs" in out and "Live research" in out


def test_tool_invalid_name_raises():
    with pytest.raises(GuildError):
        Tool("", "desc", lambda o: "")
