"""LICENSING plane — signed offline licenses + tiered entitlements.

See :mod:`pradyos.licensing.vault`.
"""

from __future__ import annotations

from pradyos.licensing.vault import (
    FEATURE_MIN_TIER,
    TIER_ENTERPRISE,
    TIER_FREE,
    TIER_PRO,
    TIER_SOVEREIGN,
    Ed25519Verifier,
    License,
    LicenseError,
    LicenseVault,
    generate_keypair,
    sign_token,
)

__all__ = [
    "FEATURE_MIN_TIER",
    "TIER_ENTERPRISE",
    "TIER_FREE",
    "TIER_PRO",
    "TIER_SOVEREIGN",
    "Ed25519Verifier",
    "License",
    "LicenseError",
    "LicenseVault",
    "generate_keypair",
    "sign_token",
]
