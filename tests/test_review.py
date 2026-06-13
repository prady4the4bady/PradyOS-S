"""REVIEW GATE tests — the self-modification review panel verified deterministically."""

from __future__ import annotations

import pytest

from pradyos.review import ReviewError, ReviewGate


def _g() -> ReviewGate:
    return ReviewGate()


def _lens(d, name):
    return next(lens for lens in d["lenses"] if lens["name"] == name)


# ── approve ───────────────────────────────────────────────────────────────────


def test_clean_change_is_approved():
    d = _g().assess(
        "pradyos/foo.py", before="def public():\n    pass\n", after="def public():\n    return 1\n"
    )
    assert d["decision"] == "approve"
    assert all(lens["verdict"] == "pass" for lens in d["lenses"])


def test_new_file_is_approved():
    d = _g().assess("pradyos/new.py", after="def helper():\n    return 1\n")
    assert d["decision"] == "approve"
    assert _lens(d, "api_preservation")["verdict"] == "pass"


# ── deny (hard lenses) ────────────────────────────────────────────────────────


def test_unparseable_change_is_denied():
    d = _g().assess("pradyos/foo.py", after="def (:\n")
    assert d["decision"] == "deny"
    assert _lens(d, "parse")["verdict"] == "fail"


def test_public_api_removal_is_denied():
    d = _g().assess(
        "pradyos/foo.py",
        before="def alpha():\n    pass\n\n\ndef beta():\n    pass\n",
        after="def alpha():\n    pass\n",
    )
    assert d["decision"] == "deny"
    assert _lens(d, "api_preservation")["verdict"] == "fail"
    assert "beta" in d["summary"]


def test_test_deletion_is_denied():
    d = _g().assess(
        "tests/test_x.py",
        before="def test_a():\n    pass\n\n\ndef test_b():\n    pass\n",
        after="def test_a():\n    pass\n",
    )
    assert d["decision"] == "deny"
    assert _lens(d, "test_retention")["verdict"] == "fail"


# ── escalate (forbidden path) ─────────────────────────────────────────────────


def test_constitution_change_escalates():
    d = _g().assess("pradyos/core/constitution.py", before="x = 1\n", after="x = 2\n")
    assert d["decision"] == "escalate"
    assert _lens(d, "forbidden_path")["verdict"] == "warn"


def test_bastion_change_escalates():
    d = _g().assess("pradyos/bastion/shield.py", before="y = 1\n", after="y = 2\n")
    assert d["decision"] == "escalate"


# ── revise (soft warnings) ────────────────────────────────────────────────────


def test_large_change_needs_revision():
    after = "x = 1\n" * 500
    d = _g().assess("pradyos/foo.py", after=after)
    assert d["decision"] == "revise"
    assert _lens(d, "change_size")["verdict"] == "warn"


# ── validation / introspection ────────────────────────────────────────────────


def test_assess_validation():
    g = _g()
    with pytest.raises(ReviewError):
        g.assess("", after="x = 1")
    with pytest.raises(ReviewError):
        g.assess("p", after=123)
    with pytest.raises(ReviewError):
        g.assess("p", after="x = 1", before=123)


def test_review_retrieval_and_stats_and_reset():
    g = _g()
    g.assess("pradyos/a.py", after="def a():\n    return 1\n")  # approve
    g.assess("pradyos/core/constitution.py", after="z = 1\n")  # escalate
    assert g.review(1)["decision"] == "approve"
    assert len(g.reviews()) == 2
    s = g.stats()
    assert (
        s["reviews"] == 2 and s["by_decision"]["approve"] == 1 and s["by_decision"]["escalate"] == 1
    )
    with pytest.raises(ReviewError):
        g.review(99)
    g.reset()
    assert g.stats()["reviews"] == 0
