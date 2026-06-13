"""Tests for the ASCENT plane — the autonomous self-improvement loop.

The survey/direct/decide core is deterministic, so it is checked against
hand-computed FORTIFY risk and verdict→decision mappings. EVOLVE is replaced by
a fake so the loop is exercised without a live LLM.
"""

from __future__ import annotations

import threading

import pytest

from pradyos.ascent import AscentError, AscentLoop

# ── source fixtures with known FORTIFY risk ────────────────────────────────────
# bare_except (high, weight 3) → risk 3, one finding.
WEAK_HIGH = "def f():\n    try:\n        g()\n    except:\n        pass\n"
# mutable_default (high) + bare_except (high) + TODO (low) → risk 3+3+1 = 7.
WEAK_HIGHER = "def f(a=[]):  # TODO: fix\n    try:\n        g()\n    except:\n        pass\n"
# no findings → risk 0.
CLEAN = "x = 1\n"


class _FakeEvolve:
    """Stand-in for EvolveEngine: records calls, returns a fixed gated verdict."""

    def __init__(
        self,
        verdict: str = "promote",
        proposed: bool = True,
        proposer_configured: bool = True,
        note: str = "stub note",
    ) -> None:
        self._verdict = verdict
        self._proposed = proposed
        self._pc = proposer_configured
        self._note = note
        self.calls: list[tuple[str, str, str]] = []

    def propose(self, path: str, directive: str, before: str = "") -> dict:
        self.calls.append((path, directive, before))
        if not self._proposed:
            return {
                "path": path,
                "directive": directive,
                "proposed": False,
                "after": None,
                "evaluation": None,
                "note": self._note,
            }
        return {
            "path": path,
            "directive": directive,
            "proposed": True,
            "after": "x = 1\n",
            "evaluation": {
                "verdict": self._verdict,
                "risk_before": 3,
                "risk_after": 1,
                "path": path,
            },
            "note": f"verdict={self._verdict}",
        }

    def stats(self) -> dict:
        return {"proposer_configured": self._pc}


# ── survey + direct ────────────────────────────────────────────────────────────


def test_survey_ranks_by_risk_descending():
    loop = AscentLoop()
    out = loop.survey({"a.py": WEAK_HIGH, "b.py": WEAK_HIGHER, "c.py": CLEAN})
    assert [e["module"] for e in out] == ["b.py", "a.py", "c.py"]
    assert [e["risk"] for e in out] == [7, 3, 0]


def test_survey_tie_break_by_module_name():
    loop = AscentLoop()
    out = loop.survey({"z.py": WEAK_HIGH, "a.py": WEAK_HIGH})
    # equal risk → module name ascending
    assert [e["module"] for e in out] == ["a.py", "z.py"]


def test_survey_entry_shape_and_top_finding():
    loop = AscentLoop()
    [entry] = loop.survey({"m.py": WEAK_HIGH})
    assert entry["finding_count"] == 1
    assert entry["by_severity"] == {"high": 1}
    assert entry["top_finding"]["rule"] == "bare_except"
    assert entry["directive"].startswith("Harden bare_except at line 4:")


def test_survey_clean_module_has_no_directive():
    loop = AscentLoop()
    [entry] = loop.survey({"clean.py": CLEAN})
    assert entry["risk"] == 0 and entry["top_finding"] is None and entry["directive"] is None


def test_directive_picks_highest_severity_finding():
    loop = AscentLoop()
    [entry] = loop.survey({"m.py": WEAK_HIGHER})
    # mutable_default (high, line 1) outranks bare_except (high, line 3) and the TODO.
    assert "mutable_default at line 1" in entry["directive"]


@pytest.mark.parametrize(
    "bad",
    [{}, "notdict", {"": "x = 1\n"}, {"m.py": 5}],
)
def test_survey_validation_errors(bad):
    with pytest.raises(AscentError):
        AscentLoop().survey(bad)


# ── run_cycle without an EVOLVE engine ─────────────────────────────────────────


