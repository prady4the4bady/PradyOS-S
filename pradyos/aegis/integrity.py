"""AEGIS — software integrity & tamper-evidence (the legitimate security pass).

A released PradyOS ships with a **signed manifest** of SHA-256 hashes of its own
source files. AEGIS recomputes those hashes at runtime and compares them to the
signed snapshot, so the OS can *prove* it hasn't been altered — and react if it
has. Crucially this is **tamper-EVIDENT, never tamper-punishing**: on a mismatch
AEGIS reports it and (optionally) drops premium entitlements / refuses to run —
it **never harms the inspecting machine**. (Anti-reverse-engineering that attacks
the analyst is exactly what the L4 critic blocks.)

  * Manifest signing reuses the project's audited Ed25519 path (the private key
    never ships; only the public key does).
  * No manifest configured ⇒ status ``unverified`` (dev default), not a false
    alarm.
  * Deterministic and dependency-light; hashing is pure stdlib.

Boot-level protections (Secure Boot, TPM-sealed keys, a measured/locked
bootloader) live in the ISO pipeline, not this Python module — see the build
scripts and docs/AGI_ASI_ROADMAP. AEGIS is the *application-layer* half.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable

__all__ = ["hash_tree", "IntegrityGuard", "load_signed_manifest", "sign_manifest"]

_EXCLUDE_DIRS = {"__pycache__", "phase_patches"}


def hash_tree(root: Path | str, patterns: tuple[str, ...] = ("*.py",)) -> dict[str, str]:
    """Map ``relpath -> sha256`` for every matching file under ``root``."""
    root = Path(root)
    base = root.parent
    out: dict[str, str] = {}
    for pat in patterns:
        for path in sorted(root.rglob(pat)):
            if any(part in _EXCLUDE_DIRS for part in path.relative_to(root).parts):
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            out[str(path.relative_to(base)).replace("\\", "/")] = digest
    return out


def sign_manifest(hashes: dict[str, str], private_key_pem: str) -> str:
    """Vendor-side: sign a hash manifest with the Ed25519 private key (offline)."""
    from pradyos.licensing.vault import sign_token

    return sign_token({"hashes": hashes}, private_key_pem)


def load_signed_manifest(token: str, public_key_pem: str) -> dict[str, str] | None:
    """Verify a signed manifest token; return its hashes, or ``None`` if invalid."""
    from pradyos.licensing.vault import Ed25519Verifier, _b64url_decode  # noqa: PLC2701

    try:
        payload_b64, sig_b64 = token.strip().split(".", 1)
        payload = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:  # noqa: BLE001
        return None
    if not Ed25519Verifier(public_key_pem).verify(payload, sig):
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
        hashes = data.get("hashes")
        return hashes if isinstance(hashes, dict) else None
    except Exception:  # noqa: BLE001
        return None


class IntegrityGuard:
    """Verifies the running tree against an expected (ideally signed) manifest."""

    def __init__(
        self,
        expected: dict[str, str] | None = None,
        root: Path | str | None = None,
        on_tamper: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        if root is None:
            import pradyos

            root = Path(pradyos.__file__).resolve().parent
        self._root = Path(root)
        self._expected = expected
        self._on_tamper = on_tamper
        self._fired = False
        self._lock = threading.RLock()

    def verify(self) -> dict[str, Any]:
        """Compare the live tree to the manifest; fire on_tamper once on mismatch."""
        if not self._expected:
            return {"status": "unverified", "reason": "no signed manifest configured"}
        current = hash_tree(self._root)
        changed = sorted(
            p for p, h in self._expected.items() if current.get(p) and current[p] != h
        )
        missing = sorted(p for p in self._expected if p not in current)
        report = {
            "status": "ok" if not (changed or missing) else "tampered",
            "tracked": len(self._expected),
            "changed": changed,
            "missing": missing,
        }
        if report["status"] == "tampered":
            with self._lock:
                first = not self._fired
                self._fired = True
            if first and self._on_tamper is not None:
                try:
                    self._on_tamper(report)
                except Exception:  # noqa: BLE001 — response must never crash the OS
                    pass
        return report

    def status(self) -> dict[str, Any]:
        return {"configured": bool(self._expected), "root": str(self._root), "tamper_fired": self._fired}
