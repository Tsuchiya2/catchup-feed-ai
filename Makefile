.PHONY: help dev test lint format run db-up db-down docker-build proto grpcurl clean

# Default target
help:
	@echo "catchup-ai Development Commands"
	@echo "================================"
	@echo "dev          - Install all dependencies (including dev)"
	@echo "test         - Run tests"
	@echo "lint         - Run linter (ruff)"
	@echo "format       - Format code (ruff)"
	@echo "run          - Start gRPC server locally"
	@echo "db-up        - Start PostgreSQL with pgvector"
	@echo "db-down      - Stop PostgreSQL"
	@echo "docker-build - Build Docker image"
	@echo "proto        - Generate Python code from proto files"
	@echo "grpcurl      - Test gRPC health check"
	@echo "notebook     - Start Jupyter notebook"
	@echo "clean        - Clean build artifacts"

# Development
dev:
	uv sync --all-extras

test:
	uv run pytest -v --cov=src/catchup_ai

lint:
	uv run ruff check src/ tests/
	uv run mypy src/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

# Run
run:
	uv run python -m catchup_ai

notebook:
	uv run jupyter notebook notebooks/

# Database
db-up:
	docker compose up -d db

db-down:
	docker compose down

# Docker
docker-build:
	docker compose build catchup-ai

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f catchup-ai

# Proto
proto:
	./scripts/generate_proto.sh

# gRPC testing (requires grpcurl: brew install grpcurl)
grpcurl:
	grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

grpcurl-embed:
	grpcurl -plaintext -d '{"article_id": 1, "title": "Test", "content": "Test content"}' \
		localhost:50051 catchup.ai.v1.ArticleAI/EmbedArticle

grpcurl-search:
	grpcurl -plaintext -d '{"query": "Rust programming", "limit": 5}' \
		localhost:50051 catchup.ai.v1.ArticleAI/SearchSimilar

# Clean
clean:
	rm -rf .venv/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf dist/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