def test_run_cycle_no_evolve_identifies_target_only():
    loop = AscentLoop()
    [cyc] = loop.run_cycle({"a.py": WEAK_HIGH, "b.py": WEAK_HIGHER})
    assert cyc["module"] == "b.py"  # highest risk
    assert cyc["verdict"] == "skipped" and cyc["decision"] == "skipped"
    assert cyc["risk_before"] == 7 and cyc["risk_after"] is None
    assert "no EVOLVE engine" in cyc["rationale"]
    assert "mutable_default at line 1" in cyc["directive"]


def test_run_cycle_max_targets_two_targets_highest_first():
    loop = AscentLoop()
    cycles = loop.run_cycle({"a.py": WEAK_HIGH, "b.py": WEAK_HIGHER, "c.py": CLEAN}, max_targets=2)
    assert [c["module"] for c in cycles] == ["b.py", "a.py"]  # clean module excluded


def test_run_cycle_skips_modules_without_findings():
    loop = AscentLoop()
    cycles = loop.run_cycle({"clean.py": CLEAN, "a.py": WEAK_HIGH}, max_targets=10)
    assert [c["module"] for c in cycles] == ["a.py"]  # only the one with findings


# True/False are int subclasses — must be rejected, not read as 1/0.
@pytest.mark.parametrize("bad", [0, -1, "x", 1.5, True, False])
def test_run_cycle_max_targets_validation(bad):
    with pytest.raises(AscentError):
        AscentLoop().run_cycle({"a.py": WEAK_HIGH}, max_targets=bad)


# ── run_cycle with a fake EVOLVE: verdict → decision mapping ────────────────────


@pytest.mark.parametrize(
    "verdict,decision",
    [
        ("promote", "apply"),
        ("revise", "defer"),
        ("escalate", "escalate"),
        ("reject", "discard"),
    ],
)
def test_verdict_decision_mapping(verdict, decision):
    loop = AscentLoop(evolve=_FakeEvolve(verdict=verdict))
    [cyc] = loop.run_cycle({"a.py": WEAK_HIGH})
    assert cyc["verdict"] == verdict and cyc["decision"] == decision
    assert cyc["risk_after"] == 1 and cyc["evaluation"]["verdict"] == verdict


def test_promote_queues_pending_with_after_source():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    pend = loop.pending()
    assert len(pend) == 1
    assert pend[0]["module"] == "a.py" and pend[0]["after"] == "x = 1\n"


def test_non_apply_verdict_does_not_queue_pending():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="revise"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    assert loop.pending() == []


# ── Sovereign review (queue / resolve / decisions) ─────────────────────────────


def test_review_queue_mirrors_pending():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    assert loop.review_queue() == loop.pending()
    assert loop.review_queue()[0]["module"] == "a.py"


def test_resolve_approve_records_and_dequeues():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    seq = loop.pending()[0]["seq"]
    rec = loop.resolve(seq, "approve", by="sovereign")
    assert rec["status"] == "approved" and rec["by"] == "sovereign" and rec["after"] == "x = 1\n"
    assert loop.pending() == []  # dequeued
    assert loop.decisions()[-1]["seq"] == seq
    assert loop.stats()["decisions"] == 1


def test_resolve_reject_drops_without_apply():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    seq = loop.pending()[0]["seq"]
    rec = loop.resolve(seq, "REJECT")  # case-insensitive
    assert rec["status"] == "rejected"
    assert loop.pending() == [] and loop.decisions()[-1]["status"] == "rejected"


def test_resolve_unknown_seq_raises():
    loop = AscentLoop()
    with pytest.raises(AscentError, match="unknown"):
        loop.resolve(999, "approve")


@pytest.mark.parametrize("bad", ["", "maybe", "applied", None])
def test_resolve_bad_decision_raises(bad):
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    seq = loop.pending()[0]["seq"]
    with pytest.raises(AscentError):
        loop.resolve(seq, bad)


@pytest.mark.parametrize("bad", [True, "1", 1.0])
def test_resolve_bad_seq_type_raises(bad):
    with pytest.raises(AscentError, match="seq must be an integer"):
        AscentLoop().resolve(bad, "approve")


