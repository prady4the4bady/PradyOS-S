"""Tests for CAUSALITY (L5) — counterfactual credit assignment.

Headline: it distinguishes a real cause from a bystander that merely co-occurs,
and is honest ('insufficient') when it hasn't seen enough trials.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.causality import CausalEngine
from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_real_cause_has_high_strength():
    eng = CausalEngine()
    # 'retry' always yields success; without it, never
    for _ in range(8):
        eng.observe(["retry"], ["success"])
        eng.observe([], [])
    cf = eng.counterfactual("retry", "success")
    assert cf["status"] == "ok"
    assert cf["p_with_cause"] == 1.0
    assert cf["p_without_cause"] == 0.0
    assert cf["strength"] == 1.0
    assert cf["interpretation"] == "strong cause"


def test_bystander_has_near_zero_strength():
    eng = CausalEngine()
    # 'noise' is present in half of all trials but never changes the effect rate
    for i in range(20):
        causes = ["noise"] if i % 2 == 0 else []
        effects = ["effect"] if i % 4 < 2 else []  # 50% regardless of noise
        eng.observe(causes, effects)
    cf = eng.counterfactual("noise", "effect")
    assert cf["status"] == "ok"
    assert abs(cf["strength"]) < 0.15
    assert "bystander" in cf["interpretation"]


def test_insufficient_data_is_honest():
    eng = CausalEngine(min_trials=5)
    eng.observe(["x"], ["y"])
    cf = eng.counterfactual("x", "y")
    assert cf["status"] == "insufficient"


def test_attribute_ranks_strongest_cause_first():
    eng = CausalEngine()
    for _ in range(10):
        eng.observe(["strong", "weak"], ["win"])  # strong always present on wins
        eng.observe(["weak"], [])                  # weak also appears on non-wins
    ranked = eng.attribute("win")
    assert ranked[0]["cause"] == "strong"
    assert ranked[0]["strength"] >= ranked[-1]["strength"]


def test_empty_baseline_trial_is_allowed():
    # the 'nothing happened' trial is essential for P(effect|¬cause)
    eng = CausalEngine()
    out = eng.observe([], [])
    assert out["trials"] == 1


def test_preventor_is_detected():
    eng = CausalEngine()
    for _ in range(8):
        eng.observe(["guard"], [])             # guard present → effect suppressed
        eng.observe([], ["incident"])          # no guard → incident happens
    cf = eng.counterfactual("guard", "incident")
    assert cf["strength"] < 0
    assert "preventor" in cf["interpretation"]


# ── HTTP ─────────────────────────────────────────────────────────────────────


def test_http_observe_and_counterfactual():
    c = _client()
    for _ in range(6):
        c.post("/api/v1/causality/observe", json={"causes": ["a"], "effects": ["b"]})
        c.post("/api/v1/causality/observe", json={"causes": [], "effects": []})
    cf = c.get("/api/v1/causality/counterfactual", params={"cause": "a", "effect": "b"}).json()
    assert cf["status"] == "ok" and cf["strength"] > 0.5


def test_http_observe_validates_lists():
    c = _client()
    assert c.post("/api/v1/causality/observe", json={"causes": "a", "effects": []}).status_code == 422
