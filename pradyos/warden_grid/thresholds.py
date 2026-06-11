"""WARDEN GRID alert thresholds.

Defaults conservative. Sovereign can override per-field via env var
``PRADYOS_THRESHOLD_<NAME>`` or by passing a ``Thresholds`` instance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _envf(name: str, default: float) -> float:
    v = os.environ.get(f"PRADYOS_THRESHOLD_{name}")
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


@dataclass(slots=True)
class Thresholds:
    """Re-reads env each instantiation so monkeypatched env wins."""

    cpu_warn: float = field(default_factory=lambda: _envf("CPU_WARN", 80.0))
    cpu_crit: float = field(default_factory=lambda: _envf("CPU_CRIT", 95.0))
    ram_warn: float = field(default_factory=lambda: _envf("RAM_WARN", 80.0))
    ram_crit: float = field(default_factory=lambda: _envf("RAM_CRIT", 95.0))
    disk_warn: float = field(default_factory=lambda: _envf("DISK_WARN", 85.0))
    disk_crit: float = field(default_factory=lambda: _envf("DISK_CRIT", 95.0))
    gpu_warn: float = field(default_factory=lambda: _envf("GPU_WARN", 85.0))
    gpu_crit: float = field(default_factory=lambda: _envf("GPU_CRIT", 97.0))
    load_warn: float = field(default_factory=lambda: _envf("LOAD_WARN", 4.0))
    load_crit: float = field(default_factory=lambda: _envf("LOAD_CRIT", 8.0))
    inode_warn: float = field(default_factory=lambda: _envf("INODE_WARN", 85.0))
    inode_crit: float = field(default_factory=lambda: _envf("INODE_CRIT", 95.0))
    interval_sec: float = field(default_factory=lambda: _envf("INTERVAL_SEC", 5.0))
