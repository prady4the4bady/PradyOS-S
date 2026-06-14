#!/usr/bin/env python3
"""Idempotently create PradyOS's Stripe products/prices — TEST or LIVE.

The mode is whatever ``STRIPE_SECRET_KEY`` selects:
  * ``sk_test_...`` → creates the catalogue in **test mode** (safe for dev).
  * ``sk_live_...`` → live mode (the live prices already exist from the MCP run).

Run once::

    pip install stripe
    STRIPE_SECRET_KEY=sk_test_xxx python scripts/stripe_setup.py

It is idempotent: each tier uses a stable ``lookup_key`` so re-running reuses the
existing price instead of duplicating. It prints the resulting price ids and the
exact env block to drop into your deploy config so the OS uses them::

    PRADYOS_STRIPE_PRICE_PRO=price_...
    PRADYOS_STRIPE_PRICE_SOVEREIGN=price_...
    PRADYOS_STRIPE_PRICE_ENTERPRISE=price_...
"""

from __future__ import annotations

import os
import sys

# tier → (product name, yearly USD cents, stable lookup key)
TIERS = {
    "pro": ("PradyOS Pro", 500, "pradyos_pro_year"),
    "sovereign": ("PradyOS Sovereign", 2500, "pradyos_sovereign_year"),
    "enterprise": ("PradyOS Enterprise", 5000, "pradyos_enterprise_year"),
}


def main() -> int:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        print("ERROR: set STRIPE_SECRET_KEY (sk_test_... for test mode).", file=sys.stderr)
        return 2
    try:
        import stripe  # type: ignore
    except ImportError:
        print("ERROR: pip install stripe", file=sys.stderr)
        return 2
    stripe.api_key = key
    mode = "TEST" if key.startswith("sk_test") else "LIVE"
    print(f"# creating PradyOS catalogue in {mode} mode\n")

    env_lines: list[str] = []
    for tier, (name, cents, lookup) in TIERS.items():
        existing = stripe.Price.list(lookup_keys=[lookup], limit=1).get("data") or []
        if existing:
            price = existing[0]
            print(f"  {tier:11} reuse  {price['id']}  (${cents/100:.0f}/yr)")
        else:
            price = stripe.Price.create(
                unit_amount=cents,
                currency="usd",
                recurring={"interval": "year"},
                lookup_key=lookup,
                nickname=f"{name} (yearly)",
                product_data={"name": name},
                metadata={"tier": tier},
            )
            print(f"  {tier:11} create {price['id']}  (${cents/100:.0f}/yr)")
        env_lines.append(f"PRADYOS_STRIPE_PRICE_{tier.upper()}={price['id']}")

    print("\n# add these to your deploy env:")
    print("\n".join(env_lines))
    print("\n# also set STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_SUCCESS_URL, STRIPE_CANCEL_URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
