"""LICENSING — signed offline licenses + tiered entitlements.

How PradyOS is monetized without phoning home: a license is a small,
cryptographically **signed** token the Sovereign installs once. The OS verifies
the signature against a shipped **public** key (the private signing key never
leaves the vendor), reads the tier, and gates premium features accordingly. It
works fully offline; a leaked key is revoked by rotating the signing key.

  * **Deterministic, dep-free core.** Tier ordering, the feature→minimum-tier
    gating map, token parsing, and expiry are pure functions, unit-tested against
    a fake verifier with no crypto and a fixed clock.
  * **Signature verification is injected.** ``Ed25519Verifier`` is the production
    path (lazy ``cryptography`` import; absent ⇒ verify fails ⇒ free tier, the
    safe default). Tests inject a fake. The vendor mints licenses offline with
    :func:`sign_token` / :func:`generate_keypair`.

Tamper-EVIDENT, never tamper-punishing: an invalid/expired license simply drops
to the free tier — the OS never harms the machine.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Tiers, lowest → highest. A tier is entitled to every feature whose minimum tier
# is at or below it.
TIER_FREE = "free"
TIER_PRO = "pro"
TIER_SOVEREIGN = "sovereign"
TIER_ENTERPRISE = "enterprise"
_TIER_ORDER: dict[str, int] = {TIER_FREE: 0, TIER_PRO: 1, TIER_SOVEREIGN: 2, TIER_ENTERPRISE: 3}

# The gate: which tier a premium feature requires. Anything not listed is ungated.
FEATURE_MIN_TIER: dict[str, str] = {
    "manual_mode": TIER_FREE,
    "local_agents": TIER_FREE,
    "research": TIER_PRO,
    "guild": TIER_PRO,
    "guild_memory": TIER_PRO,
    "cloud_ai": TIER_SOVEREIGN,
    "sovereign_mode": TIER_SOVEREIGN,
    "autonomy_driver": TIER_SOVEREIGN,
    "apply_gate": TIER_SOVEREIGN,
    "enterprise_seats": TIER_ENTERPRISE,
    "priority_support": TIER_ENTERPRISE,
}

# Public price book (yearly, USD). The Sovereign elects a tier; the higher the
# tier the smarter/more-autonomous the OS. Kept in the $5–$50 band so the
# console's upgrade modal renders directly from this single source of truth.
# ``stripe_price`` maps a tier to its live Stripe Price id (override per env in
# ``stripe_billing``); a tier with no price needs no Stripe product.
PRICING: dict[str, dict[str, Any]] = {
    TIER_FREE: {
        "name": "Free",
        "price_year": 0,
        "tagline": "The desktop, on the house.",
        "perks": ["Manual desktop", "Local on-device agents", "Community support"],
    },
    TIER_PRO: {
        "name": "Pro",
        "price_year": 5,
        "stripe_price": "price_1TiEL3Pq3dHffIt6Wgz8IxYp",
        "tagline": "Smarter, with live intelligence.",
        "perks": ["Live research sources", "The Guild (multi-agent)", "Agent memory"],
    },
    TIER_SOVEREIGN: {
        "name": "Sovereign",
        "price_year": 25,
        "featured": True,
        "stripe_price": "price_1TiELGPq3dHffIt6C9kqIQBv",
        "tagline": "The machine governs. You approve.",
        "perks": [
            "Full Sovereign autonomy",
            "Cloud AI (stronger models)",
            "Self-improvement loop",
            "Approved-edit apply-gate",
        ],
    },
    TIER_ENTERPRISE: {
        "name": "Enterprise",
        "price_year": 50,
        "seat": True,
        "stripe_price": "price_1TiELOPq3dHffIt65UeMKw8d",
        "tagline": "Fleet-scale, with a human throat to choke.",
        "perks": ["Multi-seat management", "Priority support", "Private cloud keys / BYO-model"],
    },
}


class LicenseError(RuntimeError):
    """Base class for LICENSING failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _parse_expiry(expires: str) -> float:
    """ISO date/datetime → unix timestamp (accepts a trailing Z)."""
    return datetime.fromisoformat(expires.replace("Z", "+00:00")).timestamp()


@dataclass(frozen=True)
class License:
    tier: str
    holder: str
    issued: str
    expires: str | None
    raw: dict[str, Any]


