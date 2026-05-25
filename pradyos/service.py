"""``pradyos.service`` — boots all Phase 0 planes in one process.

This is the dev-friendly single-process bring-up. Production deploys
break these into separate systemd units (see ``deploy/systemd``).

Layout:

    TITAN OPS daemon  → background thread
    WARDEN GRID       → background thread + HTTP API
    IMPERIUM kernel   → worker threads
    AURORA THRONE     → foreground (the only Sovereign-visible surface)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from pradyos.aurora_throne.app import Throne  # Rich fallback (--once mode)
from pradyos.aurora_throne.textual_app import ThroneApp  # Textual cinematic UI
from pradyos.core.audit import get_audit_log
from pradyos.core.bus import get_bus
from pradyos.imperium.kernel import Imperium
from pradyos.titan_ops.daemon import TitanDaemon
from pradyos.warden_grid.monitor import WardenMonitor

log = logging.getLogger("pradyos.service")


def _ensure_state_dirs() -> None:
    root = Path(__file__).resolve().parents[1]
    (root / "var" / "log").mkdir(parents=True, exist_ok=True)
    (root / "var" / "state").mkdir(parents=True, exist_ok=True)


def boot(headless: bool = False, throne_once: bool = False) -> int:
    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    _ensure_state_dirs()

    audit = get_audit_log()
    bus = get_bus()
    log.info("PRADY OS service boot — audit ledger at %s", audit.path)

    # --- TITAN OPS daemon (thread) ---
    titan_socket = os.environ.setdefault(
        "PRADYOS_TITAN_SOCKET",
        str(Path(__file__).resolve().parents[1] / "var" / "state" / "titan.sock"),
    )
    titan = TitanDaemon(socket_path=titan_socket)
    t_titan = threading.Thread(target=titan.serve_forever, name="titan-daemon", daemon=True)
    t_titan.start()
    log.info("TITAN OPS daemon thread started")

    # --- WARDEN GRID (thread + HTTP) ---
    warden = WardenMonitor()
    warden.start()
    log.info("WARDEN GRID monitor started")

    # --- IMPERIUM kernel ---
    imperium = Imperium()
    imperium.start()
    log.info("IMPERIUM kernel started")

    # --- Sovereign incident hook: when WARDEN raises CRIT/FATAL, log to audit ---
    def _on_incident(topic: str, payload):
        log.warning("WARDEN incident: [%s] %s", payload.get("severity"), payload.get("summary"))

    bus.subscribe("warden.incident", _on_incident)

    # --- Throne ---
    if headless:
        log.info("Service running headless. Send SIGINT to stop.")
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        try:
            while not stop.is_set():
                stop.wait(60)
        finally:
            imperium.stop()
            warden.stop()
            titan.shutdown()
        return 0

    if throne_once:
        # Rich fallback for --once (CI/smoke tests)
        throne = Throne(imperium=imperium, audit=audit)
        try:
            throne.run(once=True)
        finally:
            imperium.stop()
            warden.stop()
            titan.shutdown()
            time.sleep(0.1)
        return 0

    # Full Textual cinematic UI
    app = ThroneApp(imperium=imperium, audit=audit, refresh_hz=2.0)
    try:
        app.run()
    finally:
        imperium.stop()
        warden.stop()
        titan.shutdown()
        time.sleep(0.1)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pradyos",
        description="PRADY OS — boot all Phase 0 planes in one process.",
    )
    parser.add_argument("--headless", action="store_true",
                        help="do not render the Throne; run all daemons in background")
    parser.add_argument("--once", action="store_true",
                        help="render the Throne once and exit (dev/CI only, uses Rich fallback)")
    args = parser.parse_args(argv)
    return boot(headless=args.headless, throne_once=args.once)


if __name__ == "__main__":
    sys.exit(main())
