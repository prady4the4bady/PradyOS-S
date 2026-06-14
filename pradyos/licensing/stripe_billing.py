"""Stripe billing for PradyOS — hosted Checkout + webhook → tier activation.

The OS sells the tiers defined in :data:`pradyos.licensing.vault.PRICING`. This
module is the *bridge* between a Stripe subscription and the OS's offline license:

  * :func:`create_checkout_session` opens a Stripe Checkout for a tier (subscription
    mode) and returns the hosted URL the console redirects to.
  * :func:`tier_from_webhook` verifies a Stripe webhook signature and, on a
    completed checkout, returns the tier the buyer is now entitled to — the caller
    then activates it (e.g. mints/install a signed license, or flips the vault).

Everything is **optional and env-driven** so the OS runs with no Stripe at all:

  * ``STRIPE_SECRET_KEY``       — enables live checkout (else we return a stub).
  * ``STRIPE_WEBHOOK_SECRET``   — verifies webhook authenticity.
  * ``STRIPE_SUCCESS_URL`` / ``STRIPE_CANCEL_URL`` — post-checkout redirects.
  * ``PRADYOS_STRIPE_PRICE_<TIER>`` — override a tier's Stripe Price id.

The ``stripe`` SDK is imported lazily; if it is absent, checkout reports it
cleanly instead of crashing the web app.
"""

from __future__ import annotations

import os
from typing import Any

from pradyos.licensing.vault import PRICING, _TIER_ORDER


class StripeError(RuntimeError):
    """Stripe billing failure (misconfiguration, SDK missing, API error)."""


def is_configured() -> bool:
    """True when a Stripe secret key is present (live checkout possible)."""
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def price_id_for(tier: str) -> str | None:
    """The Stripe Price id for a tier — env override wins over the price book."""
    env = os.environ.get(f"PRADYOS_STRIPE_PRICE_{tier.upper()}")
    if env:
        return env
    return PRICING.get(tier, {}).get("stripe_price")


def _stripe() -> Any:
    try:
        import stripe  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise StripeError("the 'stripe' package is not installed") from exc
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise StripeError("STRIPE_SECRET_KEY is not set")
    stripe.api_key = key
    return stripe


def create_checkout_session(tier: str) -> dict[str, Any]:
    """Create a Stripe Checkout (subscription) for ``tier``; return its URL.

    Raises :class:`StripeError` when Stripe is unconfigured/absent so the caller
    can fall back to the offline-license path.
    """
    tier = tier.strip().lower()
    if tier not in _TIER_ORDER:
        raise StripeError(f"unknown tier {tier!r}")
    if tier == "free":
        return {"tier": tier, "status": "active", "checkout_url": None}
    price = price_id_for(tier)
    if not price:
        raise StripeError(f"no Stripe price configured for tier {tier!r}")
    stripe = _stripe()
    success = os.environ.get("STRIPE_SUCCESS_URL", "https://pradyos.local/billing/success")
    cancel = os.environ.get("STRIPE_CANCEL_URL", "https://pradyos.local/billing/cancel")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            success_url=success + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel,
            metadata={"tier": tier},
            subscription_data={"metadata": {"tier": tier}},
        )
    except Exception as exc:  # noqa: BLE001
        raise StripeError(f"Stripe checkout failed: {exc}") from exc
    return {
        "tier": tier,
        "status": "redirect",
        "checkout_url": session.get("url"),
        "session_id": session.get("id"),
    }


def tier_from_webhook(payload: bytes, sig_header: str) -> str | None:
    """Verify a webhook and return the tier to activate on a paid checkout.

    Returns ``None`` for events that don't grant entitlement. Raises
    :class:`StripeError` if the signature can't be verified.
    """
    stripe = _stripe()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise StripeError("STRIPE_WEBHOOK_SECRET is not set")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as exc:  # noqa: BLE001
        raise StripeError(f"invalid webhook signature: {exc}") from exc
    if event.get("type") != "checkout.session.completed":
        return None
    obj = (event.get("data") or {}).get("object") or {}
    tier = ((obj.get("metadata") or {}).get("tier") or "").lower()
    return tier if tier in _TIER_ORDER else None
