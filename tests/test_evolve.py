"""EVOLVE tests — the composed self-improvement verdict verified deterministically."""

from __future__ import annotations

import pytest

from pradyos.evolve import EvolveEngine, EvolveError, OllamaProposer

# before: a bare-except weakness (FORTIFY risk 3). after: fixed (risk 0).
_WEAK = "def f():\n    try:\n        g()\n    except:\n        pass\n"
_FIXED = "def f():\n    try:\n        g()\n    except ValueError:\n        log()\n"


def _e() -> EvolveEngine:
    return EvolveEngine()


def test_promote_when_safe_and_robustness_improves():
    d = _e().evaluate("pradyos/x.py", after=_FIXED, before=_WEAK)
    assert d["verdict"] == "promote"
    assert d["risk_before"] == 3 and d["risk_after"] == 0 and d["risk_delta"] == -3
    assert d["review_decision"] == "approve"


def test_promote_when_robustness_held():
    d = _e().evaluate(
        "pradyos/x.py", after="def f():\n    return 2\n", before="def f():\n    return 1\n"
    )
    assert d["verdict"] == "promote" and d["risk_delta"] == 0


def test_promote_new_file():
    d = _e().evaluate("pradyos/new.py", after="def helper():\n    return 1\n")
    assert d["verdict"] == "promote" and d["risk_before"] == 0


def test_revise_when_robustness_worsens():
    d = _e().evaluate(
        "pradyos/x.py", after="def f(x=[]):\n    return x\n", before="def f():\n    return 1\n"
    )
    assert d["verdict"] == "revise"  # review approves, but FORTIFY risk rose 0 → 3
    assert d["risk_after"] > d["risk_before"]


def test_reject_when_review_denies():
    d = _e().evaluate(
        "pradyos/x.py",
        after="def a():\n    pass\n",
        before="def a():\n    pass\n\n\ndef b():\n    pass\n",
    )
    assert d["verdict"] == "reject" and d["review_decision"] == "deny"


def test_escalate_on_forbidden_path():
    d = _e().evaluate("pradyos/core/constitution.py", after="x = 2\n", before="x = 1\n")
    assert d["verdict"] == "escalate" and d["review_decision"] == "escalate"


def test_evaluate_validation():
    e = _e()
    with pytest.raises(EvolveError):
        e.evaluate("", after="x = 1")
    with pytest.raises(EvolveError):
        e.evaluate("p", after=5)
    with pytest.raises(EvolveError):
        e.evaluate("p", after="x = 1", before=5)


def test_evaluation_retrieval_stats_reset():
    e = _e()
    e.evaluate("pradyos/a.py", after="def a():\n    return 1\n")  # promote
    e.evaluate("pradyos/core/constitution.py", after="z = 1\n")  # escalate
    assert e.evaluation(1)["verdict"] == "promote"
    assert len(e.evaluations()) == 2
    s = e.stats()
    assert (
        s["evaluations"] == 2
        and s["by_verdict"]["promote"] == 1
        and s["by_verdict"]["escalate"] == 1
    )
    with pytest.raises(EvolveError):
        e.evaluation(99)
    e.reset()
    assert e.stats()["evaluations"] == 0


def test_private_engines_are_isolated():
    # Two evaluations on the same path must not accumulate FORTIFY state.
    e = _e()
    e.evaluate("pradyos/x.py", after=_WEAK)
    d = e.evaluate("pradyos/x.py", after=_FIXED)
    assert d["fortify_after"]["risk"] == 0  # only reflects this call's 'after'


# ── propose: turn the judge into a doer (injected proposer) ────────────────────


def test_propose_generates_and_promotes_a_fix():
    # A proposer that fixes the bare-except weakness; EVOLVE judges its output.
    engine = EvolveEngine(proposer=lambda before, directive: _FIXED)
    d = engine.propose("pradyos/x.py", "replace the bare except", before=_WEAK)
    assert d["proposed"] is True
    assert d["after"] == _FIXED
    assert d["evaluation"]["verdict"] == "promote" and d["evaluation"]["risk_delta"] == -3


def test_propose_without_proposer_is_graceful():
    d = _e().propose("pradyos/x.py", "do something", before=_WEAK)
    assert d["proposed"] is False and "no code proposer" in d["note"]


def test_propose_proposer_failure_is_graceful():
    def _boom(before, directive):
        raise RuntimeError("ollama down")

    d = EvolveEngine(proposer=_boom).propose("pradyos/x.py", "fix it", before=_WEAK)
    assert d["proposed"] is False and "unavailable" in d["note"]


def test_propose_empty_output_is_graceful():
    d = EvolveEngine(proposer=lambda b, dve: "   ").propose("pradyos/x.py", "fix it")
    assert d["proposed"] is False and "no code" in d["note"]


def test_propose_validation():
    e = EvolveEngine(proposer=lambda b, d: "x = 1\n")
    with pytest.raises(EvolveError):
        e.propose("", "directive")
    with pytest.raises(EvolveError):
        e.propose("p", "")


def test_stats_reports_proposer_configured():
    assert _e().stats()["proposer_configured"] is False
    assert EvolveEngine(proposer=lambda b, d: "x").stats()["proposer_configured"] is True


def test_ollama_proposer_constructs_without_network():
    p = OllamaProposer(model="qwen2.5-coder:7b")
    assert p.name == "ollama" and callable(p) and p.model == "qwen2.5-coder:7b"
