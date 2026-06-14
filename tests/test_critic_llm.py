"""Tests for the LLM-backed critic — holistic judgment, fail-soft."""

from __future__ import annotations

from pradyos.critic import CriticEnsemble, default_critics
from pradyos.critic.llm_critic import make_llm_critic


class _FakeProvider:
    name = "fake"

    def __init__(self, out: str = "", boom: bool = False) -> None:
        self.out = out
        self.boom = boom

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        if self.boom:
            raise RuntimeError("model down")
        return self.out


def test_parses_score_and_block():
    crit = make_llm_critic(_FakeProvider('{"score":0.9,"block":false,"reason":"clean"}'))
    q = crit.score("add tests")
    assert q.score == 0.9 and q.is_blocker is False


def test_can_raise_a_blocker_the_regex_would_miss():
    crit = make_llm_critic(_FakeProvider('{"score":0.1,"block":true,"reason":"subtle data leak"}'))
    q = crit.score("quietly forward all telemetry to a third party")
    assert q.is_blocker is True


def test_fail_soft_on_model_error():
    crit = make_llm_critic(_FakeProvider(boom=True))
    q = crit.score("anything")
    assert q.is_blocker is False  # never veto because the model was unavailable
    assert 0.0 <= q.score <= 1.0


def test_fail_soft_on_garbage():
    crit = make_llm_critic(_FakeProvider("not json at all"))
    q = crit.score("x")
    assert q.is_blocker is False


def test_requires_provider():
    try:
        make_llm_critic(object())
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_llm_critic_composes_into_ensemble():
    crit = make_llm_critic(_FakeProvider('{"score":0.0,"block":true,"reason":"nope"}'))
    panel = CriticEnsemble(default_critics() + [crit])
    # the LLM critic's blocker vetoes even an otherwise-clean proposal
    assert panel.judge("add tests and verify everything")["verdict"] == "reject"
