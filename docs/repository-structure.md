# Repository Structure

**Project**: catchup-ai
**Description**: AI service for catchup-feed ecosystem - Embedding generation, RAG, and Article Classification
**Architecture**: Clean Architecture (API/Core/Infrastructure layers)
**Language**: Python 3.13
**Framework**: gRPC

## Table of Contents

- [Project Overview](#project-overview)
- [Directory Tree](#directory-tree)
- [Core Directories](#core-directories)
- [Source Code Structure](#source-code-structure)
- [Configuration Files](#configuration-files)
- [Development Tools](#development-tools)
- [Module Dependencies](#module-dependencies)

---

## Project Overview

catchup-ai is a Python-based gRPC microservice that provides AI-powered features for the catchup-feed ecosystem. It follows Clean Architecture principles with clear separation between API, Core business logic, and Infrastructure layers.

**Key Responsibilities:**
- Generate embeddings for articles (text-embedding-3-small, voyage-3)
- Support multiple embedding providers (OpenAI, Voyage AI)
- Provide gRPC API for embedding generation
- Communicate with catchup-feed-backend for embedding storage
- Future: RAG-based question answering and article classification

**Architecture Note:**
- catchup-ai generates embeddings but does NOT store them
- Storage and similarity search are delegated to catchup-feed-backend via gRPC

---

## Directory Tree

```
catchup-ai/
├── src/catchup_ai/              # Main application source code
│   ├── __init__.py              # Package initialization
│   ├── __main__.py              # Application entry point
│   ├── api/                     # API layer (gRPC interfaces)
│   │   ├── grpc/                # gRPC server and servicers
│   │   │   ├── server.py        # gRPC server setup
│   │   │   ├── article_servicer.py  # ArticleAI service implementation
│   │   │   └── generated/       # Auto-generated protobuf code
│   │   │       ├── article_pb2.py
│   │   │       ├── article_pb2_grpc.py
│   │   │       └── embedding/   # Backend client protobuf
│   │   │           ├── embedding_pb2.py
│   │   │           └── embedding_pb2_grpc.py
│   │   └── __init__.py
│   ├── core/                    # Core business logic (domain layer)
│   │   ├── embedding/           # Embedding service domain
│   │   │   ├── __init__.py      # Exports public API
│   │   │   ├── service.py       # EmbeddingService interface
│   │   │   ├── factory.py       # Service factory (Strategy pattern)
│   │   │   ├── openai_adapter.py   # OpenAI implementation
│   │   │   └── voyage_adapter.py   # Voyage AI implementation
│   │   └── __init__.py
│   └── infra/                   # Infrastructure layer
│       ├── config/              # Configuration management
│       │   ├── settings.py      # Pydantic settings (env vars)
│       │   └── __init__.py
│       └── grpc/                # External gRPC clients
│           ├── embedding_client.py  # Backend EmbeddingService client
│           └── __init__.py
├── proto/                       # Protocol buffer definitions
│   ├── article.proto            # ArticleAI service (this service)
│   └── embedding/
│       └── embedding.proto      # Backend EmbeddingService (client)
├── tests/                       # Test suite
│   ├── __init__.py
│   └── unit/                    # Unit tests
│       └── __init__.py
├── scripts/                     # Utility scripts
│   └── generate_proto.sh        # Generate Python code from proto files
├── notebooks/                   # Jupyter notebooks for experiments
│   └── 01_embedding_experiments.ipynb
├── docs/                        # Documentation
│   ├── repository-structure.md  # This file
│   ├── backend-implementation-plan.md
│   ├── screenshots/             # UI verification screenshots
│   └── reports/                 # Evaluation reports
├── .claude/                     # Claude Code agent configuration
│   ├── agents/                  # Agent definitions (workers, evaluators)
│   ├── skills/                  # Reusable skills (standards, orchestration)
│   ├── CLAUDE.md                # Claude Code documentation
│   ├── agent-models.yml         # Model configuration per agent
│   └── edaf-config.yml          # EDAF workflow configuration
├── pyproject.toml               # Project metadata and dependencies
├── uv.lock                      # Dependency lock file (uv package manager)
├── Dockerfile                   # Multi-stage Docker build
├── compose.yml                  # Docker Compose for local development
├── .env.example                 # Environment variable template
├── .env                         # Environment variables (gitignored)
├── README.md                    # Project overview
└── plan.md                      # Implementation plan
```

---

## Core Directories

### `/src/catchup_ai` - Main Application Source

The main application package following Clean Architecture principles.

#### `/src/catchup_ai/api` - API Layer

**Purpose**: Handles external communication and protocol adapters.

- **`grpc/server.py`**: gRPC server setup with health checking
  - Creates server with thread pool executor
  - Registers ArticleAI servicer
  - Registers health check service
  - Handles graceful shutdown (SIGTERM, SIGINT)

- **`grpc/article_servicer.py`**: ArticleAI service implementation
  - Implements all RPC methods from article.proto
  - Delegates to core.embedding services
  - Handles gRPC context and error mapping
  - **RPCs implemented**:
    - `EmbedArticle`: Generate embedding for an article
    - `SearchSimilar`: Find similar articles (partially implemented)
    - `QueryArticles`: RAG Q&A (placeholder for Week 5-6)
    - `GenerateWeeklySummary`: Summary generation (placeholder for Week 5-6)
    - `ClassifyArticle`: Category classification (placeholder for Week 7-8)

- **`grpc/generated/`**: Auto-generated protobuf code
  - Generated by `scripts/generate_proto.sh`
  - Do NOT edit manually
  - Excluded from linting by ruff configuration

#### `/src/catchup_ai/core` - Core Business Logic

**Purpose**: Domain layer with pure business logic (no I/O, no frameworks).

- **`embedding/service.py`**: Embedding service interface
  - `EmbeddingService` abstract base class
  - `EmbeddingResult` dataclass (vector, model, provider, tokens)
  - `ArticleEmbeddingInput` dataclass (article_id, title, content, url)
  - Custom exceptions: `EmbeddingError`, `RateLimitError`, `TokenLimitError`
  - Methods:
    - `embed_text(text: str) -> EmbeddingResult`
    - `embed_texts(texts: list[str]) -> list[EmbeddingResult]`
    - `embed_article(article: ArticleEmbeddingInput) -> EmbeddingResult`
    - `embed_articles(articles: list[ArticleEmbeddingInput]) -> list[EmbeddingResult]`

- **`embedding/factory.py`**: Service factory (Strategy Pattern)
  - `create_embedding_service(provider: str | None) -> EmbeddingService`
  - Auto-detects provider from `EMBEDDING_PROVIDER` env var
  - Supports: "openai", "voyage"
  - Enables runtime provider switching without code changes

- **`embedding/openai_adapter.py`**: OpenAI implementation
  - Uses `openai` SDK
  - Model: `text-embedding-3-small` (1536 dimensions)
  - Batch size: 2048 texts per request
  - Retry logic: Exponential backoff with jitter (max 3 retries)
  - Handles `RateLimitError` with retry-after

- **`embedding/voyage_adapter.py`**: Voyage AI implementation
  - Uses `httpx` for HTTP requests (lazy import)
  - Model: `voyage-3` (1024 dimensions) - Anthropic recommended
  - Batch size: 128 texts per request
  - Retry logic: Exponential backoff with jitter (max 3 retries)
  - Base URL: `https://api.voyageai.com/v1`

#### `/src/catchup_ai/infra` - Infrastructure Layer

**Purpose**: External integrations, configuration, I/O operations.

- **`config/settings.py`**: Application configuration
  - Uses `pydantic-settings` for type-safe env var loading
  - Auto-loads from `.env` file
  - Nested settings:
    - `EmbeddingSettings`: Provider selection, dimension
    - `OpenAISettings`: API key, model, dimension, chat model
    - `VoyageSettings`: API key, model, dimension
    - `GrpcSettings`: Host, port, max workers, max message size
    - `BackendSettings`: Backend gRPC connection (host, port, timeout)
  - Cached with `@lru_cache` for singleton behavior
  - Validates API key formats (OpenAI: `sk-*`, Voyage: `pa-*`)

- **`grpc/embedding_client.py`**: Backend gRPC client
  - Connects to catchup-feed-backend's EmbeddingService
  - Methods:
    - `store_embedding(article_id, embedding, ...) -> (success, embedding_id, error)`
    - `search_similar(embedding, embedding_type, limit) -> list[SimilarArticleResult]`
  - Uses Protocol for interface definition
  - Context manager support (`__enter__`, `__exit__`)
  - Handles gRPC errors and returns structured results

### `/proto` - Protocol Buffer Definitions

**Purpose**: Define gRPC service contracts.

- **`article.proto`**: ArticleAI service (this service exposes)
  - Package: `catchup.ai.v1`
  - Service: `ArticleAI`
  - RPCs: EmbedArticle, SearchSimilar, QueryArticles, GenerateWeeklySummary, ClassifyArticle
  - Used by external clients (Go backend, frontend)

- **`embedding/embedding.proto`**: Backend EmbeddingService (this service consumes)
  - Package: `embedding`
  - Service: `EmbeddingService`
  - RPCs: StoreEmbedding, GetEmbeddings, SearchSimilar, DeleteEmbedding
  - Copy of catchup-feed-backend's proto (for client-side code generation)

### `/tests` - Test Suite

**Purpose**: Automated testing.

- **`unit/`**: Unit tests for isolated components
  - Currently empty (tests to be added)
  - Test framework: pytest with pytest-asyncio
  - Coverage: pytest-cov

### `/scripts` - Utility Scripts

**Purpose**: Development automation.

- **`generate_proto.sh`**: Generate Python code from proto files
  - Uses `grpc_tools.protoc`
  - Generates: `*_pb2.py`, `*_pb2.pyi`, `*_pb2_grpc.py`
  - Fixes import paths (absolute → relative)
  - Creates `__init__.py` for embedding subpackage

### `/notebooks` - Jupyter Notebooks

**Purpose**: Experimentation and exploration.

- **`01_embedding_experiments.ipynb`**: Embedding provider comparison
  - Tests OpenAI and Voyage embeddings
  - Compares embedding quality
  - Validates API integration

### `/docs` - Documentation

**Purpose**: Project documentation.

- **`repository-structure.md`**: This file
- **`backend-implementation-plan.md`**: Backend integration plan
- **`screenshots/`**: UI verification screenshots (Claude Code)
- **`reports/`**: Evaluation reports (EDAF)

### `/.claude` - Claude Code Agent Configuration

**Purpose**: Evaluator-Driven Agent Flow (EDAF) configuration.

- **`agents/`**: Agent definitions
  - `requirements-gatherer.md`: Phase 1 requirements gathering
  - `designer.md`: Phase 2 system design
  - `planner.md`: Phase 3 task planning
  - `workers/`: Implementation workers (backend, database, test, documentation)
  - `evaluators/`: Quality gate evaluators for each phase

- **`skills/`**: Reusable skills
  - `python-standards/`: Python coding standards
  - `grpc-standards/`: gRPC implementation standards
  - `test-standards/`: Testing standards
  - `security-standards/`: Security best practices
  - `edaf-orchestration/`: EDAF workflow orchestration
  - `edaf-evaluation/`: Evaluation patterns and scoring

- **`agent-models.yml`**: Model configuration per agent
  - Maps agent roles to Claude model versions
  - Controls cost and performance tradeoffs

- **`edaf-config.yml`**: EDAF workflow configuration
  - Defines phase gates and evaluators
  - Configures passing thresholds

---

## Configuration Files

### Root Level Configuration

#### `pyproject.toml` - Project Metadata

**Purpose**: Python project configuration and dependency management.

**Key Sections:**
- **[project]**: Metadata (name, version, description, authors)
- **[project.dependencies]**: Production dependencies
  - LLM/Embedding: `openai>=1.0.0`
  - gRPC: `grpcio`, `grpcio-tools`, `grpcio-health-checking`
  - Configuration: `pydantic`, `pydantic-settings`
  - Utilities: `python-dotenv`, `structlog`
- **[project.optional-dependencies]**:
  - `dev`: pytest, ruff, mypy, jupyter
  - `voyage`: httpx (for Voyage AI)
- **[build-system]**: Uses `uv_build` backend
- **[tool.ruff]**: Linting configuration
  - Line length: 100
  - Target: Python 3.13
  - Exclude: `src/catchup_ai/api/grpc/generated/`
  - Ignore: N802 (PascalCase method names for gRPC)
- **[tool.mypy]**: Type checking configuration
  - Strict mode enabled
- **[tool.pytest.ini_options]**: Test configuration
  - Async mode: auto

#### `uv.lock` - Dependency Lock File

**Purpose**: Lock exact versions of dependencies for reproducibility.
- Generated by `uv` package manager
- DO NOT edit manually

#### `Dockerfile` - Container Build

**Purpose**: Multi-stage Docker build for production.

**Build stages:**
1. **builder**: Install dependencies with uv
   - Base: `python:3.13-slim`
   - Installs: uv, dependencies, project
   - Uses cache mounts for faster builds

2. **runtime**: Minimal production image
   - Base: `python:3.13-slim`
   - Non-root user: `appuser:appgroup` (UID/GID 1000)
   - Copies: virtual environment, source code
   - Exposes: port 50051 (gRPC)
   - CMD: `python -m catchup_ai`

#### `compose.yml` - Local Development

**Purpose**: Docker Compose setup for local development.

**Services:**
- **catchup-ai**: Main application
  - Build: From Dockerfile
  - Environment: Development mode, debug enabled
  - Ports: 50051:50051
  - Extra hosts: `host.docker.internal` for backend connection
  - Auto-restart: unless-stopped

**Environment Variables:**
- `EMBEDDING_PROVIDER`: openai or voyage
- `OPENAI_API_KEY`: OpenAI API key
- `VOYAGE_API_KEY`: Voyage API key (optional)
- `BACKEND_GRPC_HOST`: Backend gRPC host (default: host.docker.internal)
- `BACKEND_GRPC_PORT`: Backend gRPC port (default: 50052)

#### `.env.example` - Environment Variable Template

**Purpose**: Template for `.env` file with all configuration options.

**Categories:**
1. **Environment**: ENVIRONMENT, DEBUG, LOG_LEVEL
2. **Embedding Provider**: EMBEDDING_PROVIDER, EMBEDDING_DIMENSION
3. **OpenAI**: API key, model, dimension, chat model
4. **Voyage AI**: API key, model, dimension
5. **gRPC Server**: Host, port, max workers
6. **Backend Client**: Backend gRPC host, port, timeout

**Usage:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

---

## Source Code Structure

### Clean Architecture Layers

```
┌──────────────────────────────────────┐
│         API Layer                    │
│  (gRPC Server, Servicers)            │
│  - server.py                         │
│  - article_servicer.py               │
└──────────────────────────────────────┘
             ↓ uses
┌──────────────────────────────────────┐
│      Core Business Logic             │
│  (Domain Services, Entities)         │
│  - embedding/service.py              │
│  - embedding/factory.py              │
│  - embedding/openai_adapter.py       │
│  - embedding/voyage_adapter.py       │
└──────────────────────────────────────┘
             ↓ uses
┌──────────────────────────────────────┐
│    Infrastructure Layer              │
│  (Configuration, External Services)  │
│  - config/settings.py                │
│  - grpc/embedding_client.py          │
└──────────────────────────────────────┘
```

### Key Design Patterns

#### 1. Strategy Pattern (Embedding Service)

```python
# Factory creates appropriate strategy based on config
service = create_embedding_service()  # Uses EMBEDDING_PROVIDER env var

# All strategies implement same interface
result = service.embed_text("Hello, world!")
```

**Implementations:**
- `OpenAIEmbeddingAdapter`: OpenAI text-embedding-3-small
- `VoyageEmbeddingAdapter`: Voyage AI voyage-3

**Benefits:**
- Easy provider switching without code changes
- Consistent API across providers
- Testable with mock implementations

#### 2. Adapter Pattern (External Services)

```python
# OpenAI SDK adapter
class OpenAIEmbeddingAdapter(EmbeddingService):
    def embed_text(self, text: str) -> EmbeddingResult:
        # Adapts OpenAI SDK to our interface
        response = self._client.embeddings.create(...)
        return EmbeddingResult(...)
```

**Benefits:**
- Decouples business logic from external SDKs
- Easy to replace or mock external services
- Consistent error handling

#### 3. Dependency Injection

```python
# Servicer accepts dependencies via constructor
class ArticleAIServicer:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        embedding_client: EmbeddingClient | None = None,
    ):
        self._embedding_service = embedding_service or create_embedding_service()
        self._embedding_client = embedding_client or EmbeddingClient()
```

**Benefits:**
- Testable (inject mocks)
- Flexible (inject different implementations)
- Explicit dependencies

---

## Module Dependencies

### Import Relationships

```
article_servicer.py
├── imports: core.embedding (service, factory)
├── imports: infra.grpc (embedding_client)
├── imports: infra.config (settings)
└── imports: api.grpc.generated (article_pb2, article_pb2_grpc)

embedding/factory.py
├── imports: embedding/service (EmbeddingService interface)
├── imports: embedding/openai_adapter (OpenAIEmbeddingAdapter)
├── imports: embedding/voyage_adapter (VoyageEmbeddingAdapter)
└── imports: infra.config (settings, EmbeddingProvider)

embedding/openai_adapter.py
├── imports: embedding/service (EmbeddingService, EmbeddingResult, EmbeddingError)
├── imports: infra.config (settings)
└── imports: openai (OpenAI SDK)

embedding/voyage_adapter.py
├── imports: embedding/service (EmbeddingService, EmbeddingResult, EmbeddingError)
├── imports: infra.config (settings)
└── imports: httpx (HTTP client, lazy import)

embedding_client.py
├── imports: api.grpc.generated.embedding (EmbeddingServiceStub, *Request, *Response)
└── imports: infra.config (settings, BackendSettings)

server.py
├── imports: api.grpc.article_servicer (ArticleAIServicer)
├── imports: api.grpc.generated (article_pb2_grpc)
├── imports: infra.config (settings)
└── imports: grpc, grpc_health (gRPC framework)
```

### Dependency Flow

```
External Request
      ↓
[gRPC Server] (server.py)
      ↓
[ArticleAIServicer] (article_servicer.py)
      ↓
[EmbeddingService] (factory.py → openai_adapter.py | voyage_adapter.py)
      ↓
[OpenAI API | Voyage API] (external HTTP/SDK)

For storage/search:
[ArticleAIServicer]
      ↓
[EmbeddingClient] (embedding_client.py)
      ↓
[Backend EmbeddingService] (Go gRPC service)
      ↓
[PostgreSQL + pgvector] (database)
```

### External Dependencies

**Production:**
- `openai>=1.0.0`: OpenAI SDK for embeddings and chat
- `grpcio>=1.60.0`: gRPC framework
- `grpcio-tools>=1.60.0`: Protobuf compiler
- `grpcio-health-checking>=1.60.0`: Health check service
- `pydantic>=2.0.0`: Data validation
- `pydantic-settings>=2.0.0`: Settings management
- `python-dotenv>=1.0.0`: .env file loading
- `structlog>=24.0.0`: Structured logging

**Optional:**
- `httpx>=0.27.0`: HTTP client for Voyage AI (installed with `uv add --optional voyage`)

**Development:**
- `pytest>=8.0.0`: Test framework
- `pytest-asyncio>=0.23.0`: Async test support
- `pytest-cov>=5.0.0`: Coverage reporting
- `ruff>=0.4.0`: Linting and formatting
- `mypy>=1.10.0`: Static type checking
- `jupyter>=1.0.0`: Notebooks
- `ipykernel>=6.0.0`: Jupyter kernel

---

## Development Tools

### Package Management: uv

```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --dev

# Install with Voyage support
uv sync --extra voyage

# Add new dependency
uv add package-name

# Add dev dependency
uv add --dev package-name

# Update dependencies
uv sync --upgrade
```

### Code Quality

```bash
# Linting and formatting
ruff check src/
ruff format src/

# Type checking
mypy src/

# Run tests
pytest

# Run tests with coverage
pytest --cov=catchup_ai --cov-report=term-missing
```

### gRPC Code Generation

```bash
# Generate Python code from proto files
./scripts/generate_proto.sh

# Generated files (do not edit):
# - src/catchup_ai/api/grpc/generated/article_pb2.py
# - src/catchup_ai/api/grpc/generated/article_pb2_grpc.py
# - src/catchup_ai/api/grpc/generated/embedding/embedding_pb2.py
# - src/catchup_ai/api/grpc/generated/embedding/embedding_pb2_grpc.py
```

### Running the Application

```bash
# Local development (with .env file)
uv run python -m catchup_ai

# Docker Compose
docker compose up -d

# Docker build and run manually
docker build -t catchup-ai .
docker run -p 50051:50051 --env-file .env catchup-ai
```

### Jupyter Notebooks

```bash
# Start Jupyter server
uv run jupyter notebook

# Open notebooks/01_embedding_experiments.ipynb
```

---

## Notes

### Code Generation

- **Proto files**: Source of truth for gRPC contracts
- **Generated code**: Auto-generated by `scripts/generate_proto.sh`
- **DO NOT edit**: `src/catchup_ai/api/grpc/generated/**/*.py`
- **Excluded from linting**: Set in `pyproject.toml` ruff configuration

### Environment Variables

- **Development**: Use `.env` file (gitignored)
- **Production**: Set via Docker Compose, Kubernetes secrets, or environment
- **Template**: `.env.example` contains all available options
- **Validation**: Pydantic validates on startup (fails fast on misconfiguration)

### Architecture Boundaries

- **API Layer**: Only knows about gRPC and Core
- **Core Layer**: Pure business logic, no I/O
- **Infrastructure Layer**: Only used by API and Core for external integrations
- **No circular dependencies**: Enforced by Clean Architecture

### Testing Strategy

- **Unit tests**: Test core business logic in isolation
- **Integration tests**: Test API with mock backend
- **E2E tests**: Test full stack with real backend (future)

### Security Considerations

- **Non-root user**: Docker runs as `appuser` (UID 1000)
- **API keys**: Never commit to git (use .env, gitignored)
- **Input validation**: Pydantic validates all inputs
- **gRPC security**: Currently insecure (TLS to be added in production)

### Future Additions

- **`src/catchup_ai/core/rag/`**: RAG pipeline (Week 5-6)
- **`src/catchup_ai/core/classification/`**: Article classification (Week 7-8)
- **`tests/integration/`**: Integration tests
- **`tests/e2e/`**: End-to-end tests

---

**Document Version**: 1.0
**Last Updated**: 2026-01-23
**Maintained by**: Documentation Worker Agent
