.PHONY: install test lint run throne titan warden imperium clean

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
