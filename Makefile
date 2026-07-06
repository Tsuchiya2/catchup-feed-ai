.PHONY: help dev run test lint format clean

help:
	@echo "pulse-ai Development Commands"
	@echo "============================="
	@echo "dev    - Install all dependencies (including dev)"
	@echo "run    - Run the transcribe worker (DATABASE_URL required; see .env.example)"
	@echo "test   - Run tests"
	@echo "lint   - Run linter (ruff) and type checker (mypy)"
	@echo "format - Format code (ruff)"
	@echo "clean  - Clean build artifacts"

dev:
	uv sync --all-extras

# 実運用は launchd の夜間起動(03:00)。--deadline 04:15 が既定で、
# radio(04:30)の前に新規 claim を止める。手動実行時は必要に応じて
# ARGS="--deadline HH:MM" を渡す。
run:
	uv run pulse-transcribe $(ARGS)

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
