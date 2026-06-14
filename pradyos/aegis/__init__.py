"""AEGIS plane — software integrity & tamper-evidence (security).

See :mod:`pradyos.aegis.integrity`. Verifies the OS's own files against a signed
manifest; tamper-EVIDENT (self-disables premium), never tamper-punishing.
"""

from __future__ import annotations

from pradyos.aegis.integrity import IntegrityGuard, hash_tree, load_signed_manifest, sign_manifest

__all__ = ["IntegrityGuard", "hash_tree", "load_signed_manifest", "sign_manifest"]
