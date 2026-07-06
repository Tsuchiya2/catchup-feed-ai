.PHONY: help dev test lint format clean

help:
	@echo "pulse-ai Development Commands"
	@echo "============================="
	@echo "dev    - Install all dependencies (including dev)"
	@echo "test   - Run tests"
	@echo "lint   - Run linter (ruff) and type checker (mypy)"
	@echo "format - Format code (ruff)"
	@echo "clean  - Clean build artifacts"

dev:
	uv sync --all-extras

test:
	uv run pytest -v --cov=src

lint:
	uv run ruff check src/ tests/
	uv run mypy src/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

clean:
	rm -rf .venv/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf dist/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
