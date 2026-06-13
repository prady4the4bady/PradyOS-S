"""Tests for the ASCENT applier — the gated, staged, re-gated write path."""

from __future__ import annotations

import pytest

from pradyos.ascent import AscentApplier, AscentError


def _applier(tmp_path, audit=None):
    return AscentApplier(
        apply_root=tmp_path / "applied",
        source_root=tmp_path / "src",
        audit=audit,
    )


def test_apply_stages_new_module(tmp_path):
    res = _applier(tmp_path).apply("pradyos/new.py", "def f():\n    return 1\n")
    assert res["applied"] is True and res["gate_decision"] in ("approve", "revise")
    staged = tmp_path / "applied" / "pradyos" / "new.py"
    assert staged.is_file() and staged.read_text() == "def f():\n    return 1\n"
    assert res["path"] == str(staged) and res["bytes"] > 0


def test_apply_never_touches_source_root(tmp_path):
    # The live source tree must be untouched — apply only writes under apply_root.
    src = tmp_path / "src" / "pradyos"
    src.mkdir(parents=True)
    (src / "live.py").write_text("ORIGINAL = 1\n")
    _applier(tmp_path).apply("pradyos/live.py", "ORIGINAL = 2\n")
    assert (src / "live.py").read_text() == "ORIGINAL = 1\n"  # unchanged
    assert (tmp_path / "applied" / "pradyos" / "live.py").read_text() == "ORIGINAL = 2\n"


def test_apply_refuses_when_change_drops_public_api(tmp_path):
    src = tmp_path / "src" / "pradyos"
    src.mkdir(parents=True)
    (src / "m.py").write_text("def keep():\n    pass\n\n\ndef drop():\n    pass\n")
    res = _applier(tmp_path).apply("pradyos/m.py", "def keep():\n    pass\n")  # drops 'drop'
    assert res["applied"] is False and res["gate_decision"] == "deny"
    assert not (tmp_path / "applied" / "pradyos" / "m.py").exists()  # nothing written


def test_apply_refuses_forbidden_constitutional_path(tmp_path):
    res = _applier(tmp_path).apply("pradyos/core/constitution.py", "x = 1\n")
    assert res["applied"] is False and res["gate_decision"] == "escalate"


def test_apply_refuses_broken_parse(tmp_path):
    res = _applier(tmp_path).apply("pradyos/broken.py", "def f(:\n    pass\n")
    assert res["applied"] is False and res["gate_decision"] == "deny"


def test_apply_rejects_path_traversal(tmp_path):
    with pytest.raises(AscentError, match="unsafe"):
        _applier(tmp_path).apply("../../etc/evil.py", "x = 1\n")


def test_read_current_reads_source_and_missing_is_empty(tmp_path):
    src = tmp_path / "src" / "pradyos"
    src.mkdir(parents=True)
    (src / "r.py").write_text("X = 9\n")
    ap = _applier(tmp_path)
    assert ap.read_current("pradyos/r.py") == "X = 9\n"
    assert ap.read_current("pradyos/missing.py") == ""
    assert ap.read_current("../../../etc/passwd") == ""  # traversal → empty, no read


def test_apply_records_to_audit(tmp_path):
    events = []

    class _Audit:
        def record(self, agent_id, kind, summary, detail=None, exit_code=None):
            events.append((agent_id, kind, exit_code))

    _applier(tmp_path, audit=_Audit()).apply("pradyos/n.py", "x = 1\n")
    assert events == [("ascent", "ascent.apply", 0)]


def test_apply_validation(tmp_path):
    ap = _applier(tmp_path)
    with pytest.raises(AscentError):
        ap.apply("", "x = 1\n")
    with pytest.raises(AscentError):
        ap.apply("pradyos/x.py", 5)
