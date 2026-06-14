#!/usr/bin/env python3
"""Vendor-side: build + sign the AEGIS integrity manifest for a PradyOS release.

Computes SHA-256 of every ``pradyos/**/*.py`` and signs the manifest with the
Ed25519 private key (which NEVER ships). The OS verifies it at runtime with the
public key and self-disables premium on tamper (see ``pradyos.aegis``).

Generate a keypair once (keep the private key secret)::

    python -c "from pradyos.licensing.vault import generate_keypair; \
               priv,pub=generate_keypair(); open('aegis_priv.pem','w').write(priv); \
               open('aegis_pub.pem','w').write(pub)"

Then, at each release::

    python scripts/build_manifest.py aegis_priv.pem var/integrity.manifest

At runtime, point the OS at it::

    PRADYOS_INTEGRITY_MANIFEST=var/integrity.manifest \
    PRADYOS_INTEGRITY_PUBKEY=aegis_pub.pem  python -m pradyos.sovereign_web
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: build_manifest.py <private_key.pem> <out_manifest_path>", file=sys.stderr)
        return 2
    priv_path, out_path = argv[1], argv[2]
    import pradyos
    from pradyos.aegis import hash_tree, sign_manifest

    root = Path(pradyos.__file__).resolve().parent
    hashes = hash_tree(root)
    token = sign_manifest(hashes, Path(priv_path).read_text(encoding="utf-8"))
    Path(out_path).write_text(token, encoding="utf-8")
    print(f"signed manifest for {len(hashes)} files → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
