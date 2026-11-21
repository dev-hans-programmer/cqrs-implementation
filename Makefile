.PHONY: install test lint typecheck up down

install:
	python -m pip install -e '.[dev]'

test:
	python -m pytest

lint:
	python -m ruff check .
	python -m ruff format --check .

typecheck:
	python -m mypy services

up:
	docker compose up --build

down:
	docker compose down

