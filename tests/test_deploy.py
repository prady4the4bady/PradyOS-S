"""Tests for deploy infrastructure files.

Phase 7G: Dockerfile, docker-compose, CI workflow.
Phase 9:  Two new systemd units (oracle, admission), Docker hardening,
          oracle + admission services in docker-compose.

No Docker daemon or systemd required -- all assertions are pure file/text checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SYSTEMD_DIR = REPO_ROOT / "deploy" / "systemd"
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.yml"
DOCKERFILE = REPO_ROOT / "deploy" / "Dockerfile"


# ---------------------------------------------------------------------------
# 1. Dockerfile structure (Phase 7G)
# ---------------------------------------------------------------------------

def test_dockerfile_exists():
    assert DOCKERFILE.exists(), "deploy/Dockerfile not found"


def test_dockerfile_has_multistage_build():
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:" in content
    assert "AS builder" in content
    assert "AS runtime" in content


def test_dockerfile_exposes_port_8000():
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "EXPOSE 8000" in content, "Dockerfile must EXPOSE 8000"


def test_dockerfile_has_healthcheck():
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content, "Dockerfile must define a HEALTHCHECK"


def test_dockerfile_uses_nonroot_user():
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER pradyos" in content or "useradd" in content


# ---------------------------------------------------------------------------
# 2. Dockerfile hardening (Phase 9)
# ---------------------------------------------------------------------------

def test_dockerfile_uses_python312():
    """Base image must be Python 3.12 (Phase 9 upgrade from 3.11)."""
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "python:3.12" in content, "Dockerfile base image must be python:3.12-slim"


def test_dockerfile_chown_copy():
    """COPY --chown ensures venv/source owned by non-root user."""
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "--chown=pradyos" in content, "Dockerfile must COPY --chown=pradyos"


# ---------------------------------------------------------------------------
# 3. docker-compose.yml baseline (Phase 7G)
# ---------------------------------------------------------------------------

def test_docker_compose_exists():
    assert COMPOSE_FILE.exists(), "deploy/docker-compose.yml not found"


def test_docker_compose_has_sovereign_service():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "sovereign:" in content


def test_docker_compose_has_volume():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "volumes:" in content


# ---------------------------------------------------------------------------
# 4. docker-compose Phase 9: oracle + admission services
# ---------------------------------------------------------------------------

def test_docker_compose_has_oracle_service():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "oracle:" in content, "docker-compose must define an 'oracle' service"


def test_docker_compose_has_admission_service():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "admission:" in content, "docker-compose must define an 'admission' service"


def test_docker_compose_oracle_has_healthcheck():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "oracle/status" in content, "oracle service must healthcheck /oracle/status"


def test_docker_compose_admission_has_healthcheck():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "admission_bridge" in content or "pradyos-admission" in content, \
        "admission service must declare a healthcheck"


# ---------------------------------------------------------------------------
# 5. docker-compose Phase 9: security hardening
# ---------------------------------------------------------------------------

def test_docker_compose_has_cap_drop():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "cap_drop" in content, "docker-compose must use cap_drop (Phase 9)"


def test_docker_compose_has_no_new_privileges():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "no-new-privileges" in content, "docker-compose must set no-new-privileges"


def test_docker_compose_has_read_only_root():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "read_only" in content, "docker-compose must set read_only: true"


def test_docker_compose_has_named_var_volume():
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "pradyos-var" in content, "docker-compose must define 'pradyos-var' volume"


# ---------------------------------------------------------------------------
# 6. CI workflow (Phase 7G)
# ---------------------------------------------------------------------------

def test_ci_workflow_exists():
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.exists(), ".github/workflows/ci.yml not found"


def test_ci_workflow_runs_prove():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "prove.py" in content


def test_ci_workflow_has_lint_job():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "lint" in content.lower()


def test_ci_workflow_has_test_job():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in content


def test_ci_workflow_triggers_on_push():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "push:" in content


# ---------------------------------------------------------------------------
# 7. Systemd units: existing three (Phase 7G baseline)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unit_name", [
    "pradyos-titan.service",
    "pradyos-warden.service",
    "pradyos-imperium.service",
])
def test_existing_systemd_units_present(unit_name: str):
    assert (SYSTEMD_DIR / unit_name).exists(), f"{unit_name} not found"


@pytest.mark.parametrize("unit_name", [
    "pradyos-warden.service",
    "pradyos-imperium.service",
])
def test_existing_systemd_units_restart_on_failure(unit_name: str):
    content = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
    assert "Restart=on-failure" in content


@pytest.mark.parametrize("unit_name", [
    "pradyos-warden.service",
    "pradyos-imperium.service",
])
def test_existing_systemd_units_no_new_privileges(unit_name: str):
    content = (SYSTEMD_DIR / unit_name).read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in content


# ---------------------------------------------------------------------------
# 8. Systemd: pradyos-oracle.service (Phase 9A)
# ---------------------------------------------------------------------------

def test_oracle_service_exists():
    assert (SYSTEMD_DIR / "pradyos-oracle.service").exists(), \
        "deploy/systemd/pradyos-oracle.service not found (Phase 9A)"


def test_oracle_service_restart_on_failure():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "Restart=on-failure" in content


def test_oracle_service_watchdog():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "WatchdogSec=" in content, "oracle.service must set WatchdogSec"


def test_oracle_service_after_imperium():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "pradyos-imperium.service" in content, \
        "oracle.service must declare After=/BindsTo= pradyos-imperium.service"


def test_oracle_service_no_new_privileges():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in content


def test_oracle_service_protect_system():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "ProtectSystem=" in content


def test_oracle_service_private_tmp():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "PrivateTmp=true" in content


def test_oracle_service_type_notify():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "Type=notify" in content or "Type=simple" in content


def test_oracle_service_non_root_user():
    content = (SYSTEMD_DIR / "pradyos-oracle.service").read_text(encoding="utf-8")
    assert "User=pradyos" in content


# ---------------------------------------------------------------------------
# 9. Systemd: pradyos-admission.service (Phase 9A)
# ---------------------------------------------------------------------------

def test_admission_service_exists():
    assert (SYSTEMD_DIR / "pradyos-admission.service").exists(), \
        "deploy/systemd/pradyos-admission.service not found (Phase 9A)"


def test_admission_service_restart_on_failure():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "Restart=on-failure" in content


def test_admission_service_after_oracle():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "pradyos-oracle.service" in content, \
        "admission.service must declare After=/BindsTo= pradyos-oracle.service"


def test_admission_service_requires_imperium():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "pradyos-imperium.service" in content, \
        "admission.service must declare Requires= pradyos-imperium.service"


def test_admission_service_no_new_privileges():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in content


def test_admission_service_protect_system():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "ProtectSystem=" in content


def test_admission_service_private_tmp():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "PrivateTmp=true" in content


def test_admission_service_non_root_user():
    content = (SYSTEMD_DIR / "pradyos-admission.service").read_text(encoding="utf-8")
    assert "User=pradyos" in content


# ---------------------------------------------------------------------------
# 10. Fleet-level dependency ordering (Phase 9A)
# ---------------------------------------------------------------------------

def test_all_five_systemd_units_present():
    units = [
        "pradyos-titan.service",
        "pradyos-warden.service",
        "pradyos-imperium.service",
        "pradyos-oracle.service",
        "pradyos-admission.service",
    ]
    missing = [u for u in units if not (SYSTEMD_DIR / u).exists()]
    assert not missing, f"Missing systemd units: {missing}"


def test_imperium_depends_on_titan_and_warden():
    content = (SYSTEMD_DIR / "pradyos-imperium.service").read_text(encoding="utf-8")
    assert "pradyos-titan.service" in content
    assert "pradyos-warden.service" in content
