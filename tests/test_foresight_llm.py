"""Tests for FORESIGHT L2 — the LLM-backed world-model (fail-soft to heuristic)."""

from __future__ import annotations

from pradyos.foresight import ForesightEngine
from pradyos.foresight.llm_model import LLMPredictor, make_llm_world_model


class _FakeProvider:
    name = "fake"

    def __init__(self, out: str = "", boom: bool = False) -> None:
        self.out = out
        self.boom = boom
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        self.prompts.append(prompt)
        if self.boom:
            raise RuntimeError("model down")
        return self.out


def test_parses_clean_json():
    p = LLMPredictor(_FakeProvider('{"value":0.8,"confidence":0.7,"rationale":"likely"}'))
    pred = p("deploy", "ship", (0.0, 0))
    assert pred.expected_value == 0.8
    assert pred.confidence == 0.7
    assert "likely" in pred.rationale


def test_extracts_json_from_prose_and_fences():
    p = LLMPredictor(_FakeProvider('Sure!\n```json\n{"value":0.6,"confidence":0.5}\n```'))
    pred = p("s", "a", (0.0, 0))
    assert pred.expected_value == 0.6


def test_clamps_out_of_range_values():
    p = LLMPredictor(_FakeProvider('{"value":9,"confidence":-3}'))
    pred = p("s", "a", (0.0, 0))
    assert pred.expected_value == 1.0
    assert pred.confidence == 0.0


def test_falls_back_to_heuristic_on_garbage():
    # no JSON at all → use the prior-anchored heuristic (prior mean 0.9 over 5)
    p = LLMPredictor(_FakeProvider("I cannot help with that."))
    pred = p("s", "a", (0.9, 5))
    assert pred.expected_value > 0.7  # anchored to the strong prior, not 0.5


def test_falls_back_when_provider_raises():
    p = LLMPredictor(_FakeProvider(boom=True))
    pred = p("s", "a", (0.0, 0))
    assert pred.expected_value == 0.5  # neutral fallback, no prior


def test_predictor_requires_a_provider():
    try:
        LLMPredictor(object())
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_engine_uses_llm_world_model():
    fake = _FakeProvider('{"value":0.95,"confidence":0.9,"rationale":"strong"}')
    eng = ForesightEngine(world_model=make_llm_world_model(fake))
    decision = eng.deliberate("novel state never seen", ["bold-move"])
    assert decision["ranked"][0]["expected_value"] == 0.95
    assert fake.prompts  # the model was actually consulted
