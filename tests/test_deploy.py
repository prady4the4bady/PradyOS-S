"""Tests for Phase 7G: deploy infrastructure files.

Validates that all required deploy artifacts exist and contain
the correct content markers.  No Docker daemon is required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Root of the repository (one level up from tests/)
REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# 1. Dockerfile exists
# ---------------------------------------------------------------------------

def test_dockerfile_exists():
    dockerfile = REPO_ROOT / "deploy" / "Dockerfile"
    assert dockerfile.exists(), "deploy/Dockerfile not found"


# ---------------------------------------------------------------------------
# 2. Dockerfile has correct structure
# ---------------------------------------------------------------------------

def test_dockerfile_has_multistage_build():
    content = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:" in content, "Dockerfile must have a FROM python: base"
    assert "AS builder" in content, "Dockerfile must have a builder stage"
    assert "AS runtime" in content, "Dockerfile must have a runtime stage"


def test_dockerfile_exposes_port_8000():
    content = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8000" in content, "Dockerfile must EXPOSE 8000"


def test_dockerfile_has_healthcheck():
    content = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content, "Dockerfile must define a HEALTHCHECK"


def test_dockerfile_uses_nonroot_user():
    content = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "USER pradyos" in content or "useradd" in content, \
        "Dockerfile must create/use a non-root user"


# ---------------------------------------------------------------------------
# 3. docker-compose.yml exists and has required services
# ---------------------------------------------------------------------------

def test_docker_compose_exists():
    compose = REPO_ROOT / "deploy" / "docker-compose.yml"
    assert compose.exists(), "deploy/docker-compose.yml not found"


def test_docker_compose_has_sovereign_service():
    content = (REPO_ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "sovereign:" in content, "docker-compose must define a 'sovereign' service"


def test_docker_compose_has_volume():
    content = (REPO_ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "volumes:" in content, "docker-compose must define volumes for persistence"


# ---------------------------------------------------------------------------
# 4. GitHub Actions CI workflow exists and is valid
# ---------------------------------------------------------------------------

def test_ci_workflow_exists():
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.exists(), ".github/workflows/ci.yml not found"


def test_ci_workflow_runs_prove():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "prove.py" in content, "ci.yml must invoke scripts/prove.py"


def test_ci_workflow_has_lint_job():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "lint" in content.lower(), "ci.yml must have a lint job"


def test_ci_workflow_has_test_job():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in content, "ci.yml must run pytest"


def test_ci_workflow_triggers_on_push():
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "push:" in content, "ci.yml must trigger on push"
