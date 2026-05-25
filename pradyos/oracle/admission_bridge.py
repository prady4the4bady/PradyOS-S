"""
OracleAdmissionBridge — routes ORACLE-proposed campaigns through the
Proving Ground before IMPERIUM queues them for execution.

Flow:
  oracle.proposal (bus event)
      → AdmissionPipeline.admit_inline(intent, kind)
          → ADMITTED    → submit ImperiumTask  (or publish oracle.proposal.admitted)
          → QUARANTINED → publish oracle.proposal.quarantined  (Throne review)
          → REJECTED    → publish oracle.proposal.rejected + audit log

Standalone daemon entry point: ``pradyos-admission`` (see :func:`main`).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from pradyos.core.bus import EventBus
from pradyos.imperium.task import ImperiumTask
from pradyos.proving_ground.pipeline import AdmissionPipeline
from pradyos.proving_ground.verdict import AdmissionStatus, AdmissionVerdict

log = logging.getLogger("pradyos.oracle.admission_bridge")


class OracleAdmissionBridge:
    """Subscribes to ``oracle.proposal`` events and runs them through the
    Proving Ground's inline constitutional scan before they reach IMPERIUM.

    Parameters
    ----------
    pipeline:
        An :class:`AdmissionPipeline` instance (must have ``admit_inline``).
    bus:
        The shared :class:`EventBus`.
    audit:
        An audit log object with a ``record()`` method (AuditLog) or
        ``append()`` method (EventAuditLog) — duck-typed.
    imperium_kernel:
        Optional IMPERIUM kernel.  When supplied, admitted proposals are
        submitted via ``kernel.submit(ImperiumTask(...))``.  When ``None``,
        admitted proposals are published as ``oracle.proposal.admitted``.
    """

    def __init__(
        self,
        pipeline: AdmissionPipeline,
        bus: EventBus,
        audit: Any,
        imperium_kernel: Any | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._bus = bus
        self._audit = audit
        self._kernel = imperium_kernel

        bus.subscribe("oracle.proposal", self._on_proposal)
        log.info("OracleAdmissionBridge subscribed to oracle.proposal")

    # ------------------------------------------------------------------
    # Synchronous bus handler
    # ------------------------------------------------------------------

    def _on_proposal(self, topic: str, payload: dict) -> None:
        """Synchronous bus callback — bridges into async admit logic."""
        try:
            loop = asyncio.get_running_loop()
            # Already inside an async context — schedule without blocking
            asyncio.ensure_future(self._admit_async(payload), loop=loop)
        except RuntimeError:
            # No running event loop — run synchronously via a fresh loop
            asyncio.run(self._admit_async(payload))

    # ------------------------------------------------------------------
    # Async admission logic
    # ------------------------------------------------------------------

    async def _admit_async(self, payload: dict) -> None:
        """Run the inline constitutional scan and act on the verdict."""
        intent: str = payload.get("intent", "autonomous")
        kind: str = payload.get("kind", "shell")

        try:
            verdict: AdmissionVerdict = await asyncio.to_thread(
                self._pipeline.admit_inline, intent, kind
            )
        except Exception as exc:  # noqa: BLE001
            log.error("admit_inline raised unexpectedly: %s", exc)
            self._bus.publish(
                "oracle.proposal.quarantined",
                {"intent": intent, "kind": kind, "reason": f"admission error: {exc}"},
            )
            return

        if verdict.status is AdmissionStatus.ADMITTED:
            log.info("OracleAdmissionBridge: ADMITTED — %s (%s)", intent, kind)
            if self._kernel is not None:
                task = ImperiumTask(
                    kind=kind,
                    intent=intent,
                    submitted_by="oracle.admission_bridge",
                )
                self._kernel.submit(task)
            else:
                self._bus.publish(
                    "oracle.proposal.admitted",
                    {"intent": intent, "kind": kind, "reason": verdict.reason},
                )

        elif verdict.status is AdmissionStatus.QUARANTINED:
            log.warning("OracleAdmissionBridge: QUARANTINED — %s: %s", intent, verdict.reason)
            self._bus.publish(
                "oracle.proposal.quarantined",
                {"intent": intent, "kind": kind, "reason": verdict.reason},
            )

        elif verdict.status is AdmissionStatus.REJECTED:
            log.error("OracleAdmissionBridge: REJECTED — %s: %s", intent, verdict.reason)
            self._bus.publish(
                "oracle.proposal.rejected",
                {"intent": intent, "kind": kind, "reason": verdict.reason},
            )
            self._log_audit(
                "oracle.proposal_rejected",
                {"intent": intent, "kind": kind, "reason": verdict.reason},
            )

    # ------------------------------------------------------------------
    # Audit helper (duck-typed for AuditLog and EventAuditLog)
    # ------------------------------------------------------------------

    def _log_audit(self, action: str, detail: dict) -> None:
        """Write to audit log using whichever interface is available."""
        if hasattr(self._audit, "record"):
            self._audit.record(
                agent_id="oracle.admission_bridge",
                kind=action,
                summary=action,
                detail=detail,
            )
        elif hasattr(self._audit, "append"):
            from pradyos.core.audit import AuditEvent, AuditCategory  # noqa: PLC0415
            self._audit.append(
                AuditEvent(
                    category=AuditCategory.ORACLE,
                    actor="oracle.admission_bridge",
                    action=action,
                    payload=detail,
                )
            )


# ---------------------------------------------------------------------------
# Standalone daemon
# ---------------------------------------------------------------------------

async def _run_admission_daemon(debug: bool = False) -> None:
    """Instantiate the bridge and block until SIGTERM / SIGINT."""
    from pradyos.core.audit import get_audit_log  # noqa: PLC0415
    from pradyos.core.bus import get_bus  # noqa: PLC0415
    from pradyos.proving_ground.pipeline import AdmissionPipeline  # noqa: PLC0415

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stderr,
    )

    bus = get_bus()
    audit = get_audit_log()
    pipeline = AdmissionPipeline()

    # Instantiation auto-subscribes to oracle.proposal on the shared bus.
    bridge = OracleAdmissionBridge(pipeline=pipeline, bus=bus, audit=audit)  # noqa: F841
    log.info("Admission Bridge daemon running — awaiting oracle.proposal events.")

    # Notify systemd readiness if sd_notify is available.
    try:
        import sdnotify  # type: ignore[import-untyped]  # noqa: PLC0415

        sdnotify.SystemdNotifier().notify("READY=1")
    except Exception:  # noqa: BLE001
        pass

    # Block until cancelled by signal.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    log.info("Admission Bridge daemon stopping.")


def main() -> None:
    """CLI entry point: ``pradyos-admission``."""
    import click  # noqa: PLC0415

    @click.command()
    @click.option("--debug", is_flag=True, help="Enable DEBUG logging.")
    def _cli(debug: bool) -> None:
        """Run the ORACLE Admission Bridge as a standalone daemon."""
        asyncio.run(_run_admission_daemon(debug=debug))

    _cli()
