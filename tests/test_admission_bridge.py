"""Tests for Phase 8B: OracleAdmissionBridge + AdmissionPipeline.admit_inline.

All tests are synchronous — the bridge's _on_proposal handler drives
asyncio.run() internally, so by the time bus.publish() returns every
downstream event has already been dispatched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from pradyos.core.bus import EventBus, reset_bus_for_tests
from pradyos.oracle.admission_bridge import OracleAdmissionBridge
from pradyos.proving_ground.pipeline import AdmissionPipeline
from pradyos.proving_ground.verdict import AdmissionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline() -> AdmissionPipeline:
    """Real AdmissionPipeline — admit_inline needs no external resources."""
    return AdmissionPipeline()


def _make_bridge(
    bus: EventBus,
    kernel: MagicMock | None = None,
    pipeline: AdmissionPipeline | None = None,
) -> OracleAdmissionBridge:
    audit = MagicMock()
    return OracleAdmissionBridge(
        pipeline=pipeline or _make_pipeline(),
        bus=bus,
        audit=audit,
        imperium_kernel=kernel,
    )


def _collect(bus: EventBus, topic: str) -> list[dict]:
    events: list[dict] = []
    bus.subscribe(topic, lambda _t, p: events.append(p))
    return events


# ---------------------------------------------------------------------------
# admit_inline unit tests (no bus needed)
# ---------------------------------------------------------------------------

def test_admit_inline_clean():
    p = _make_pipeline()
    v = p.admit_inline("prune old logs", "shell")
    assert v.status is AdmissionStatus.ADMITTED


def test_admit_inline_hard_violation():
    p = _make_pipeline()
    v = p.admit_inline("rm -rf /", "shell")
    assert v.status is AdmissionStatus.REJECTED


def test_admit_inline_soft_violation():
    p = _make_pipeline()
    v = p.admit_inline("eval(x)", "shell")
    assert v.status is AdmissionStatus.QUARANTINED


def test_admit_inline_drop_table_rejected():
    p = _make_pipeline()
    v = p.admit_inline("DROP TABLE users", "shell")
    assert v.status is AdmissionStatus.REJECTED


def test_admit_inline_returns_verdict_with_reason():
    p = _make_pipeline()
    v = p.admit_inline("prune old logs", "shell")
    assert v.reason != ""
    assert v.repo_url.startswith("inline://")


# ---------------------------------------------------------------------------
# Bridge integration tests
# ---------------------------------------------------------------------------

def test_admitted_proposal_submits_to_imperium():
    """Clean proposal + kernel → kernel.submit called once."""
    bus = reset_bus_for_tests()
    kernel = MagicMock()
    _make_bridge(bus, kernel=kernel)

    bus.publish("oracle.proposal", {"intent": "prune logs", "kind": "shell"})

    kernel.submit.assert_called_once()
    submitted_task = kernel.submit.call_args[0][0]
    assert submitted_task.intent == "prune logs"
    assert submitted_task.kind == "shell"
    assert submitted_task.submitted_by == "oracle.admission_bridge"


def test_bridge_no_kernel_publishes_admitted():
    """Clean proposal without kernel → oracle.proposal.admitted published."""
    bus = reset_bus_for_tests()
    admitted = _collect(bus, "oracle.proposal.admitted")
    _make_bridge(bus, kernel=None)

    bus.publish("oracle.proposal", {"intent": "prune logs", "kind": "shell"})

    assert len(admitted) == 1
    assert admitted[0]["intent"] == "prune logs"


def test_quarantined_proposal_publishes_event():
    """Intent containing eval() → oracle.proposal.quarantined."""
    bus = reset_bus_for_tests()
    quarantined = _collect(bus, "oracle.proposal.quarantined")
    _make_bridge(bus)

    bus.publish("oracle.proposal", {"intent": "eval(user_input)", "kind": "shell"})

    assert len(quarantined) == 1
    assert quarantined[0]["intent"] == "eval(user_input)"
    assert "reason" in quarantined[0]


def test_rejected_proposal_publishes_event():
    """rm -rf / intent → oracle.proposal.rejected."""
    bus = reset_bus_for_tests()
    rejected = _collect(bus, "oracle.proposal.rejected")
    _make_bridge(bus)

    bus.publish("oracle.proposal", {"intent": "rm -rf /", "kind": "shell"})

    assert len(rejected) == 1
    assert rejected[0]["intent"] == "rm -rf /"
    assert "reason" in rejected[0]


def test_rejected_proposal_logs_to_audit():
    """Rejected proposals must be written to the audit log."""
    bus = reset_bus_for_tests()
    audit = MagicMock()
    OracleAdmissionBridge(
        pipeline=_make_pipeline(), bus=bus, audit=audit, imperium_kernel=None
    )

    bus.publish("oracle.proposal", {"intent": "rm -rf /", "kind": "shell"})

    assert audit.record.called
    call_kwargs = audit.record.call_args.kwargs
    assert call_kwargs["kind"] == "oracle.proposal_rejected"


def test_bridge_uses_default_intent_and_kind():
    """Missing keys in payload → defaults 'autonomous' / 'shell' used."""
    bus = reset_bus_for_tests()
    admitted = _collect(bus, "oracle.proposal.admitted")
    _make_bridge(bus, kernel=None)

    bus.publish("oracle.proposal", {})  # empty payload

    # 'autonomous' + 'shell' is clean → admitted
    assert len(admitted) == 1
    assert admitted[0]["intent"] == "autonomous"
