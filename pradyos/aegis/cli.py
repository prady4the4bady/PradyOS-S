"""AEGIS boot-time integrity check — the CLI a systemd unit runs at boot.

    python -m pradyos.aegis verify

Loads the signed manifest from ``PRADYOS_INTEGRITY_MANIFEST`` (a signed token),
verifies it with ``PRADYOS_INTEGRITY_PUBKEY``, recomputes the running tree's
hashes, and writes a result marker to ``PRADYOS_INTEGRITY_RESULT``
(default ``var/aegis-result.json``). Exit code:

  * ``0`` — ``ok`` or ``unverified`` (no manifest configured ⇒ dev/early boot)
  * ``1`` — ``tampered`` (a tracked file changed or went missing)

The marker lets the rest of the OS react (the running app already drops to the
free tier on tamper). This stays tamper-EVIDENT: it reports and degrades — it
never touches anything outside PradyOS, and never the user's hardware.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _load_expected(env: Mapping[str, str]) -> dict[str, str] | None:
    man = env.get("PRADYOS_INTEGRITY_MANIFEST")
    pub = env.get("PRADYOS_INTEGRITY_PUBKEY")
    if not (man and pub):
        return None
    try:
        from pradyos.aegis import load_signed_manifest

        token = Path(man).read_text(encoding="utf-8")
        pub_pem = Path(pub).read_text(encoding="utf-8")
        return load_signed_manifest(token, pub_pem)
    except Exception:  # noqa: BLE001 — unreadable/invalid ⇒ unverified, never crash boot
        return None


def verify(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Run the integrity verification and write the result marker. Returns the report."""
    env = env if env is not None else os.environ
    from pradyos.aegis import IntegrityGuard

    expected = _load_expected(env)
    report = IntegrityGuard(expected=expected).verify()
    out = env.get("PRADYOS_INTEGRITY_RESULT", "var/aegis-result.json")
    try:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError:
        pass  # a read-only /var must not fail the check
    return report


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "verify"
    if cmd not in ("verify", "status"):
        print(f"usage: python -m pradyos.aegis verify   (got {cmd!r})", file=sys.stderr)
        return 2
    report = verify(env)
    print(json.dumps(report))
    return 1 if report.get("status") == "tampered" else 0


if __name__ == "__main__":
    raise SystemExit(main())
