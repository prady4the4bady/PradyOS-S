"""FORTIFY tests — robustness-weakness detection verified against known source."""

from __future__ import annotations

import pytest

from pradyos.fortify import RULES, FortifyEngine, FortifyError

WEAK = """\
def f(items=[]):
    try:
        risky()
    except Exception:
        pass
    while True:
        items.append(1)
    assert items  # FIXME later
"""


def _e() -> FortifyEngine:
    return FortifyEngine()


def _rules(report) -> set[str]:
    return {f["rule"] for f in report["findings"]}


# ── detection ─────────────────────────────────────────────────────────────────


def test_audit_detects_all_weaknesses():
    r = _e().audit("demo", WEAK)
    assert _rules(r) == {
        "mutable_default",
        "swallowed_error",
        "infinite_loop",
        "assert_validation",
        "debt_marker",
    }
    assert r["by_severity"] == {"high": 1, "medium": 2, "low": 2}
    assert r["risk"] == 9  # 3 + 2 + 2 + 1 + 1


def test_findings_sorted_severity_then_line():
    findings = _e().audit("demo", WEAK)["findings"]
    assert findings[0]["rule"] == "mutable_default" and findings[0]["severity"] == "high"
    severities = [f["severity"] for f in findings]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])


def test_bare_except_is_high():
    r = _e().audit("m", "try:\n    x()\nexcept:\n    pass\n")
    bare = [f for f in r["findings"] if f["rule"] == "bare_except"]
    assert len(bare) == 1 and bare[0]["severity"] == "high"


def test_mutable_default_variants():
    src = "def a(x=[]):\n    return x\n\n\ndef b(y={}):\n    return y\n\n\ndef c(z=set()):\n    return z\n"
    r = _e().audit("m", src)
    assert len([f for f in r["findings"] if f["rule"] == "mutable_default"]) == 3


def test_clean_source_has_no_findings():
    r = _e().audit("m", "def f(x):\n    return x + 1\n")
    assert r["findings"] == [] and r["risk"] == 0


def test_while_true_with_break_is_ok():
    r = _e().audit("m", "def f():\n    while True:\n        if done():\n            break\n")
    assert not any(f["rule"] == "infinite_loop" for f in r["findings"])


def test_parse_error_is_reported_not_raised():
    r = _e().audit("m", "def (:\n")
    assert any(f["rule"] == "parse_error" and f["severity"] == "high" for f in r["findings"])


# ── validation / introspection ────────────────────────────────────────────────


def test_audit_validation():
    e = _e()
    with pytest.raises(FortifyError):
        e.audit("", "x = 1")
    with pytest.raises(FortifyError):
        e.audit("m", 123)


def test_report_retrieval_and_unknown():
    e = _e()
    e.audit("mod.a", WEAK)
    assert e.report("mod.a")["module"] == "mod.a"
    assert len(e.reports()) == 1
    with pytest.raises(FortifyError):
        e.report("ghost")


def test_rules_catalogue_exposed():
    rules = _e().rules()
    assert rules == RULES
    assert rules["bare_except"]["severity"] == "high"


def test_stats_and_reset():
    e = _e()
    e.audit("mod.a", WEAK)
    s = e.stats()
    assert s["modules"] == 1 and s["total_findings"] == 5 and s["total_risk"] == 9
    e.reset()
    assert e.stats()["modules"] == 0