def test_resolve_twice_is_unknown_second_time():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    seq = loop.pending()[0]["seq"]
    loop.resolve(seq, "approve")
    with pytest.raises(AscentError, match="unknown"):
        loop.resolve(seq, "approve")


def test_decisions_limit_validation_and_reset_clears():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    loop.resolve(loop.pending()[0]["seq"], "approve")
    with pytest.raises(AscentError):
        loop.decisions(limit=0)
    loop.reset()
    assert loop.decisions() == [] and loop.stats()["decisions"] == 0


# ── apply-gate (loop ↔ applier) ────────────────────────────────────────────────


class _FakeApplier:
    def __init__(self, applied: bool = True, gate: str = "approve") -> None:
        self.calls: list[tuple[str, str]] = []
        self._applied = applied
        self._gate = gate

    def apply(self, module: str, after: str) -> dict:
        self.calls.append((module, after))
        return {
            "applied": self._applied,
            "module": module,
            "gate_decision": self._gate,
            "reason": "staged" if self._applied else "refused",
            "path": f"/staged/{module}" if self._applied else None,
            "bytes": len(after.encode("utf-8")) if self._applied else 0,
        }


def _approved_loop(applier):
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"), applier=applier)
    loop.run_cycle({"a.py": WEAK_HIGH})
    seq = loop.pending()[0]["seq"]
    loop.resolve(seq, "approve")
    return loop, seq


def test_apply_stages_approved_change_and_marks_decision():
    applier = _FakeApplier(applied=True)
    loop, seq = _approved_loop(applier)
    rec = loop.apply(seq)
    assert rec["applied"] is True and rec["module"] == "a.py" and rec["seq"] == seq
    assert applier.calls == [("a.py", "x = 1\n")]  # applier got the module + after
    assert loop.applied()[-1]["seq"] == seq
    assert loop.decisions()[-1]["status"] == "applied"
    assert loop.stats()["applied"] == 1 and loop.stats()["applier_configured"] is True


def test_apply_refused_marks_decision_apply_refused():
    loop, seq = _approved_loop(_FakeApplier(applied=False, gate="deny"))
    rec = loop.apply(seq)
    assert rec["applied"] is False and rec["gate_decision"] == "deny"
    assert loop.decisions()[-1]["status"] == "apply_refused"


def test_apply_without_applier_raises():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    loop.resolve(loop.pending()[0]["seq"], "approve")
    with pytest.raises(AscentError, match="no applier"):
        loop.apply(1)


def test_apply_unknown_or_unapproved_seq_raises():
    # a rejected (not approved) seq cannot be applied; an absent seq is unknown
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"), applier=_FakeApplier())
    loop.run_cycle({"a.py": WEAK_HIGH})
    loop.resolve(loop.pending()[0]["seq"], "reject")
    with pytest.raises(AscentError, match="not approved"):
        loop.apply(1)
    with pytest.raises(AscentError, match="unknown approved decision"):
        loop.apply(999)


def test_apply_twice_is_refused():
    loop, seq = _approved_loop(_FakeApplier(applied=True))
    loop.apply(seq)
    with pytest.raises(AscentError, match="already applied"):
        loop.apply(seq)


@pytest.mark.parametrize("bad", [True, "1", 1.5])
def test_apply_bad_seq_type_raises(bad):
    with pytest.raises(AscentError, match="seq must be an integer"):
        AscentLoop(applier=_FakeApplier()).apply(bad)


def test_applied_limit_validation_and_reset_clears():
    loop, seq = _approved_loop(_FakeApplier(applied=True))
    loop.apply(seq)
    with pytest.raises(AscentError):
        loop.applied(limit=0)
    loop.reset()
    assert loop.applied() == [] and loop.stats()["applied"] == 0


def test_proposer_unavailable_records_skip_with_note():
    loop = AscentLoop(evolve=_FakeEvolve(proposed=False, note="proposer unavailable"))
    [cyc] = loop.run_cycle({"a.py": WEAK_HIGH})
    assert cyc["verdict"] == "skipped" and cyc["decision"] == "skipped"
    assert cyc["rationale"] == "proposer unavailable"


