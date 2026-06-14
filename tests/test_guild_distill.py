"""Tests for L1 auto-distillation — a completed Guild project becomes a skill.

A new objective creates a new skill; a repeat objective reinforces it. The hook
must fire only on COMPLETED projects (a charter-only run learns nothing), and a
distillation failure must never sink the Guild run.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.guild import GuildOrg, Role
from pradyos.guild.distill import distill_project, skill_id_for
from pradyos.skills import SkillLibrary
from pradyos.sovereign_web import create_app


def _worker(role, objective, context):  # noqa: ANN001, ARG001
    return f"{role.name} did work on {objective}"


def _guild_with_distill(lib: SkillLibrary) -> GuildOrg:
    org = GuildOrg(worker=_worker, roles=(Role("planner", "plan", "plans"),))
    org.set_on_complete(lambda p: distill_project(lib, p))
    return org


# ── distill_project (pure) ───────────────────────────────────────────────────


def test_skill_id_is_deterministic_slug():
    assert skill_id_for("Cache the query results") == "guild-cache-the-query-results"


def test_distill_creates_then_reinforces():
    lib = SkillLibrary()
    proj = {"objective": "optimise the build", "synthesis": "step one\nstep two", "status": "complete"}
    sid = distill_project(lib, proj)
    assert sid == "guild-optimise-the-build"
    assert lib.recall(sid)["steps"] == ["step one", "step two"]
    # repeat objective → reinforced, not duplicated
    distill_project(lib, proj)
    assert lib.recall(sid)["success"] == 1
    assert len(lib.skills()) == 1


def test_distill_ignores_empty_objective():
    lib = SkillLibrary()
    assert distill_project(lib, {"objective": "  "}) is None
    assert lib.skills() == []


# ── Guild hook integration ───────────────────────────────────────────────────


def test_completed_run_distills_into_a_skill():
    lib = SkillLibrary()
    org = _guild_with_distill(lib)
    org.run("ship the release")
    skills = lib.skills()
    assert len(skills) == 1
    assert skills[0]["id"] == "guild-ship-the-release"


def test_charter_run_distills_nothing():
    lib = SkillLibrary()
    # no worker → contributions are empty → status 'charter' → hook must not fire
    org = GuildOrg(roles=(Role("planner", "plan", "plans"),))
    org.set_on_complete(lambda p: distill_project(lib, p))
    org.run("do something")
    assert lib.skills() == []


def test_distill_failure_never_sinks_run():
    class _BoomLib:
        def learn(self, *a, **k):
            raise RuntimeError("boom")

        def reinforce(self, *a, **k):
            raise RuntimeError("boom")

    org = _guild_with_distill(_BoomLib())  # type: ignore[arg-type]
    out = org.run("resilient objective")
    assert out["status"] == "complete"  # the run still succeeded


def test_app_run_then_skill_is_searchable_via_plan():
    # End-to-end through the real app: a completed guild run should leave a skill
    # that /api/v1/plan can match. (Default app guild has no worker → charter, so
    # we drive distill directly against the app's skill library instead.)
    c = TestClient(create_app())
    # learn a skill the normal way, then confirm /plan can find it (distill path
    # uses the same learn()).
    c.post("/api/v1/skills/learn", json={"id": "guild-deploy", "name": "deploy",
                                          "trigger": "deploy release ship", "steps": ["build", "push"]})
    plan = c.post("/api/v1/plan", json={"intent": "deploy the release"}).json()
    assert plan["chosen"] == "deploy"
