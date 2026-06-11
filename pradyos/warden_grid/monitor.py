"""WARDEN GRID monitor — telemetry collection, incident raising, JSON API.

Polls host telemetry on a fixed cadence, snapshots it, classifies against
``Thresholds``, and serves the result over HTTP at ``/health``,
``/incidents``, ``/services`` and ``/`` (combined snapshot).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psutil

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.warden_grid.incidents import (
    Incident,
    IncidentSeverity,
    IncidentStore,
)
from pradyos.warden_grid.thresholds import Thresholds

log = logging.getLogger("pradyos.warden_grid")

# ---------------------------------------------------------------------------
# Optional GPU probe (NVIDIA)
# ---------------------------------------------------------------------------

try:
    import pynvml  # type: ignore

    _HAS_NVML = True
except Exception:  # noqa: BLE001
    _HAS_NVML = False


# ---------------------------------------------------------------------------
# Health snapshot
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GpuInfo:
    index: int
    name: str
    util_percent: float
    mem_used_mb: float
    mem_total_mb: float
    temperature_c: float | None = None


@dataclass(slots=True)
class ServiceInfo:
    name: str
    pid: int | None
    running: bool
    cpu_percent: float | None = None
    memory_rss_mb: float | None = None


@dataclass(slots=True)
class HealthSnapshot:
    timestamp: float
    hostname: str
    platform: str
    uptime_sec: float
    cpu_percent: float
    cpu_count: int
    load_average: tuple[float, float, float] | None
    ram_percent: float
    ram_total_mb: float
    ram_used_mb: float
    swap_percent: float
    disk: list[dict[str, Any]]
    inode: list[dict[str, Any]]
    network_io: dict[str, int]
    process_count: int
    gpus: list[GpuInfo]
    services: list[ServiceInfo]
    has_nvml: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gpus"] = [asdict(g) for g in self.gpus]
        d["services"] = [asdict(s) for s in self.services]
        return d


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class WardenMonitor:
    """Polls telemetry, raises incidents, serves JSON.

    Thread-safe. Designed to run forever; ``stop()`` is cooperative.
    """

    AGENT_ID = "warden_grid"

    def __init__(
        self,
        thresholds: Thresholds | None = None,
        watched_services: Iterable[str] | None = None,
        audit: AuditLog | None = None,
        bus: EventBus | None = None,
        incident_store: IncidentStore | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.thresholds = thresholds or Thresholds()
        self.watched_services = list(
            watched_services or os.environ.get("PRADYOS_WATCHED_SERVICES", "").split(",")
        )
        self.watched_services = [s.strip() for s in self.watched_services if s.strip()]

        self.audit = audit or get_audit_log()
        self.bus = bus or get_bus()
        self.incidents = incident_store or IncidentStore()
        self.host = host or os.environ.get("PRADYOS_WARDEN_HOST", "127.0.0.1")
        self.port = int(port or int(os.environ.get("PRADYOS_WARDEN_PORT", "9701")))

        self._latest: HealthSnapshot | None = None
        self._snap_lock = threading.Lock()
        self._stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None

        # initialize NVML if available
        self._nvml_ok = False
        if _HAS_NVML:
            try:
                pynvml.nvmlInit()
                self._nvml_ok = True
            except Exception:  # noqa: BLE001
                self._nvml_ok = False

    # ---------- lifecycle ----------
    def start(self) -> None:
        self._stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="warden-poll", daemon=True
        )
        self._poll_thread.start()
        self._start_http()

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except OSError:
                pass
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2)
        if self._server_thread is not None:
            self._server_thread.join(timeout=2)
        if self._nvml_ok:
            try:
                pynvml.nvmlShutdown()
            except Exception:  # noqa: BLE001
                pass

    # ---------- introspection ----------
    def latest_snapshot(self) -> HealthSnapshot:
        with self._snap_lock:
            if self._latest is None:
                self._latest = self._collect()
            return self._latest

    # ---------- poll loop ----------
    def _poll_loop(self) -> None:
        # priming call so CPU percent is meaningful
        psutil.cpu_percent(interval=None)
        while not self._stop.is_set():
            snap = self._collect()
            with self._snap_lock:
                self._latest = snap
            self._classify(snap)
            self._stop.wait(self.thresholds.interval_sec)

    def _collect(self) -> HealthSnapshot:
        vmem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        load = None
        try:
            load = os.getloadavg()  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            load = None

        disks: list[dict[str, Any]] = []
        inodes: list[dict[str, Any]] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(
                    {
                        "mount": part.mountpoint,
                        "device": part.device,
                        "fstype": part.fstype,
                        "total_mb": usage.total / 1_048_576,
                        "used_mb": usage.used / 1_048_576,
                        "percent": usage.percent,
                    }
                )
            except PermissionError:
                continue
            try:
                if hasattr(os, "statvfs"):
                    st = os.statvfs(part.mountpoint)  # type: ignore[attr-defined]
                    if st.f_files > 0:
                        used_inodes = st.f_files - st.f_ffree
                        pct = (used_inodes / st.f_files) * 100
                        inodes.append(
                            {
                                "mount": part.mountpoint,
                                "percent": pct,
                                "total": st.f_files,
                                "free": st.f_ffree,
                            }
                        )
            except (OSError, PermissionError):
                pass

        net = psutil.net_io_counters()
        net_io = {
            "bytes_sent": int(net.bytes_sent),
            "bytes_recv": int(net.bytes_recv),
            "packets_sent": int(net.packets_sent),
            "packets_recv": int(net.packets_recv),
            "errin": int(net.errin),
            "errout": int(net.errout),
        }

        gpus = self._collect_gpus()
        services = self._collect_services()

        return HealthSnapshot(
            timestamp=time.time(),
            hostname=socket.gethostname(),
            platform=platform.platform(),
            uptime_sec=time.time() - psutil.boot_time(),
            cpu_percent=psutil.cpu_percent(interval=None),
            cpu_count=psutil.cpu_count(logical=True) or 0,
            load_average=load,
            ram_percent=vmem.percent,
            ram_total_mb=vmem.total / 1_048_576,
            ram_used_mb=vmem.used / 1_048_576,
            swap_percent=swap.percent,
            disk=disks,
            inode=inodes,
            network_io=net_io,
            process_count=len(psutil.pids()),
            gpus=gpus,
            services=services,
            has_nvml=self._nvml_ok,
        )

    def _collect_gpus(self) -> list[GpuInfo]:
        if not self._nvml_ok:
            return []
        out: list[GpuInfo] = []
        try:
            n = pynvml.nvmlDeviceGetCount()
            for i in range(n):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                temp = None
                try:
                    temp = float(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
                except Exception:  # noqa: BLE001
                    temp = None
                out.append(
                    GpuInfo(
                        index=i,
                        name=name,
                        util_percent=float(util.gpu),
                        mem_used_mb=mem.used / 1_048_576,
                        mem_total_mb=mem.total / 1_048_576,
                        temperature_c=temp,
                    )
                )
        except Exception:  # noqa: BLE001
            return []
        return out

    def _collect_services(self) -> list[ServiceInfo]:
        if not self.watched_services:
            return []
        out: list[ServiceInfo] = []
        by_name: dict[str, ServiceInfo] = {
            name: ServiceInfo(name=name, pid=None, running=False) for name in self.watched_services
        }
        for proc in psutil.process_iter(
            attrs=["pid", "name", "cmdline", "cpu_percent", "memory_info"]
        ):
            try:
                info = proc.info
                pname = info.get("name") or ""
                cmdline = " ".join(info.get("cmdline") or [])
                for target in self.watched_services:
                    if target in pname or target in cmdline:
                        svc = by_name[target]
                        svc.pid = info["pid"]
                        svc.running = True
                        svc.cpu_percent = float(info.get("cpu_percent") or 0.0)
                        mi = info.get("memory_info")
                        if mi is not None:
                            svc.memory_rss_mb = mi.rss / 1_048_576
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        out = list(by_name.values())
        return out

    # ---------- classification ----------
    def _classify(self, snap: HealthSnapshot) -> None:
        t = self.thresholds
        self._maybe_raise(
            "cpu", "cpu", snap.cpu_percent, t.cpu_warn, t.cpu_crit, f"CPU {snap.cpu_percent:.1f}%"
        )
        self._maybe_raise(
            "ram", "ram", snap.ram_percent, t.ram_warn, t.ram_crit, f"RAM {snap.ram_percent:.1f}%"
        )
        if snap.load_average is not None:
            l1 = snap.load_average[0]
            self._maybe_raise("load", "load_1m", l1, t.load_warn, t.load_crit, f"load 1m {l1:.2f}")
        for d in snap.disk:
            self._maybe_raise(
                "disk",
                f"disk:{d['mount']}",
                d["percent"],
                t.disk_warn,
                t.disk_crit,
                f"disk {d['mount']} {d['percent']:.1f}%",
                detail={"mount": d["mount"], "device": d["device"]},
            )
        for d in snap.inode:
            self._maybe_raise(
                "inode",
                f"inode:{d['mount']}",
                d["percent"],
                t.inode_warn,
                t.inode_crit,
                f"inode {d['mount']} {d['percent']:.1f}%",
                detail={"mount": d["mount"]},
            )
        for g in snap.gpus:
            self._maybe_raise(
                "gpu",
                f"gpu:{g.index}",
                g.util_percent,
                t.gpu_warn,
                t.gpu_crit,
                f"GPU{g.index} {g.util_percent:.1f}%",
                detail={
                    "index": g.index,
                    "name": g.name,
                    "mem_pct": (g.mem_used_mb / g.mem_total_mb * 100) if g.mem_total_mb else 0.0,
                },
            )
        for svc in snap.services:
            if not svc.running:
                inc, was_new = self.incidents.raise_(
                    component="service",
                    kind="failure",
                    target=svc.name,
                    severity=IncidentSeverity.CRIT,
                    summary=f"service '{svc.name}' is not running",
                    detail={"service": svc.name},
                    rollback_hook=f"systemctl start {svc.name}",
                )
                if was_new:
                    self._on_new_incident(inc)
            else:
                # auto-resolve any open failure for this service
                sig_ = self._service_signature(svc.name)
                self.incidents.resolve(sig_)

    def _maybe_raise(
        self,
        component: str,
        target: str,
        value: float,
        warn: float,
        crit: float,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        sev: IncidentSeverity | None = None
        if value >= crit:
            sev = IncidentSeverity.CRIT
        elif value >= warn:
            sev = IncidentSeverity.WARN
        if sev is None:
            return
        merged = {"value": value, "warn": warn, "crit": crit}
        if detail:
            merged.update(detail)
        inc, was_new = self.incidents.raise_(
            component=component,
            kind="threshold",
            severity=sev,
            summary=summary,
            target=target,
            detail=merged,
        )
        if was_new:
            self._on_new_incident(inc)

    def _service_signature(self, name: str) -> str:
        from pradyos.warden_grid.incidents import signature

        return signature("service", "failure", name)

    def _on_new_incident(self, inc: Incident) -> None:
        self.audit.record(
            agent_id=self.AGENT_ID,
            kind="incident",
            summary=inc.summary,
            detail={
                "incident_id": inc.incident_id,
                "signature": inc.signature,
                "severity": inc.severity.value,
                "component": inc.component,
                **inc.detail,
            },
            rollback_hook=inc.rollback_hook,
        )
        self.bus.publish(
            "warden.incident",
            {
                "incident_id": inc.incident_id,
                "severity": inc.severity.value,
                "component": inc.component,
                "summary": inc.summary,
                "rollback_hook": inc.rollback_hook,
            },
        )

    # ---------- HTTP API ----------
    def _start_http(self) -> None:
        monitor = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: N802
                log.debug("warden.http " + fmt, *args)

            def do_GET(self) -> None:  # noqa: N802
                if self.path in ("/", "/health"):
                    self._write_json(monitor.latest_snapshot().to_dict())
                    return
                if self.path == "/incidents":
                    self._write_json(
                        {"open": [i.to_dict() for i in monitor.incidents.open_incidents()]}
                    )
                    return
                if self.path == "/incidents/all":
                    self._write_json({"all": [i.to_dict() for i in monitor.incidents.all()]})
                    return
                if self.path == "/services":
                    snap = monitor.latest_snapshot()
                    self._write_json({"services": [asdict(s) for s in snap.services]})
                    return
                if self.path == "/thresholds":
                    self._write_json(asdict(monitor.thresholds))
                    return
                if self.path == "/ping":
                    self._write_json({"ok": True, "agent": "warden_grid"})
                    return
                self.send_error(404, "not found")

            def _write_json(self, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="warden-http",
            daemon=True,
        )
        self._server_thread.start()
        log.info("WARDEN GRID HTTP API listening on http://%s:%d", self.host, self.port)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    mon = WardenMonitor()
    mon.start()
    log.info("WARDEN GRID running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log.info("WARDEN GRID shutting down")
        mon.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
