#!/usr/bin/env bash
# PRADY OS Phase 0 bootstrap — sets up venv, installs deps, primes state dirs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PRADYOS_PYTHON:-python3}"

echo ">> Creating venv at $ROOT/.venv"
"$PY" -m venv .venv

# shellcheck disable=SC1091
source .venv/bin/activate

echo ">> Upgrading pip"
pip install --upgrade pip wheel

echo ">> Installing PRADY OS (editable, with dev extras)"
pip install -e ".[dev]"

echo ">> Priming var/ dirs"
mkdir -p var/log var/state
touch var/log/.gitkeep var/state/.gitkeep

echo ">> Running tests"
pytest -v --tb=short

echo
echo "PHASE 0 substrate ready."
echo "Sovereign Throne entrypoint:  source .venv/bin/activate && python -m pradyos.aurora_throne.app"
