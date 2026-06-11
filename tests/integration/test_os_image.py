"""PRADY OS — host-side OS-image integration test.

Boots dist/pradyos-sovereign.iso headless in QEMU via scripts/verify_boot.sh
and asserts the in-guest selftest (core planes + cross-plane round-trip)
and the host-side API probes both pass.

Opt-in by design — it needs a built ISO, QEMU, and ~5-25 minutes:

    PRADYOS_OS_IMAGE_TESTS=1 pytest tests/integration/ -v

It is intentionally NOT part of scripts/prove.py's module list; the OS-image
gate lives in .github/workflows/os-image.yml and `make verify-os`.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ISO = ROOT / "dist" / "pradyos-sovereign.iso"
HARNESS = ROOT / "scripts" / "verify_boot.sh"

pytestmark = pytest.mark.skipif(
    os.environ.get("PRADYOS_OS_IMAGE_TESTS") != "1"
    or not ISO.exists()
    or shutil.which("bash") is None
    or (shutil.which("qemu-system-x86_64") is None and os.name != "nt"),
    reason=(
        "OS-image test is opt-in: build dist/pradyos-sovereign.iso "
        "(sudo bash scripts/build_iso.sh) and set PRADYOS_OS_IMAGE_TESTS=1"
    ),
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.timeout(2400)
def test_iso_boots_and_core_planes_converge(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PRADYOS_VM_PORT"] = str(_free_port())
    env["PRADYOS_VERIFY_DIR"] = str(tmp_path)
    res = subprocess.run(
        ["bash", str(HARNESS), str(ISO)],
        env=env,
        capture_output=True,
        text=True,
        timeout=2100,
    )
    tail = (res.stdout or "")[-4000:] + "\n--- stderr ---\n" + (res.stderr or "")[-2000:]
    assert res.returncode == 0, f"verify_boot.sh failed:\n{tail}"
    assert "PASS — image verified" in res.stdout, tail
    serial = (tmp_path / "serial.log").read_text(errors="replace")
    assert "PRADYOS-SELFTEST: PASS" in serial
