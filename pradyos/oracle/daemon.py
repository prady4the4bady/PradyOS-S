"""ORACLE daemon — async main loop.

Registers ORACLE as an IMPERIUM handler for task kinds:
    'research'          — background intelligence gathering
    'oracle.plan'       — explicit planning request from Throne/campaign
    'oracle.check'      — connectivity / status check

Also exposes a lightweight HTTP status endpoint at /oracle/status
(TCP only, no AF_UNIX) for Throne polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from pradyos.core.audit import get_audit_log
from pradyos.core.bus import get_bus
from pradyos.oracle.oracle import Oracle

log = logging.getLogger("pradyos.oracle.daemon")

DEFAULT_PORT = int(os.environ.get("PRADYOS_ORACLE_PORT", "11435"))
DEFAULT_BASE_URL = os.environ.get("PRADYOS_OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("PRADYOS_ORACLE_MODEL", "qwen2.5:7b")

# ---------------------------------------------------------------------------
# HTTP status server
# ---------------------------------------------------------------------------

_oracle_ref: Oracle | None = None


class _OracleHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
        pass

    def do_GET(self) -> None:
        if self.path.rstrip("/") not in ("/oracle/status", "/status", ""):
            self.send_response(404)
            self.end_headers()
            return

        if _oracle_ref is None:
            payload = {"status": "starting"}
        else:
            try:
                loop = asyncio.new_event_loop()
                status = loop.run_until_complete(_oracle_ref.check_ollama())
                loop.close()
            except Exception as e:  # noqa: BLE001
                status = {"error": str(e)}
            payload = {
                "status": "running",
                "ollama": status,
            }

        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_http_server(port: int) -> None:
    """Start the Oracle HTTP status server in a background thread."""
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), _OracleHandler)
        t = Thread(target=srv.serve_forever, daemon=True, name="oracle-http")
        t.start()
        log.info("ORACLE status endpoint: http://127.0.0.1:%d/oracle/status", port)
    except OSError as e:
        log.warning("ORACLE HTTP server failed to start (port %d): %s", port, e)


# ---------------------------------------------------------------------------
# Daemon entry point
# ---------------------------------------------------------------------------


async def run_daemon(
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    port: int = DEFAULT_PORT,
    memory_store: Any | None = None,
    register_with_imperium: bool = True,
) -> None:
    """Run the ORACLE daemon until cancelled."""
    global _oracle_ref

    audit = get_audit_log()
    bus = get_bus()

    oracle = Oracle(base_url=base_url, model=model, memory_store=memory_store, bus=bus)
    _oracle_ref = oracle

    # Status endpoint
    _start_http_server(port)

    # Register handlers with IMPERIUM if it's running in-process
    if register_with_imperium:
        _try_register_imperium(oracle)

    # Connectivity check on startup
    status = await oracle.check_ollama()
    if status["alive"]:
        log.info(
            "ORACLE online — Ollama at %s, model=%s, available=%s",
            status["base_url"],
            status["model"],
            status["available_models"],
        )
        audit.log("oracle.started", {
            "ollama_url": base_url,
            "model": model,
            "available_models": status["available_models"],
        }, agent_id="oracle")
    else:
        log.warning(
            "ORACLE started but Ollama is NOT reachable at %s — "
            "planning will fail until Ollama is available.",
            base_url,
        )
        audit.log("oracle.started_degraded", {"ollama_url": base_url}, agent_id="oracle")

    # Subscribe to bus events
    bus.subscribe("imperium.task_queued", _on_task_queued)

    # Keep alive
    try:
        while True:
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        log.info("ORACLE daemon shutting down.")
        _oracle_ref = None


def _try_register_imperium(oracle: Oracle) -> None:
    """Attempt to register Oracle handlers with a running Imperium singleton."""
    try:
        from pradyos.imperium.kernel import Imperium  # noqa: PLC0415

        imp = Imperium._instance if hasattr(Imperium, "_instance") else None
        if imp is not None:
            imp.register_handler("research", oracle.imperium_handler)
            imp.register_handler("oracle.plan", oracle.imperium_handler)
            log.info("ORACLE registered as IMPERIUM handler for 'research' and 'oracle.plan'")
    except Exception as e:  # noqa: BLE001
        log.debug("IMPERIUM handler registration skipped: %s", e)


def _on_task_queued(topic: str, payload: dict[str, Any]) -> None:
    kind = payload.get("kind", "")
    if kind in ("research", "oracle.plan"):
        log.debug("ORACLE notified of queued task: %s", payload.get("task_id"))


def main() -> None:
    """CLI entry point: pradyos-oracle."""
    import click

    @click.command()
    @click.option("--ollama-url", default=DEFAULT_BASE_URL, help="Ollama base URL")
    @click.option("--model", default=DEFAULT_MODEL, help="Ollama model name")
    @click.option("--port", default=DEFAULT_PORT, type=int, help="Oracle HTTP port")
    @click.option("--debug", is_flag=True, help="Enable debug logging")
    def _cli(ollama_url: str, model: str, port: int, debug: bool) -> None:
        """Start the ORACLE AI reasoning daemon."""
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        )
        try:
            asyncio.run(run_daemon(base_url=ollama_url, model=model, port=port))
        except KeyboardInterrupt:
            pass

    _cli()


if __name__ == "__main__":
    main()
