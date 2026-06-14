"""Tests for the FORESIGHT plane — predict → deliberate → observe → learn.

The headline property: the engine becomes BETTER CALIBRATED with experience —
mean surprise for a repeated (state, action) outcome falls toward zero. Plus the
deterministic mechanics (priors, deliberation ranking, risk discount) and the
HTTP surface.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.foresight import ForesightEngine, Prediction, WorldModel
from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


# ── core: priors + learning ─────────────────────────────────────────────────


def test_prior_empty_before_any_episode():
    eng = ForesightEngine()
    assert eng.prior("s", "a") == (0.0, 0)


def test_prediction_neutral_without_experience():
    eng = ForesightEngine()
    p = eng.predict("deploy", "ship-it")
    assert p.expected_value == 0.5
    assert p.confidence < 0.3


def test_engine_learns_surprise_drops_with_experience():
    eng = ForesightEngine()
    first = eng.observe("deploy", "ship-it", 0.9)  # predicted 0.5 → big surprise
    for _ in range(8):
        eng.observe("deploy", "ship-it", 0.9)  # consistent reality
    last = eng.observe("deploy", "ship-it", 0.9)
    assert first.surprise > last.surprise
    assert last.surprise < 0.15  # well-calibrated now
    assert eng.stats()["calibration"] > 0.8


def test_prior_tracks_mean_and_count():
    eng = ForesightEngine()
    eng.observe("s", "a", 0.2)
    eng.observe("s", "a", 0.4)
    mean, n = eng.prior("s", "a")
    assert n == 2
    assert abs(mean - 0.3) < 1e-9


def test_deliberate_prefers_higher_value_action():
    eng = ForesightEngine()
    for _ in range(6):
        eng.observe("task", "good", 0.95)
        eng.observe("task", "bad", 0.05)
    decision = eng.deliberate("task", ["bad", "good"])
    assert decision["chosen"] == "good"
    assert decision["ranked"][0]["action"] == "good"


def test_deliberate_requires_actions():
    eng = ForesightEngine()
    try:
        eng.deliberate("s", [])
        raise AssertionError("expected ForesightError")
    except Exception as exc:  # noqa: BLE001
        assert "candidate action" in str(exc)


def test_injected_predictor_is_used():
    def always_high(state, action, prior):  # noqa: ANN001, ARG001
        return Prediction(0.99, 0.99, "stub")

    eng = ForesightEngine(world_model=WorldModel(predictor=always_high))
    assert eng.predict("x", "y").expected_value == 0.99


def test_outcome_value_is_clamped():
    eng = ForesightEngine()
    ep = eng.observe("s", "a", 5.0)  # out of range
    assert ep.outcome.value == 1.0


def test_recall_returns_recent_first():
    eng = ForesightEngine()
    eng.observe("s", "a", 0.1, note="old")
    eng.observe("s", "a", 0.2, note="new")
    eps = eng.recall("a", limit=2)
    assert eps[0].outcome.note == "new"


# ── HTTP surface ─────────────────────────────────────────────────────────────


def test_http_deliberate_and_learn_cycle():
    c = _client()
    # teach the engine that "cache" beats "recompute"
    for _ in range(6):
        c.post("/api/v1/foresight/observe", json={"state": "q", "action": "cache", "value": 0.9})
        c.post("/api/v1/foresight/observe", json={"state": "q", "action": "recompute", "value": 0.2})
    d = c.post("/api/v1/foresight/deliberate", json={"state": "q", "actions": ["recompute", "cache"]})
    assert d.status_code == 200
    assert d.json()["chosen"] == "cache"


def test_http_stats_and_history():
    c = _client()
    c.post("/api/v1/foresight/observe", json={"state": "s", "action": "a", "value": 0.7})
    s = c.get("/api/v1/foresight/stats").json()
    assert s["episodes"] >= 1
    h = c.get("/api/v1/foresight/history").json()
    assert isinstance(h["history"], list) and h["history"]


def test_http_observe_validation():
    c = _client()
    r = c.post("/api/v1/foresight/observe", json={"state": "s"})
    assert r.status_code == 422


def test_http_deliberate_validation():
    c = _client()
    r = c.post("/api/v1/foresight/deliberate", json={"state": "s", "actions": []})
    assert r.status_code == 422
