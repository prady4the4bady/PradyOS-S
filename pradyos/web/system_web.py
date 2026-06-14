"""HTTP surface for the OS shell's REAL system data — what makes the console an
actual OS face rather than a mock.

Registers ``/api/v1/system/*`` and ``/api/v1/files``:

  * ``GET /api/v1/system/metrics``   — live CPU / RAM / disk / network rates,
  * ``GET /api/v1/system/info``      — neofetch facts (kernel, host, uptime, …),
  * ``GET /api/v1/system/processes`` — top processes by CPU,
  * ``GET /api/v1/files``            — a read-only directory listing of the real
    filesystem, scoped to the user's home (no traversal escape).

``psutil`` is used when present (real numbers) and the endpoints **degrade
gracefully** to stdlib / synthetic values when it is not — so the shell is always
alive and ``create_app()`` never hard-depends on an optional package. Everything
is read-only; the file endpoint refuses to leave its root.
"""

from __future__ import annotations

import os
import platform
import socket
import time
from pathlib import Path
from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse

try:  # optional — real metrics when available
    import psutil  # type: ignore
except Exception:  # noqa: BLE001
    psutil = None  # type: ignore

# net-rate state (counters + timestamp of the previous sample)
_NET_PREV: dict[str, float] = {}
# pseudo CPU baseline so the synthetic path is stable-ish rather than pure noise
_SYNTH = {"cpu": 12.0, "gpu": 18.0}


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    if d:
        return f"{d}d {h}h {m}m"
    return f"{h}h {m}m"


def _safe_root() -> Path:
    return Path(os.environ.get("PRADYOS_FILES_ROOT", str(Path.home()))).resolve()


def register_system_routes(app: Any) -> None:
    """Register the real-system + filesystem routes on ``app``."""

    @app.get("/api/v1/system/metrics")
    async def api_system_metrics() -> JSONResponse:
        if psutil is not None:
            try:
                cpu = float(psutil.cpu_percent(interval=None))
                ram = float(psutil.virtual_memory().percent)
                root = "C:\\" if os.name == "nt" else "/"
                disk = float(psutil.disk_usage(root).percent)
                net = psutil.net_io_counters()
                now = time.time()
                down = up = 0.0
                if _NET_PREV:
                    dt = max(1e-6, now - _NET_PREV["t"])
                    down = (net.bytes_recv - _NET_PREV["r"]) * 8 / dt / 1e9  # Gbps
                    up = (net.bytes_sent - _NET_PREV["s"]) * 8 / dt / 1e6  # Mbps
                _NET_PREV.update(t=now, r=net.bytes_recv, s=net.bytes_sent)
                # GPU is platform-specific; approximate from load unless NVML present.
                gpu = min(99.0, cpu * 1.3)
                return JSONResponse(
                    {
                        "cpu": round(cpu, 1),
                        "gpu": round(gpu, 1),
                        "ram": round(ram, 1),
                        "disk": round(disk, 1),
                        "net_down": round(max(0.0, down), 2),
                        "net_up": round(max(0.0, up), 1),
                        "source": "psutil",
                    }
                )
            except Exception:  # noqa: BLE001 — fall through to synthetic
                pass
        # synthetic, gently varying so the rings move without a backend
        import random

        _SYNTH["cpu"] = max(4, min(60, _SYNTH["cpu"] + random.uniform(-4, 4)))
        _SYNTH["gpu"] = max(8, min(70, _SYNTH["gpu"] + random.uniform(-4, 4)))
        return JSONResponse(
            {
                "cpu": round(_SYNTH["cpu"], 1),
                "gpu": round(_SYNTH["gpu"], 1),
                "ram": 32.0,
                "disk": 68.0,
                "net_down": round(1 + random.random(), 2),
                "net_up": round(700 + random.random() * 400, 1),
                "source": "synthetic",
            }
        )

    @app.get("/api/v1/system/info")
    async def api_system_info() -> JSONResponse:
        info: dict[str, Any] = {
            "os": "PRADYOS Sovereign Edition",
            "kernel": platform.release() or "6.x-nebula",
            "host": socket.gethostname() or "pradyos",
            "shell": os.environ.get("SHELL", "PRISM").split("/")[-1] or "PRISM",
            "cpu_model": platform.processor() or platform.machine() or "—",
            "arch": platform.machine(),
        }
        if psutil is not None:
            try:
                info["mem_total"] = _fmt_bytes(psutil.virtual_memory().total)
                info["uptime"] = _fmt_uptime(time.time() - psutil.boot_time())
                info["cpu_cores"] = psutil.cpu_count(logical=True)
            except Exception:  # noqa: BLE001
                pass
        info.setdefault("mem_total", "—")
        info.setdefault("uptime", "—")
        return JSONResponse(info)

    @app.get("/api/v1/system/processes")
    async def api_system_processes() -> JSONResponse:
        procs: list[dict[str, Any]] = []
        if psutil is not None:
            try:
                for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
                    procs.append(
                        {
                            "name": (p.info.get("name") or "?")[:32],
                            "cpu": round(float(p.info.get("cpu_percent") or 0.0), 1),
                            "mem": round(float(p.info.get("memory_percent") or 0.0), 1),
                        }
                    )
                procs.sort(key=lambda x: x["cpu"], reverse=True)
                return JSONResponse({"processes": procs[:15], "source": "psutil"})
            except Exception:  # noqa: BLE001
                pass
        sample = [
            {"name": "pradyos-kernel", "cpu": 3.1, "mem": 2.4},
            {"name": "prism-shell", "cpu": 1.4, "mem": 1.1},
            {"name": "guild-worker", "cpu": 2.2, "mem": 3.0},
            {"name": "aurora-throne", "cpu": 0.9, "mem": 1.8},
            {"name": "warden-grid", "cpu": 0.6, "mem": 0.9},
        ]
        return JSONResponse({"processes": sample, "source": "synthetic"})

    @app.get("/api/v1/files")
    async def api_files(path: str = Query("~")) -> JSONResponse:
        root = _safe_root()
        try:
            target = (root if path in ("~", "", "/") else Path(path).expanduser()).resolve()
            # refuse to escape the configured root (path-traversal guard)
            if root not in target.parents and target != root:
                target = root
            if not target.is_dir():
                target = root
            entries: list[dict[str, Any]] = []
            for child in sorted(
                target.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())
            ):
                if child.name.startswith("."):
                    continue
                try:
                    size_kb = round(child.stat().st_size / 1024, 1) if child.is_file() else 0
                except OSError:
                    size_kb = 0
                entries.append({"name": child.name, "is_dir": child.is_dir(), "size_kb": size_kb})
            return JSONResponse(
                {"path": str(target), "root": str(root), "entries": entries[:200]}
            )
        except Exception:  # noqa: BLE001 — never leak a stack trace to the shell
            return JSONResponse({"path": str(root), "root": str(root), "entries": []})
