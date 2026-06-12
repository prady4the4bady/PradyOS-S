"""HELIOS FORGE tests — stage machine + gates verified against ground truth."""

from __future__ import annotations

import pytest

from pradyos.helios_forge import STAGES, ForgeError, HeliosForge


def _f() -> HeliosForge:
    return HeliosForge()


def test_create_starts_planned():
    m = _f().create("b1", "Project Aurora")
    assert m["stage"] == "planned" and m["stage_index"] == 0
    assert m["project"] == "Project Aurora" and m["is_terminal"] is False


def test_create_validation_and_dupe():
    f = _f()
    with pytest.raises(ForgeError):
        f.create("", "p")
    f.create("b1", "p")
    with pytest.raises(ForgeError):
        f.create("b1", "p")


def test_advance_through_early_stages():
    f = _f()
    f.create("b", "p")
    assert f.advance("b")["stage"] == "scaffolded"
    assert f.advance("b")["stage"] == "coded"
    assert f.advance("b")["stage"] == "tested"


def test_validate_gate_requires_green_tests():
    f = _f()
    f.create("b", "p")
    for _ in range(3):  # planned -> tested
        f.advance("b")
    # no tests recorded -> cannot validate
    with pytest.raises(ForgeError):
        f.advance("b")
    # failing tests -> still blocked
    f.record_tests("b", passed=5, failed=2)
    with pytest.raises(ForgeError):
        f.advance("b")
    # green tests -> validates
    f.record_tests("b", passed=7, failed=0)
    assert f.advance("b")["stage"] == "validated"


def test_stage_gate_requires_all_milestones():
    f = _f()
    f.create("b", "p")
    f.add_milestone("b", "scaffold")
    f.add_milestone("b", "tests")
    for _ in range(3):
        f.advance("b")
    f.record_tests("b", passed=1, failed=0)
    f.advance("b")  # -> validated
    # milestones incomplete -> cannot stage
    with pytest.raises(ForgeError):
        f.advance("b")
    f.complete_milestone("b", "scaffold")
    with pytest.raises(ForgeError):
        f.advance("b")
    f.complete_milestone("b", "tests")
    m = f.advance("b")  # -> staged
    assert m["stage"] == "staged" and m["is_terminal"] is True
    assert m["stage_index"] == len(STAGES) - 1


def test_cannot_advance_past_staged():
    f = _f()
    f.create("b", "p")
    for _ in range(3):
        f.advance("b")
    f.record_tests("b", passed=1, failed=0)
    f.advance("b")  # validated
    f.advance("b")  # staged
    with pytest.raises(ForgeError):
        f.advance("b")


def test_staged_build_is_immutable():
    f = _f()
    f.create("b", "p")
    for _ in range(3):
        f.advance("b")
    f.record_tests("b", passed=1, failed=0)
    f.advance("b")  # validated
    f.advance("b")  # staged (terminal)
    for mutate in (
        lambda: f.add_milestone("b", "late"),
        lambda: f.complete_milestone("b", "late"),
        lambda: f.record_artifact("b", "x", "code"),
        lambda: f.record_tests("b", passed=2, failed=0),
    ):
        with pytest.raises(ForgeError):
            mutate()


def test_complete_unknown_milestone_raises():
    f = _f()
    f.create("b", "p")
    with pytest.raises(ForgeError):
        f.complete_milestone("b", "ghost")


def test_artifacts():
    f = _f()
    f.create("b", "p")
    f.record_artifact("b", "main.py", "code")
    m = f.record_artifact("b", "test_main.py", "test")
    kinds = sorted(a["kind"] for a in m["artifacts"])
    assert kinds == ["code", "test"]
    with pytest.raises(ForgeError):
        f.record_artifact("b", "x", "binary")


def test_milestone_progress():
    f = _f()
    f.create("b", "p")
    f.add_milestone("b", "a")
    f.add_milestone("b", "b")
    m = f.complete_milestone("b", "a")
    assert m["milestone_progress"] == {"done": 1, "total": 2}


def test_record_tests_validation():
    f = _f()
    f.create("b", "p")
    with pytest.raises(ForgeError):
        f.record_tests("b", passed=-1, failed=0)


def test_stats_and_reset():
    f = _f()
    f.create("b1", "p")
    f.create("b2", "p")
    f.advance("b1")
    s = f.stats()
    assert s["builds"] == 2 and s["by_stage"]["scaffolded"] == 1 and s["by_stage"]["planned"] == 1
    f.reset()
    assert f.stats()["builds"] == 0 and f.builds() == []


def test_unknown_build_raises():
    with pytest.raises(ForgeError):
        _f().advance("nope")
