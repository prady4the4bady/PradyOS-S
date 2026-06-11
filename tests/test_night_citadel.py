"""NIGHT CITADEL tests — the self-improvement safety gates verified."""

from __future__ import annotations

import pytest

from pradyos.night_citadel import (
    GDI_THRESHOLD,
    REGRESSION_THRESHOLD,
    CitadelError,
    NightCitadel,
)


def _c() -> NightCitadel:
    return NightCitadel()


def _seed(nc: NightCitadel, cid="c", gdi=0.1, constraints=True, regression=0.0):
    nc.start_cycle(cid)
    nc.record_audit(cid, ["slow_task", "low_conf"])
    nc.add_candidate(cid, "tune_prompt", "oracle")
    nc.set_gdi(cid, gdi)
    nc.set_constraints_ok(cid, constraints)
    nc.set_regression(cid, regression)
    return cid


def test_start_in_auditing():
    m = _c().start_cycle("c")
    assert m["phase"] == "auditing" and m["promoted"] is False and m["halted"] is False


def test_start_dupe_raises():
    nc = _c()
    nc.start_cycle("c")
    with pytest.raises(CitadelError):
        nc.start_cycle("c")


def test_clean_cycle_promotes():
    nc = _c()
    cid = _seed(nc, gdi=0.1, constraints=True, regression=0.01)
    # auditing -> generating -> drift_check -> constraint_check -> regression_check -> staging -> promoted
    phases = []
    for _ in range(6):
        phases.append(nc.advance(cid)["phase"])
    assert phases[-1] == "promoted"
    m = nc.manifest(cid)
    assert m["promoted"] is True and m["halted"] is False


def test_drift_gate_halts():
    nc = _c()
    cid = _seed(nc, gdi=GDI_THRESHOLD + 0.1)
    # advance to drift_check then attempt to leave it
    nc.advance(cid)  # generating
    nc.advance(cid)  # drift_check
    m = nc.advance(cid)  # drift gate fails -> halted
    assert m["halted"] is True and "GDI" in m["halt_reason"]


def test_constraint_gate_halts():
    nc = _c()
    cid = _seed(nc, gdi=0.1, constraints=False)
    nc.advance(cid)  # generating
    nc.advance(cid)  # drift_check
    nc.advance(cid)  # constraint_check
    m = nc.advance(cid)  # constraint gate fails -> halted
    assert m["halted"] is True and "constraint" in m["halt_reason"].lower()


def test_regression_gate_halts():
    nc = _c()
    cid = _seed(nc, gdi=0.1, constraints=True, regression=REGRESSION_THRESHOLD + 0.05)
    for _ in range(4):  # auditing -> ... -> regression_check
        nc.advance(cid)
    m = nc.advance(cid)  # leaving regression_check: gate fails -> halted
    assert m["halted"] is True and "regression" in m["halt_reason"]


def test_no_candidates_blocks_drift():
    nc = _c()
    nc.start_cycle("c")
    nc.advance("c")  # generating
    with pytest.raises(CitadelError):
        nc.advance("c")  # -> drift_check requires a candidate


def test_missing_gdi_raises():
    nc = _c()
    nc.start_cycle("c")
    nc.add_candidate("c", "x")
    nc.advance("c")  # generating
    nc.advance("c")  # drift_check
    with pytest.raises(CitadelError):
        nc.advance("c")  # gdi not set


def test_manual_halt_and_terminal():
    nc = _c()
    nc.start_cycle("c")
    m = nc.halt("c", "operator stop")
    assert m["halted"] is True and m["halt_reason"] == "operator stop"
    with pytest.raises(CitadelError):
        nc.advance("c")


def test_validation_errors():
    nc = _c()
    nc.start_cycle("c")
    with pytest.raises(CitadelError):
        nc.record_audit("c", "notalist")
    with pytest.raises(CitadelError):
        nc.set_gdi("c", -1)
    with pytest.raises(CitadelError):
        nc.set_regression("c", -0.5)


def test_stats_and_reset():
    nc = _c()
    _seed(nc, "c1", gdi=0.1)
    _seed(nc, "c2", gdi=0.9)
    s = nc.stats()
    assert s["cycles"] == 2
    nc.reset()
    assert nc.stats()["cycles"] == 0 and nc.cycles() == []


def test_unknown_cycle_raises():
    with pytest.raises(CitadelError):
        _c().advance("nope")