def test_proposer_raising_records_skip_not_crash():
    # A raising/dead proposer must degrade to a recorded skip, never bubble out
    # (the web route only maps AscentError, so an escape would be a 500).
    class _RaisingEvolve:
        def propose(self, path: str, directive: str, before: str = "") -> dict:
            raise RuntimeError("llm offline")

        def stats(self) -> dict:
            return {"proposer_configured": True}

    loop = AscentLoop(evolve=_RaisingEvolve())
    [cyc] = loop.run_cycle({"a.py": WEAK_HIGH})
    assert cyc["verdict"] == "skipped" and cyc["decision"] == "skipped"
    assert cyc["rationale"] == "evolve proposer failed"


def test_evolve_called_with_target_directive_and_source():
    fake = _FakeEvolve(verdict="promote")
    loop = AscentLoop(evolve=fake)
    loop.run_cycle({"a.py": WEAK_HIGH})
    assert len(fake.calls) == 1
    path, directive, before = fake.calls[0]
    assert path == "a.py" and before == WEAK_HIGH
    assert directive.startswith("Harden bare_except at line 4:")


# ── introspection ──────────────────────────────────────────────────────────────


def test_cycle_roundtrip_and_unknown():
    loop = AscentLoop()
    loop.run_cycle({"a.py": WEAK_HIGH})
    assert loop.cycle(1)["seq"] == 1
    with pytest.raises(AscentError):
        loop.cycle(99)


def test_cycles_limit_and_validation():
    loop = AscentLoop()
    for _ in range(3):
        loop.run_cycle({"a.py": WEAK_HIGH})
    assert len(loop.cycles(limit=2)) == 2
    assert loop.cycles()[-1]["seq"] == 3
    with pytest.raises(AscentError):
        loop.cycles(limit=0)


def test_pending_limit_validation():
    with pytest.raises(AscentError):
        AscentLoop().pending(limit=-1)


def test_stats_counts_and_flags():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    loop.run_cycle({"b.py": WEAK_HIGHER})
    s = loop.stats()
    assert s["cycles"] == 2 and s["pending"] == 2
    assert s["by_verdict"]["promote"] == 2 and s["by_decision"]["apply"] == 2
    assert s["evolve_wired"] is True and s["proposer_configured"] is True


def test_stats_flags_without_evolve():
    s = AscentLoop().stats()
    assert s["evolve_wired"] is False and s["proposer_configured"] is False


def test_reset_clears_state():
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    loop.run_cycle({"a.py": WEAK_HIGH})
    loop.reset()
    s = loop.stats()
    assert s["cycles"] == 0 and s["pending"] == 0
    # seq restarts at 1 after reset
    [cyc] = loop.run_cycle({"a.py": WEAK_HIGH})
    assert cyc["seq"] == 1


# ── determinism + thread-safety ────────────────────────────────────────────────


def test_survey_is_deterministic():
    loop = AscentLoop()
    cand = {"a.py": WEAK_HIGH, "b.py": WEAK_HIGHER, "c.py": CLEAN}
    assert loop.survey(cand) == loop.survey(cand)


def test_concurrent_run_cycle_assigns_unique_sequential_seqs():
    loop = AscentLoop()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        loop.run_cycle({"a.py": WEAK_HIGH})

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    seqs = sorted(c["seq"] for c in loop.cycles(limit=100))
    assert seqs == list(range(1, 9))
    assert loop.stats()["cycles"] == 8


def test_concurrent_promote_cycles_queue_all_pending_without_loss():
    # Exercise the _queue_pending path (the second lock-guarded list) under
    # contention: every concurrent cycle promotes, so all must enqueue exactly once.
    loop = AscentLoop(evolve=_FakeEvolve(verdict="promote"))
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        loop.run_cycle({"a.py": WEAK_HIGH})

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    pend = loop.pending(limit=100)
    assert len(pend) == 8  # no lost or duplicated pending entries under contention
    assert sorted(p["seq"] for p in pend) == list(range(1, 9))
    assert loop.stats()["by_decision"]["apply"] == 8
