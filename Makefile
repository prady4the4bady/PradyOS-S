.PHONY: install test lint format run throne titan warden imperium clean iso vm verify-os

install:
	python3 -m pip install -e ".[dev]"

test:
	pytest -v --tb=short

lint:
	ruff check pradyos tests
	ruff format --check pradyos tests

format:
	ruff format pradyos tests
	ruff check --fix pradyos tests

run:
	python -m pradyos.service

throne:
	python -m pradyos.aurora_throne.app

titan:
	python -m pradyos.titan_ops.daemon

warden:
	python -m pradyos.warden_grid.monitor

imperium:
	python -m pradyos.imperium.kernel

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# ---- OS image pipeline (see docs/BUILD_PIPELINE.md) ----
# Build the bootable Sovereign Edition ISO (needs root: debootstrap/chroot).
iso:
	sudo bash scripts/build_iso.sh

# Run the built ISO interactively in QEMU (dashboard on http://localhost:8000).
vm:
	bash scripts/run_vm.sh

# Automated OS-image integration test: boot the ISO headless, gate on the
# in-guest selftest + host-side API probes.
verify-os:
	bash scripts/verify_boot.sh
