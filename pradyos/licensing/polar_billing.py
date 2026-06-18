"""Polar.sh billing for PradySovereign — lightweight hosted checkout.

Opt-in via POLAR_ACCESS_TOKEN and PRADYOS_POLAR_PRODUCT_<TIER> env vars.
Falls back cleanly if not configured.
"""

from __future__ import annotations

import os
from typing import Any

POLAR_PRODUCT_IDS: dict[str, str] = {
    "pro": os.environ.get("PRADYOS_POLAR_PRODUCT_PRO", ""),
    "sovereign": os.environ.get("PRADYOS_POLAR_PRODUCT_SOVEREIGN", ""),
    "enterprise": os.environ.get("PRADYOS_POLAR_PRODUCT_ENTERPRISE", ""),
}


class PolarError(RuntimeError):
    """Polar.sh billing failure (misconfiguration)."""


def is_configured() -> bool:
    """True when a Polar access token is present (can generate checkout URLs)."""
    return bool(os.environ.get("POLAR_ACCESS_TOKEN"))


def checkout_url(tier: str) -> str | None:
    """Return the Polar.sh hosted checkout URL for a tier, or None if unconfigured."""
    product_id = POLAR_PRODUCT_IDS.get(tier.lower(), "")
    if not product_id:
        return None
    return f"https://buy.polar.sh/{product_id}"


def tier_from_webhook(payload: bytes, sig_header: str) -> str | None:
    """Verify Polar webhook and return tier.

    Polar webhook verification: https://docs.polar.sh/developers/webhooks
    Returns None (stub) until Polar product IDs are configured.
    """
    return None
