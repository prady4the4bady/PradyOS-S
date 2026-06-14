"""LICENSING tests — entitlement logic (fake verifier) + Ed25519 round-trip."""

from __future__ import annotations

import base64
import json

import pytest

from pradyos.licensing import LicenseError, LicenseVault

_NOW = 1_700_000_000  # a fixed clock for deterministic expiry tests (~2023)


class _Ok:
    def verify(self, payload: bytes, signature: bytes) -> bool:
        return True


class _No:
    def verify(self, payload: bytes, signature: bytes) -> bool:
        return False


def _token(payload: dict) -> str:
    pb = json.dumps(payload).encode("utf-8")
    b = base64.urlsafe_b64encode(pb).decode("ascii").rstrip("=")
    return f"{b}.c2ln"  # any signature; the fake verifier decides validity


# ── free tier + gating ──────────────────────────────────────────────────────────


def test_free_tier_by_default():
    v = LicenseVault()
    assert v.tier() == "free"
    assert v.entitled("manual_mode") is True  # free feature
    assert v.entitled("sovereign_mode") is False  # premium, gated
    assert v.entitled("cloud_ai") is False
    assert v.status()["valid"] is False


def test_install_sovereign_unlocks_premium():
    v = LicenseVault(verifier=_Ok())
    st = v.install(_token({"tier": "sovereign", "holder": "Prady"}))
    assert st["tier"] == "sovereign" and st["holder"] == "Prady" and st["valid"] is True
    assert v.entitled("sovereign_mode") is True
    assert v.entitled("research") is True  # lower tier feature also unlocked
    assert v.entitled("enterprise_seats") is False  # higher tier still gated


def test_pro_tier_gates_cloud_ai():
    v = LicenseVault(verifier=_Ok())
    v.install(_token({"tier": "pro"}))
    assert v.entitled("research") is True and v.entitled("cloud_ai") is False


def test_unknown_feature_is_ungated():
    assert LicenseVault().entitled("some_random_feature") is True


# ── verification + validation ────────────────────────────────────────────────────


def test_invalid_signature_rejected():
    with pytest.raises(LicenseError, match="signature"):
        LicenseVault(verifier=_No()).install(_token({"tier": "sovereign"}))


def test_no_verifier_rejects_everything():
    with pytest.raises(LicenseError, match="signature"):
        LicenseVault().install(_token({"tier": "sovereign"}))


@pytest.mark.parametrize("bad", ["", "nodot", "  "])
def test_malformed_token_rejected(bad):
    with pytest.raises(LicenseError):
        LicenseVault(verifier=_Ok()).install(bad)


def test_bad_payload_json_rejected():
    tok = base64.urlsafe_b64encode(b"not json").decode().rstrip("=") + ".c2ln"
    with pytest.raises(LicenseError, match="JSON"):
        LicenseVault(verifier=_Ok()).install(tok)


def test_unknown_tier_rejected():
    with pytest.raises(LicenseError, match="unknown tier"):
        LicenseVault(verifier=_Ok()).install(_token({"tier": "wizard"}))


# ── expiry ───────────────────────────────────────────────────────────────────────


def test_expired_license_rejected():
    v = LicenseVault(verifier=_Ok(), clock=lambda: _NOW)
    with pytest.raises(LicenseError, match="expired"):
        v.install(_token({"tier": "sovereign", "expires": "2020-01-01T00:00:00Z"}))


def test_future_expiry_is_valid():
    v = LicenseVault(verifier=_Ok(), clock=lambda: _NOW)
    v.install(_token({"tier": "sovereign", "expires": "2099-01-01T00:00:00Z"}))
    assert v.tier() == "sovereign" and v.status()["valid"] is True


def test_unparseable_expiry_fails_closed():
    v = LicenseVault(verifier=_Ok(), clock=lambda: _NOW)
    with pytest.raises(LicenseError, match="expired"):
        v.install(_token({"tier": "sovereign", "expires": "whenever"}))


# ── catalogue / require / clear ──────────────────────────────────────────────────


def test_tiers_catalogue_is_cumulative():
    t = LicenseVault().tiers()
    assert "manual_mode" in t["free"]
    assert "sovereign_mode" in t["sovereign"] and "sovereign_mode" not in t["pro"]
    # enterprise unlocks everything the lower tiers do
    assert set(t["sovereign"]).issubset(set(t["enterprise"]))


def test_require_raises_when_not_entitled():
    v = LicenseVault()
    with pytest.raises(LicenseError, match="sovereign"):
        v.require("sovereign_mode")
    v.require("manual_mode")  # free → no raise


def test_clear_drops_to_free():
    v = LicenseVault(verifier=_Ok())
    v.install(_token({"tier": "enterprise"}))
    assert v.clear()["tier"] == "free"


# ── real Ed25519 round-trip (skips if cryptography is absent) ───────────────────


def test_ed25519_sign_verify_roundtrip():
    pytest.importorskip("cryptography")
    from pradyos.licensing import Ed25519Verifier, generate_keypair, sign_token

    private_pem, public_pem = generate_keypair()
    token = sign_token({"tier": "sovereign", "holder": "Prady"}, private_pem)
    vault = LicenseVault(verifier=Ed25519Verifier(public_pem))
    assert vault.install(token)["tier"] == "sovereign"

    # a token signed by a DIFFERENT key must be rejected
    other_priv, _ = generate_keypair()
    forged = sign_token({"tier": "enterprise"}, other_priv)
    with pytest.raises(LicenseError, match="signature"):
        vault.install(forged)
