"""AETHER SHELL tests — intent routing + chamber composition verified."""

from __future__ import annotations

import pytest

from pradyos.aether_shell import AetherError, AetherShell


def _a() -> AetherShell:
    return AetherShell()


# ── intent routing ─────────────────────────────────────────────────────────────


def test_intent_routes_governance():
    a = _a()
    i = a.capture_intent("i1", "Approve the proposal for project X")
    assert i["surface"] == "governance"


def test_intent_routes_projects():
    assert _a().capture_intent("i", "start a new build")["surface"] == "projects"


def test_intent_routes_alerts():
    assert _a().capture_intent("i", "show me the latest incident")["surface"] == "alerts"


def test_intent_routes_status():
    assert _a().capture_intent("i", "what is empire health")["surface"] == "status"


def test_intent_routes_gallery():
    assert _a().capture_intent("i", "open the artifact gallery")["surface"] == "gallery"


def test_intent_defaults_to_projects():
    assert _a().capture_intent("i", "hmm, something vague")["surface"] == "projects"


def test_intent_validation():
    a = _a()
    with pytest.raises(AetherError):
        a.capture_intent("", "x")
    with pytest.raises(AetherError):
        a.capture_intent("i", "")


# ── cards ───────────────────────────────────────────────────────────────────────


def test_push_card_validation():
    a = _a()
    with pytest.raises(AetherError):
        a.push_card("c", "void", "t")
    with pytest.raises(AetherError):
        a.push_card("c", "governance", "t", urgency="panic")
    with pytest.raises(AetherError):
        a.push_card("c", "governance", "")


def test_push_dupe_raises():
    a = _a()
    a.push_card("c", "governance", "t")
    with pytest.raises(AetherError):
        a.push_card("c", "governance", "t2")


def test_ack_card_removes_from_active():
    a = _a()
    a.push_card("c", "alerts", "breach!", urgency="urgent")
    assert a.experience()["counts"]["active"] == 1
    a.ack_card("c")
    assert a.experience()["counts"]["active"] == 0
    assert a.experience()["counts"]["acked"] == 1


def test_ack_unknown_and_double():
    a = _a()
    with pytest.raises(AetherError):
        a.ack_card("ghost")
    a.push_card("c", "alerts", "x")
    a.ack_card("c")
    with pytest.raises(AetherError):
        a.ack_card("c")


# ── experience composition ──────────────────────────────────────────────────────


def test_experience_urgent_first_then_oldest():
    a = _a()
    a.push_card("c1", "projects", "info card", urgency="info")  # seq 1
    a.push_card("c2", "alerts", "urgent A", urgency="urgent")  # seq 2
    a.push_card("c3", "governance", "urgent B", urgency="urgent")  # seq 3
    a.push_card("c4", "status", "attention", urgency="attention")  # seq 4
    order = [c["id"] for c in a.experience()["active"]]
    # urgent (oldest-first) -> attention -> info
    assert order == ["c2", "c3", "c4", "c1"]


def test_experience_groups_by_surface():
    a = _a()
    a.push_card("c1", "governance", "approve me", urgency="urgent")
    a.push_card("c2", "projects", "building")
    exp = a.experience()
    assert "governance" in exp["by_surface"] and "projects" in exp["by_surface"]
    assert exp["by_surface"]["governance"][0]["id"] == "c1"


def test_experience_headlines():
    a = _a()
    assert "All quiet" in a.experience()["headline"]
    a.push_card("c1", "projects", "x", urgency="info")
    assert "no urgency" in a.experience()["headline"]
    a.push_card("c2", "alerts", "y", urgency="urgent")
    assert "attention" in a.experience()["headline"]


def test_stats_and_reset():
    a = _a()
    a.capture_intent("i", "build")
    a.push_card("c", "projects", "x")
    s = a.stats()
    assert s["intents"] == 1 and s["cards"] == 1 and s["active_cards"] == 1
    a.reset()
    assert a.stats() == {"intents": 0, "cards": 0, "active_cards": 0}
