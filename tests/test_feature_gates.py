"""Feature gate tests — entitlement logic for free/pro/sovereign/enterprise tiers."""

from __future__ import annotations

import pytest

from pradyos.licensing import LicenseError, LicenseVault
from pradyos.licensing.vault import FEATURE_MIN_TIER, _TIER_ORDER


class _Ok:
    def verify(self, payload: bytes, signature: bytes) -> bool:
        return True


def _make_vault(tier: str = "free") -> LicenseVault:
    v = LicenseVault(verifier=_Ok())
    if tier != "free":
        import base64, json

        pb = json.dumps({"tier": tier, "holder": "test"}).encode("utf-8")
        b64 = base64.urlsafe_b64encode(pb).decode("ascii").rstrip("=")
        v.install(f"{b64}.c2ln")
    return v


# ── free tier: all free features pass, all paid features gate ────────────────


@pytest.mark.parametrize(
    "feature",
    [f for f, m in FEATURE_MIN_TIER.items() if m == "free"],
)
def test_free_features_pass_on_free_tier(feature):
    assert _make_vault("free").entitled(feature) is True


@pytest.mark.parametrize(
    "feature",
    [f for f, m in FEATURE_MIN_TIER.items() if m != "free"],
)
def test_paid_features_gate_on_free_tier(feature):
    assert _make_vault("free").entitled(feature) is False


# ── pro tier ─────────────────────────────────────────────────────────────────


def test_pro_tier_unlocks_pro_features():
    v = _make_vault("pro")
    assert v.entitled("research") is True
    assert v.entitled("guild") is True
    assert v.entitled("audit_log_export") is True


def test_pro_tier_gates_sovereign_features():
    v = _make_vault("pro")
    assert v.entitled("sovereign_mode") is False
    assert v.entitled("blueprint_manager") is False
    assert v.entitled("metrics_prometheus") is False


def test_pro_tier_gates_enterprise_features():
    v = _make_vault("pro")
    assert v.entitled("enterprise_seats") is False
    assert v.entitled("fleet_orchestration") is False
    assert v.entitled("aegis_integrity") is False


# ── sovereign tier ────────────────────────────────────────────────────────────


def test_sovereign_tier_unlocks_sovereign_features():
    v = _make_vault("sovereign")
    assert v.entitled("sovereign_mode") is True
    assert v.entitled("blueprint_manager") is True
    assert v.entitled("metrics_prometheus") is True
    assert v.entitled("cloud_ai") is True


def test_sovereign_tier_gates_enterprise_features():
    v = _make_vault("sovereign")
    assert v.entitled("enterprise_seats") is False
    assert v.entitled("fleet_orchestration") is False
    assert v.entitled("aegis_integrity") is False


# ── enterprise tier ────────────────────────────────────────────────────────────


def test_enterprise_tier_unlocks_all():
    v = _make_vault("enterprise")
    for feature in FEATURE_MIN_TIER:
        assert v.entitled(feature) is True, f"{feature} should be unlocked"


# ── open mode gate bypass ─────────────────────────────────────────────────────


def test_open_mode_bypasses_all_gates():
    v = LicenseVault()
    v.set_open_mode(True)
    for feature in FEATURE_MIN_TIER:
        assert v.entitled(feature) is True, f"{feature} should be free in open mode"


# ── grant_tier server-side activation ─────────────────────────────────────────


def test_grant_tier_activates_pro():
    v = LicenseVault()
    v.grant_tier("pro")
    assert v.entitled("research") is True
    assert v.entitled("sovereign_mode") is False


def test_grant_tier_activates_enterprise():
    v = LicenseVault()
    v.grant_tier("enterprise")
    assert v.entitled("aegis_integrity") is True
    assert v.entitled("fleet_orchestration") is True


def test_grant_tier_unknown_tier():
    v = LicenseVault()
    with pytest.raises(LicenseError, match="unknown tier"):
        v.grant_tier("wizard")


# ── require() enforcement ─────────────────────────────────────────────────────


def test_require_raises_on_gated_feature():
    v = LicenseVault()
    with pytest.raises(LicenseError, match="aegis_integrity"):
        v.require("aegis_integrity")


def test_require_passes_on_free_feature():
    LicenseVault().require("dev_mode")  # should not raise


# ── new feature gates from the directive ──────────────────────────────────────


def test_new_feature_gates_present():
    for f in ("dev_mode", "local_mode", "codemap", "benchmarks",
              "audit_log_export", "blueprint_manager",
              "fleet_orchestration", "aegis_integrity", "metrics_prometheus"):
        assert f in FEATURE_MIN_TIER, f"{f} must be in FEATURE_MIN_TIER"


def test_new_free_features_pass():
    v = _make_vault("free")
    for f in ("dev_mode", "local_mode", "codemap", "benchmarks"):
        assert v.entitled(f) is True, f"{f} should be free"


def test_new_paid_features_gate():
    v = _make_vault("free")
    for f in ("audit_log_export", "blueprint_manager",
              "fleet_orchestration", "aegis_integrity", "metrics_prometheus"):
        assert v.entitled(f) is False, f"{f} should be gated on free tier"
