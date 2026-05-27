"""Phase 24C — 20 tests for HealthScorecard, ComponentScore, HealthReport."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.health_scorecard import (
    ComponentScore,
    HealthReport,
    HealthScorecard,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Initialisation
# ─────────────────────────────────────────────────────────────────────────────

def test_init_no_components():
    sc = HealthScorecard()
    report = sc.get_report()
    assert report.components == []


# ─────────────────────────────────────────────────────────────────────────────
# 2. Default report (no updates)
# ─────────────────────────────────────────────────────────────────────────────

def test_default_report_score():
    sc = HealthScorecard()
    assert sc.get_report().score == 100.0


def test_default_report_grade():
    sc = HealthScorecard()
    assert sc.get_report().grade == "A"


# ─────────────────────────────────────────────────────────────────────────────
# 3. update() sets component score
# ─────────────────────────────────────────────────────────────────────────────

def test_update_sets_score():
    sc = HealthScorecard()
    sc.update("cpu", 80.0)
    report = sc.get_report()
    assert len(report.components) == 1
    assert report.components[0].score == 80.0


def test_single_component_score_equals_report_score():
    sc = HealthScorecard()
    sc.update("memory", 65.0)
    assert sc.get_report().score == pytest.approx(65.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Grade boundaries
# ─────────────────────────────────────────────────────────────────────────────

def test_grade_A():
    sc = HealthScorecard()
    sc.update("x", 95.0)
    assert sc.get_report().grade == "A"


def test_grade_A_boundary():
    sc = HealthScorecard()
    sc.update("x", 90.0)
    assert sc.get_report().grade == "A"


def test_grade_B():
    sc = HealthScorecard()
    sc.update("x", 80.0)
    assert sc.get_report().grade == "B"


def test_grade_B_boundary():
    sc = HealthScorecard()
    sc.update("x", 75.0)
    assert sc.get_report().grade == "B"


def test_grade_C():
    sc = HealthScorecard()
    sc.update("x", 65.0)
    assert sc.get_report().grade == "C"


def test_grade_C_boundary():
    sc = HealthScorecard()
    sc.update("x", 60.0)
    assert sc.get_report().grade == "C"


def test_grade_D():
    sc = HealthScorecard()
    sc.update("x", 50.0)
    assert sc.get_report().grade == "D"


def test_grade_D_boundary():
    sc = HealthScorecard()
    sc.update("x", 40.0)
    assert sc.get_report().grade == "D"


def test_grade_F():
    sc = HealthScorecard()
    sc.update("x", 20.0)
    assert sc.get_report().grade == "F"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Clamping
# ─────────────────────────────────────────────────────────────────────────────

def test_clamp_negative_to_zero():
    sc = HealthScorecard()
    sc.update("bad", -10.0)
    assert sc.get_report().components[0].score == 0.0


def test_clamp_over_100():
    sc = HealthScorecard()
    sc.update("over", 150.0)
    assert sc.get_report().components[0].score == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Auto-register
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_register_unknown_component():
    sc = HealthScorecard()
    sc.update("new_comp", 70.0)
    report = sc.get_report()
    names = [c.name for c in report.components]
    assert "new_comp" in names


# ─────────────────────────────────────────────────────────────────────────────
# 7. Explicit register with weight
# ─────────────────────────────────────────────────────────────────────────────

def test_register_explicit_weight():
    sc = HealthScorecard()
    sc.register("critical", weight=3.0)
    sc.update("critical", 50.0)
    report = sc.get_report()
    assert report.components[0].weight == 3.0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Weighted average
# ─────────────────────────────────────────────────────────────────────────────

def test_weighted_average_two_components():
    sc = HealthScorecard()
    sc.register("a", weight=1.0)
    sc.register("b", weight=3.0)
    sc.update("a", 100.0)
    sc.update("b", 0.0)
    # weighted avg = (100*1 + 0*3) / 4 = 25.0
    assert sc.get_report().score == pytest.approx(25.0)


# ─────────────────────────────────────────────────────────────────────────────
# 9. reset()
# ─────────────────────────────────────────────────────────────────────────────

def test_reset_single_component():
    sc = HealthScorecard()
    sc.update("alpha", 80.0)
    sc.update("beta", 60.0)
    sc.reset("alpha")
    names = [c.name for c in sc.get_report().components]
    assert "alpha" not in names
    assert "beta" in names


def test_reset_all():
    sc = HealthScorecard()
    sc.update("x", 50.0)
    sc.update("y", 70.0)
    sc.reset()
    assert sc.get_report().components == []
    assert sc.get_report().score == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 10. to_dict()
# ─────────────────────────────────────────────────────────────────────────────

def test_component_score_to_dict_keys():
    cs = ComponentScore(name="cpu", score=75.0, weight=1.0, details={"foo": "bar"})
    d = cs.to_dict()
    assert set(d.keys()) >= {"name", "score", "weight", "details"}


def test_health_report_to_dict_keys():
    sc = HealthScorecard()
    sc.update("z", 80.0)
    d = sc.get_report().to_dict()
    assert set(d.keys()) >= {"score", "grade", "components", "timestamp"}


# ─────────────────────────────────────────────────────────────────────────────
# 11. details defaults to {}
# ─────────────────────────────────────────────────────────────────────────────

def test_details_defaults_empty_dict():
    sc = HealthScorecard()
    sc.update("no_details", 55.0)
    comp = sc.get_report().components[0]
    assert comp.details == {}


# ─────────────────────────────────────────────────────────────────────────────
# 12. Thread safety
# ─────────────────────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_updates():
    sc = HealthScorecard()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            sc.update(f"comp_{i}", float(i % 101))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread errors: {errors}"
    report = sc.get_report()
    assert len(report.components) == 50
