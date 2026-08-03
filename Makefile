.PHONY: install run test lint typecheck check

install:
	python3 -m venv .venv
	.venv/bin/pip install -e '.[dev]'

run:
	.venv/bin/uvicorn verifiable_agent_runtime.api:app --reload

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

typecheck:
	.venv/bin/mypy

check: lint typecheck test