class LicenseVault:
    """Holds the active license and answers entitlement questions."""

    def __init__(
        self,
        verifier: Any | None = None,
        clock: Any | None = None,
        open_mode: bool = False,
    ) -> None:
        # verifier.verify(payload: bytes, signature: bytes) -> bool. None ⇒ no
        # license can be trusted ⇒ the OS stays on the free tier.
        self._verifier = verifier
        self._clock = clock or time.time
        self._license: License | None = None
        # OPEN MODE — the Sovereign's master switch: when on, EVERY feature is
        # unlocked for everyone regardless of tier (a temporary "all free" promo /
        # beta). Flip it back off and paid gating resumes instantly. Defaults from
        # PRADYOS_OPEN_MODE so it can be set at boot, overridable at runtime.
        env_open = os.environ.get("PRADYOS_OPEN_MODE", "").strip().lower()
        self._open_mode = bool(open_mode) or env_open in ("1", "true", "yes", "on")
        self._lock = threading.RLock()

    # ── open mode (master switch) ───────────────────────────────────────────────

    def set_open_mode(self, enabled: bool) -> dict[str, Any]:
        """Turn the all-features-free master switch on/off; return status."""
        with self._lock:
            self._open_mode = bool(enabled)
        return self.status()

    def open_mode(self) -> bool:
        with self._lock:
            return self._open_mode

    # ── install / inspect ──────────────────────────────────────────────────────

    def install(self, token: str) -> dict[str, Any]:
        """Verify + activate a license token (``<b64 payload>.<b64 signature>``)."""
        if not _is_str(token):
            raise LicenseError("token must be a non-empty string")
        try:
            payload_b64, sig_b64 = token.strip().split(".", 1)
            payload_bytes = _b64url_decode(payload_b64)
            sig_bytes = _b64url_decode(sig_b64)
        except Exception as exc:  # noqa: BLE001
            raise LicenseError("malformed license token") from exc
        if self._verifier is None or not self._verifier.verify(payload_bytes, sig_bytes):
            raise LicenseError("license signature is not valid")
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise LicenseError("license payload is not valid JSON") from exc
        if not isinstance(data, dict):
            raise LicenseError("license payload must be an object")
        tier = str(data.get("tier", "")).lower()
        if tier not in _TIER_ORDER:
            raise LicenseError(f"unknown tier {tier!r}")
        lic = License(
            tier=tier,
            holder=str(data.get("holder", "")),
            issued=str(data.get("issued", "")),
            expires=data.get("expires") or None,
            raw=data,
        )
        if self._expired(lic):
            raise LicenseError("license has expired")
        with self._lock:
            self._license = lic
        return self.status()

    def grant_tier(self, tier: str, holder: str = "", expires: str | None = None) -> dict[str, Any]:
        """Activate a tier from a TRUSTED server-side event (a verified Stripe
        webhook after payment). Unlike :meth:`install` this needs no signature —
        callers MUST gate it behind their own trust check (webhook signature)."""
        tier = str(tier).strip().lower()
        if tier not in _TIER_ORDER:
            raise LicenseError(f"unknown tier {tier!r}")
        lic = License(tier=tier, holder=holder, issued="", expires=expires, raw={"source": "stripe"})
        with self._lock:
            self._license = lic
        return self.status()

    def _expired(self, lic: License) -> bool:
        if not lic.expires:
            return False
        try:
            return self._clock() > _parse_expiry(lic.expires)
        except Exception:  # noqa: BLE001 — unparseable expiry → fail closed (treat as expired)
            return True

    def tier(self) -> str:
        with self._lock:
            lic = self._license
        if lic is None or self._expired(lic):
            return TIER_FREE
        return lic.tier

    def entitled(self, feature: str) -> bool:
        """Is ``feature`` unlocked at the active tier? (Unknown features ungated.)"""
        if self.open_mode():  # master switch: everything free for everyone
            return True
        min_tier = FEATURE_MIN_TIER.get(feature)
        if min_tier is None:
            return True
        return _TIER_ORDER[self.tier()] >= _TIER_ORDER[min_tier]

    def require(self, feature: str) -> None:
        """Raise if ``feature`` is not entitled (for gating server-side actions)."""
        if not self.entitled(feature):
            raise LicenseError(
                f"feature {feature!r} requires the "
                f"{FEATURE_MIN_TIER.get(feature, '?')} tier (current: {self.tier()})"
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            lic = self._license
        valid = lic is not None and not self._expired(lic)
        return {
            "tier": self.tier(),
            "holder": lic.holder if lic else "",
            "expires": lic.expires if lic else None,
            "valid": valid,
            "open_mode": self.open_mode(),
            "entitlements": {f: self.entitled(f) for f in FEATURE_MIN_TIER},
        }

    @staticmethod
    def tiers() -> dict[str, list[str]]:
        """The catalogue: each tier → the features it unlocks."""
        return {
            t: sorted(f for f, m in FEATURE_MIN_TIER.items() if _TIER_ORDER[m] <= _TIER_ORDER[t])
            for t in _TIER_ORDER
        }

    @staticmethod
    def pricing() -> list[dict[str, Any]]:
        """The price book as an ordered list (free→enterprise) for the upgrade UI."""
        return [
            {
                "tier": t,
                "name": PRICING[t]["name"],
                "price": PRICING[t]["price_year"],
                "feat": bool(PRICING[t].get("featured")),
                "seat": bool(PRICING[t].get("seat")),
                "tagline": PRICING[t].get("tagline", ""),
                "perks": list(PRICING[t].get("perks", [])),
                "features": LicenseVault.tiers()[t],
            }
            for t in sorted(_TIER_ORDER, key=lambda x: _TIER_ORDER[x])
        ]

    def clear(self) -> dict[str, Any]:
        with self._lock:
            self._license = None
        return self.status()


class Ed25519Verifier:
    """Production verifier — Ed25519 over a shipped PEM **public** key.

    Lazy ``cryptography`` import; if it is unavailable or the signature is bad,
    :meth:`verify` returns ``False`` (the OS stays free — fail safe, never crash)."""

    def __init__(self, public_key_pem: str) -> None:
        self._pem = public_key_pem
        self._key: Any | None = None

    def verify(self, payload: bytes, signature: bytes) -> bool:
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            if self._key is None:
                self._key = load_pem_public_key(self._pem.encode("utf-8"))
            self._key.verify(signature, payload)
            return True
        except Exception:  # noqa: BLE001 — any failure ⇒ not verified
            return False


# ── vendor-side tooling (run OFFLINE; the private key never ships) ──────────────


def generate_keypair() -> tuple[str, str]:
    """Generate an Ed25519 (private_pem, public_pem). Keep the private key secret."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    private_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        priv.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def sign_token(payload: dict[str, Any], private_key_pem: str) -> str:
    """Mint a license token by signing ``payload`` with the Ed25519 private key."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    key = load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    signature = key.sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"
