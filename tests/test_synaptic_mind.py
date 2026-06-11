"""SYNAPTIC MIND tests — benchmark + upgrade-proposal logic verified."""

from __future__ import annotations

import pytest

from pradyos.synaptic_mind import UPGRADE_MARGIN, SynapticError, SynapticMind


def _m() -> SynapticMind:
    m = SynapticMind()
    m.register_model("qwen-1.5b", "ollama")
    m.register_model("gpt-5.2", "openai")
    m.register_model("sonar-pro", "perplexity")
    return m


def test_register_and_stats():
    m = _m()
    s = m.stats()
    assert s["models"] == 3 and s["benchmarked"] == 0 and s["default"] is None


def test_benchmark_validation():
    m = _m()
    with pytest.raises(SynapticError):
        m.record_benchmark("qwen-1.5b", 1.5)
    with pytest.raises(SynapticError):
        m.record_benchmark("ghost", 0.5)


def test_evaluate_requires_default():
    m = _m()
    with pytest.raises(SynapticError):
        m.evaluate()


def test_evaluate_proposes_better_model():
    m = _m()
    m.record_benchmark("qwen-1.5b", 0.60)
    m.record_benchmark("gpt-5.2", 0.80)  # +33% over default
    m.record_benchmark("sonar-pro", 0.61)  # +1.7% -> below margin
    m.set_default("qwen-1.5b")
    ev = m.evaluate()
    names = [p["model"] for p in ev["proposals"]]
    assert names == ["gpt-5.2"]  # only the one beating default by >5%
    assert ev["recommended"] == "gpt-5.2"
    assert ev["proposals"][0]["improvement"] > UPGRADE_MARGIN


def test_evaluate_no_proposal_when_default_best():
    m = _m()
    m.record_benchmark("qwen-1.5b", 0.90)
    m.record_benchmark("gpt-5.2", 0.85)
    m.set_default("qwen-1.5b")
    ev = m.evaluate()
    assert ev["proposals"] == [] and ev["recommended"] is None


def test_proposals_sorted_by_improvement():
    m = _m()
    m.record_benchmark("qwen-1.5b", 0.50)
    m.record_benchmark("gpt-5.2", 0.90)  # +80%
    m.record_benchmark("sonar-pro", 0.70)  # +40%
    m.set_default("qwen-1.5b")
    ev = m.evaluate()
    assert [p["model"] for p in ev["proposals"]] == ["gpt-5.2", "sonar-pro"]


def test_promote_swaps_default():
    m = _m()
    m.record_benchmark("qwen-1.5b", 0.50)
    m.record_benchmark("gpt-5.2", 0.90)
    m.set_default("qwen-1.5b")
    m.promote("gpt-5.2")
    ev = m.evaluate()
    assert ev["default"] == "gpt-5.2" and ev["proposals"] == []


def test_promote_unknown_raises():
    with pytest.raises(SynapticError):
        _m().promote("nope")


def test_reset():
    m = _m()
    m.set_default("gpt-5.2")
    m.reset()
    assert m.stats()["models"] == 0 and m.stats()["default"] is None
