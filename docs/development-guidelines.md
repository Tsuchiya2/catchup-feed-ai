# Development Guidelines

**Project**: catchup-ai
**Version**: 0.1.0
**Python**: >=3.13
**Last Updated**: 2026-01-23

This document defines the coding standards, best practices, and development workflow for the catchup-ai project.

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Project Structure](#project-structure)
3. [Coding Standards](#coding-standards)
4. [Naming Conventions](#naming-conventions)
5. [Type Hints and Type Safety](#type-hints-and-type-safety)
6. [Error Handling](#error-handling)
7. [Logging](#logging)
8. [Configuration Management](#configuration-management)
9. [Testing](#testing)
10. [gRPC Development](#grpc-development)
11. [Development Workflow](#development-workflow)
12. [Git Workflow](#git-workflow)
13. [Code Review Guidelines](#code-review-guidelines)

---

## Technology Stack

### Core Technologies

- **Language**: Python 3.13+
- **Package Manager**: [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- **gRPC**: grpcio, grpcio-tools, grpcio-health-checking
- **AI/ML**: OpenAI, Voyage AI (optional)
- **Configuration**: pydantic, pydantic-settings
- **Logging**: structlog

### Development Tools

- **Linter**: ruff (replaces flake8, isort, black)
- **Type Checker**: mypy (strict mode)
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Notebooks**: Jupyter, ipykernel
- **Container**: Docker, Docker Compose

### Architecture Pattern

Clean Architecture with layered separation:
- **API Layer** (`api/`): gRPC servicers, request/response handling
- **Core Layer** (`core/`): Domain logic, business rules, service interfaces
- **Infrastructure Layer** (`infra/`): External dependencies, configuration, gRPC clients

---

## Project Structure

```
catchup-ai/
├── src/catchup_ai/          # Main application code
│   ├── __init__.py          # Package initialization
│   ├── __main__.py          # Entry point (python -m catchup_ai)
│   ├── api/                 # API layer (gRPC servicers)
│   │   └── grpc/
│   │       ├── server.py    # gRPC server setup
│   │       ├── article_servicer.py  # ArticleAI servicer implementation
│   │       └── generated/   # Generated protobuf code (DO NOT EDIT)
│   ├── core/                # Domain logic
│   │   └── embedding/
│   │       ├── service.py   # Service interface (ABC)
│   │       ├── factory.py   # Factory pattern for service creation
│   │       ├── openai_adapter.py   # OpenAI implementation
│   │       └── voyage_adapter.py   # Voyage AI implementation
│   └── infra/               # Infrastructure layer
│       ├── config/
│       │   └── settings.py  # Pydantic settings
│       └── grpc/
│           └── embedding_client.py  # Backend gRPC client
├── proto/                   # Protocol Buffer definitions
├── tests/                   # Test suite
│   └── unit/
├── scripts/                 # Build and utility scripts
├── notebooks/               # Jupyter notebooks
├── pyproject.toml           # Project metadata and dependencies
├── Dockerfile               # Container image definition
├── compose.yml              # Docker Compose configuration
└── Makefile                 # Development commands
```

### Key Files

- **pyproject.toml**: Project metadata, dependencies, and tool configuration
- **Makefile**: Common development commands (`make help`, `make test`, `make lint`)
- **.env.example**: Template for environment variables (copy to `.env`)
- **Dockerfile**: Multi-stage build for production container
- **compose.yml**: Docker Compose for local development

### Directory Conventions

- **Generated Code**: `src/catchup_ai/api/grpc/generated/` - Never edit manually, regenerate with `make proto`
- **Tests**: Mirror source structure under `tests/` (e.g., `tests/unit/core/embedding/`)
- **Scripts**: Executable shell scripts in `scripts/` (must have `#!/bin/bash` shebang)

---

## Coding Standards

### Linter and Formatter: Ruff

All code must pass ruff checks before commit.

**Configuration** (from `pyproject.toml`):

```toml
[tool.ruff]
line-length = 100
target-version = "py313"
exclude = ["src/catchup_ai/api/grpc/generated/"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["N802"]  # PascalCase method names (required for gRPC servicers)

[tool.ruff.lint.per-file-ignores]
"*_servicer.py" = ["N802"]  # gRPC servicers override methods with PascalCase
```

**Enabled Rules**:
- **E**: pycodestyle errors
- **F**: Pyflakes
- **I**: isort (import sorting)
- **N**: pep8-naming
- **W**: pycodestyle warnings
- **UP**: pyupgrade (modern Python syntax)

**Key Standards**:
- Line length: 100 characters (not 80)
- Indentation: 4 spaces (no tabs)
- Quote style: Double quotes for strings (configurable, follow ruff's default)
- Import order: stdlib → third-party → local (automatic with ruff)

**Run Commands**:

```bash
# Check code
make lint           # Run ruff + mypy
uv run ruff check src/ tests/

# Auto-fix issues
make format         # Fix + format
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

### Type Checker: mypy

Strict type checking is enabled.

**Configuration** (from `pyproject.toml`):

```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_return_any = true
warn_unused_configs = true
```

**Requirements**:
- All functions must have type hints for parameters and return values
- Use `| None` instead of `Optional[]` (PEP 604, Python 3.10+)
- Use `list[str]` instead of `List[str]` (PEP 585)
- No `Any` types unless absolutely necessary (document why if used)

**Example** (from `openai_adapter.py`):

```python
def __init__(
    self,
    api_key: str | None = None,
    model: str | None = None,
) -> None:
    """Initialize OpenAI client."""
    settings = get_settings()
    self._api_key = api_key or settings.openai.api_key
    self._model = model or settings.openai.embedding_model
    self._client = OpenAI(api_key=self._api_key)
```

---

## Naming Conventions

### Variables and Functions

**Style**: `snake_case`

Examples from codebase:

```python
# Variables
embedding_service: EmbeddingService
api_key: str | None
max_retries: int = 3
base_delay: float

# Functions
def create_embedding_service() -> EmbeddingService:
def configure_logging() -> None:
def _calculate_retry_delay(self, attempt: int) -> float:
```

**Private Members**: Prefix with single underscore `_`

```python
# Private attributes
self._api_key = api_key
self._client = OpenAI(api_key=self._api_key)
self._logger = logger.bind(service="openai_embedding")

# Private methods
def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
def _call_api(self, texts: list[str]) -> list[EmbeddingResult]:
def _calculate_retry_delay(self, attempt: int) -> float:
```

### Classes

**Style**: `PascalCase`

Examples:

```python
class EmbeddingService(ABC):
class OpenAIEmbeddingAdapter(EmbeddingService):
class VoyageEmbeddingAdapter(EmbeddingService):
class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
class EmbeddingClient:
```

### Constants

**Style**: `UPPER_SNAKE_CASE`

While not extensively used in current codebase, follow this pattern:

```python
MAX_BATCH_SIZE = 2048
DEFAULT_TIMEOUT = 30.0
OPENAI_BATCH_LIMIT = 2048
VOYAGE_BATCH_LIMIT = 128
```

### Enums

**Style**: `PascalCase` for class, `UPPER_SNAKE_CASE` for values

Example from `settings.py`:

```python
class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
    OPENAI = "openai"
    VOYAGE = "voyage"
```

### Modules and Packages

**Style**: `snake_case`

```
catchup_ai/
├── core/
│   └── embedding/
│       ├── service.py
│       ├── factory.py
│       ├── openai_adapter.py
│       └── voyage_adapter.py
├── api/
│   └── grpc/
│       ├── server.py
│       └── article_servicer.py
└── infra/
    ├── config/
    └── grpc/
```

### gRPC Servicer Methods

**Exception**: gRPC servicers use `PascalCase` for RPC method names (ruff rule N802 is ignored for `*_servicer.py` files)

```python
class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
    def EmbedArticle(self, request, context):  # PascalCase (gRPC convention)
        """Generate embedding for an article."""
        pass

    def SearchSimilar(self, request, context):  # PascalCase (gRPC convention)
        """Search for similar articles."""
        pass
```

---

## Type Hints and Type Safety

### Modern Python Type Syntax

Use Python 3.10+ type union syntax:

```python
# ✅ GOOD (Python 3.10+)
def embed_text(self, text: str) -> EmbeddingResult:
    pass

def __init__(self, api_key: str | None = None) -> None:
    pass

results: list[EmbeddingResult] = []
client: grpc.Channel | None = None

# ❌ BAD (old syntax)
from typing import Optional, List
def __init__(self, api_key: Optional[str] = None) -> None:
    pass
results: List[EmbeddingResult] = []
```

### Dataclasses for Data Models

Use `@dataclass` for immutable data structures:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class EmbeddingResult:
    """Result of an embedding operation."""
    vector: list[float]
    model: str
    provider: str
    tokens_used: int

    @property
    def dimension(self) -> int:
        """Get the dimension of the embedding vector."""
        return len(self.vector)

@dataclass(frozen=True)
class ArticleEmbeddingInput:
    """Input for embedding an article."""
    article_id: int
    title: str
    content: str
    url: str | None = None
```

**Key Points**:
- Use `frozen=True` for immutable objects (prevents accidental modification)
- Add type hints to all fields
- Use `| None` for optional fields with `= None` default
- Add docstrings explaining the purpose of each dataclass

### Protocols for Structural Typing

Use `Protocol` for interface definitions (structural subtyping):

```python
from typing import Protocol

class EmbeddingClientProtocol(Protocol):
    """Protocol for embedding client implementations."""

    def store_embedding(
        self,
        article_id: int,
        embedding: list[float],
        embedding_type: str,
        provider: str,
        model: str,
        dimension: int,
    ) -> tuple[bool, int | None, str | None]:
        """Store an embedding in the backend."""
        ...
```

### Abstract Base Classes for Inheritance

Use `ABC` and `@abstractmethod` for inheritance-based interfaces:

```python
from abc import ABC, abstractmethod

class EmbeddingService(ABC):
    """Abstract base class for embedding services."""

    @abstractmethod
    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts (batch)."""
        pass

    def embed_article(self, article: ArticleEmbeddingInput) -> EmbeddingResult:
        """Generate embedding for an article (concrete implementation)."""
        text = article.to_text()
        return self.embed_text(text)
```

### Type Aliases

Define type aliases for complex types:

```python
# Common patterns from codebase
from grpc import ServicerContext
StubType = EmbeddingServiceStub
ResponseType = tuple[bool, int | None, str | None]
```

---

## Error Handling

### Exception Hierarchy

Define custom exceptions for domain-specific errors:

```python
class EmbeddingError(Exception):
    """Base exception for embedding errors."""
    pass

class RateLimitError(EmbeddingError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after: {retry_after}s")

class TokenLimitError(EmbeddingError):
    """Raised when text exceeds token limit."""

    def __init__(self, tokens: int, limit: int):
        self.tokens = tokens
        self.limit = limit
        super().__init__(f"Token limit exceeded: {tokens} > {limit}")
```

**Conventions**:
- Custom exceptions inherit from a base exception (e.g., `EmbeddingError`)
- Store relevant context as attributes (e.g., `retry_after`, `tokens`)
- Provide descriptive error messages in `__init__`

### Retry Logic with Exponential Backoff

Pattern from `openai_adapter.py`:

```python
def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
    """Embed texts with retry logic for transient failures."""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            return self._call_api(texts)
        except OpenAIRateLimitError as e:
            if attempt == max_retries - 1:
                raise RateLimitError() from e
            delay = self._calculate_retry_delay(attempt)
            self._logger.warning(
                "Rate limited, retrying",
                attempt=attempt + 1,
                delay=delay,
            )
            time.sleep(delay)
        except Exception as e:
            if attempt == max_retries - 1:
                raise EmbeddingError(f"Failed after {max_retries} attempts: {e}") from e
            delay = self._calculate_retry_delay(attempt)
            self._logger.warning(
                "API error, retrying",
                attempt=attempt + 1,
                delay=delay,
                error=str(e),
            )
            time.sleep(delay)

    raise EmbeddingError("Unexpected retry loop exit")

def _calculate_retry_delay(self, attempt: int) -> float:
    """Calculate delay with exponential backoff + jitter."""
    base_delay = 2 ** attempt
    max_delay = 30.0
    delay = min(base_delay, max_delay)
    return delay * random.uniform(0.5, 1.5)  # Add jitter
```

**Key Principles**:
1. **Exponential Backoff**: `2^attempt` seconds (1s, 2s, 4s, 8s, ...)
2. **Jitter**: Add randomness to prevent thundering herd (0.5x to 1.5x)
3. **Max Delay Cap**: Don't exceed 30 seconds
4. **Specific Exception Handling**: Catch specific exceptions first, then generic
5. **Re-raise on Final Attempt**: Convert to domain exception with context

### gRPC Error Handling

Pattern from `article_servicer.py`:

```python
def SearchSimilar(
    self,
    request: article_pb2.SearchSimilarRequest,
    context: grpc.ServicerContext,
) -> article_pb2.SearchSimilarResponse:
    """Search for similar articles."""
    try:
        # Business logic here
        results = self._embedding_client.search_similar(...)
        return article_pb2.SearchSimilarResponse(articles=results)

    except EmbeddingError as e:
        self._logger.error("SearchSimilar embedding failed", error=str(e))
        context.set_code(grpc.StatusCode.INTERNAL)
        context.set_details(f"Embedding generation failed: {e}")
        return article_pb2.SearchSimilarResponse()

    except Exception as e:
        self._logger.error("SearchSimilar failed", error=str(e))
        context.set_code(grpc.StatusCode.INTERNAL)
        context.set_details(str(e))
        return article_pb2.SearchSimilarResponse()
```

**gRPC Status Codes**:
- `INVALID_ARGUMENT`: Client provided invalid input
- `NOT_FOUND`: Resource not found
- `UNIMPLEMENTED`: Feature not yet implemented
- `INTERNAL`: Server-side error (use sparingly, log details)

---

## Logging

### Structured Logging with structlog

Use structlog for all logging (configured in `__main__.py`):

```python
import structlog

logger = structlog.get_logger()

# Module-level logger with bound context
logger = structlog.get_logger(__name__)

# Instance-level logger with bound context
self._logger = logger.bind(service="openai_embedding", model=self._model)
```

### Logging Configuration

From `__main__.py`:

```python
def configure_logging() -> None:
    """Configure structured logging."""
    settings = get_settings()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            # Use JSON in production, console in development
            structlog.processors.JSONRenderer()
            if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Output Format**:
- **Development**: Human-readable console output (colored)
- **Production**: JSON lines (for log aggregation)

### Logging Best Practices

**1. Use Structured Context**

```python
# ✅ GOOD: Structured fields
logger.info(
    "EmbedArticle request",
    article_id=request.article_id,
    title=request.title[:50],
    embedding_type=embedding_type,
)

logger.info(
    "Embedding generated successfully",
    article_id=request.article_id,
    dimension=result.dimension,
    provider=result.provider,
    model=result.model,
)

# ❌ BAD: String formatting
logger.info(f"EmbedArticle request for article {request.article_id}")
```

**2. Bind Context to Logger**

```python
# Bind service-level context
self._logger = logger.bind(servicer="article_ai")

# Bind request-level context
request_logger = self._logger.bind(article_id=request.article_id)
request_logger.info("Processing request")
request_logger.info("Request completed", duration_ms=duration)
```

**3. Log Levels**

- **DEBUG**: Detailed diagnostic information (e.g., API request details)
- **INFO**: General informational messages (e.g., request received, operation completed)
- **WARNING**: Warning messages (e.g., retrying after error, deprecated feature used)
- **ERROR**: Error messages (e.g., operation failed, exception caught)

Examples from codebase:

```python
# DEBUG: Diagnostic information
self._logger.debug("Calling OpenAI API", text_count=len(texts))

# INFO: Normal operations
logger.info(
    "gRPC server started",
    address=settings.grpc.address,
    environment=settings.environment,
)

# WARNING: Retryable errors
self._logger.warning(
    "Rate limited, retrying",
    attempt=attempt + 1,
    delay=delay,
)

# ERROR: Non-recoverable errors
self._logger.error(
    "Embedding failed",
    article_id=request.article_id,
    error=str(e),
)
```

**4. Never Log Sensitive Data**

```python
# ✅ GOOD: Mask sensitive data
logger.info("Client initialized", api_key_prefix=api_key[:7])

# ❌ BAD: Log sensitive data
logger.info("Client initialized", api_key=api_key)
```

---

## Configuration Management

### Pydantic Settings

All configuration is managed through `pydantic-settings` (see `infra/config/settings.py`).

**Key Principles**:
1. Environment variables take precedence over `.env` file
2. Settings are validated at startup (fail fast)
3. Settings are cached with `@lru_cache` (singleton pattern)
4. Group related settings into sub-settings classes

**Example Structure**:

```python
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class OpenAISettings(BaseSettings):
    """OpenAI API configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_")

    api_key: str = Field(default="", description="OpenAI API key")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model to use for embeddings",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if v and not v.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format")
        return v

class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    @property
    def openai(self) -> OpenAISettings:
        """OpenAI settings."""
        return OpenAISettings()

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
```

**Environment Variable Naming**:
- Main settings: `ENVIRONMENT`, `DEBUG`, `LOG_LEVEL`
- Sub-settings: Use `env_prefix` (e.g., `OPENAI_API_KEY`, `GRPC_HOST`)

**Usage**:

```python
from catchup_ai.infra.config.settings import get_settings

settings = get_settings()
api_key = settings.openai.api_key
grpc_address = settings.grpc.address
```

### Environment Files

- **.env.example**: Template with all available settings (committed to git)
- **.env**: Local overrides (NOT committed, in `.gitignore`)

**Example** (from `.env.example`):

```bash
# Environment
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO

# Embedding Provider Selection
EMBEDDING_PROVIDER=openai
EMBEDDING_DIMENSION=1536

# OpenAI Configuration
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSION=1536

# gRPC Server
GRPC_HOST=0.0.0.0
GRPC_PORT=50051
```

---

## Testing

### Testing Framework

- **Test Runner**: pytest
- **Async Support**: pytest-asyncio
- **Coverage**: pytest-cov
- **Configuration**: `[tool.pytest.ini_options]` in `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Test Organization

Mirror source structure:

```
tests/
└── unit/
    ├── core/
    │   └── embedding/
    │       ├── test_service.py
    │       ├── test_openai_adapter.py
    │       └── test_voyage_adapter.py
    ├── api/
    │   └── grpc/
    │       └── test_article_servicer.py
    └── infra/
        ├── config/
        │   └── test_settings.py
        └── grpc/
            └── test_embedding_client.py
```

### Running Tests

```bash
# Run all tests
make test
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=src/catchup_ai

# Run specific test file
uv run pytest tests/unit/core/embedding/test_openai_adapter.py

# Run tests matching pattern
uv run pytest -k "test_embed"
```

### Test Naming Conventions

- Test files: `test_<module_name>.py`
- Test functions: `test_<function_name>_<scenario>`
- Test classes: `Test<ClassName>`

**Examples**:

```python
def test_embed_text_success():
    """Test successful text embedding."""
    pass

def test_embed_text_rate_limit_error():
    """Test handling of rate limit errors."""
    pass

def test_embed_texts_batch():
    """Test batch embedding of multiple texts."""
    pass

class TestEmbeddingService:
    def test_init_with_default_settings(self):
        pass

    def test_init_with_custom_api_key(self):
        pass
```

### Testing Best Practices

**1. Use Fixtures for Setup**

```python
import pytest
from catchup_ai.infra.config.settings import Settings

@pytest.fixture
def mock_settings():
    """Provide test settings."""
    return Settings(
        environment="test",
        debug=True,
    )

@pytest.fixture
def embedding_service(mock_settings):
    """Provide embedding service with mock settings."""
    return create_embedding_service()
```

**2. Mock External Dependencies**

```python
from unittest.mock import Mock, patch

def test_embed_text_with_mock():
    with patch("openai.OpenAI") as mock_client:
        mock_client.return_value.embeddings.create.return_value = Mock(
            data=[Mock(embedding=[0.1, 0.2, 0.3])],
            model="text-embedding-3-small",
            usage=Mock(total_tokens=10),
        )

        service = OpenAIEmbeddingAdapter()
        result = service.embed_text("test")

        assert result.provider == "openai"
        assert len(result.vector) == 3
```

**3. Test Error Cases**

```python
def test_embed_text_rate_limit():
    """Test that rate limit errors are handled correctly."""
    with patch("openai.OpenAI") as mock_client:
        mock_client.return_value.embeddings.create.side_effect = OpenAIRateLimitError(
            "Rate limit exceeded"
        )

        service = OpenAIEmbeddingAdapter()

        with pytest.raises(RateLimitError):
            service.embed_text("test")
```

---

## gRPC Development

### Protocol Buffer Definitions

Proto files live in `proto/`:

```
proto/
├── article.proto              # ArticleAI service (this server)
└── embedding/
    └── embedding.proto        # EmbeddingService (backend client)
```

**Naming Conventions**:
- Service names: `PascalCase` (e.g., `ArticleAI`, `EmbeddingService`)
- RPC methods: `PascalCase` (e.g., `EmbedArticle`, `SearchSimilar`)
- Message types: `PascalCase` (e.g., `EmbedArticleRequest`, `EmbedArticleResponse`)
- Field names: `snake_case` (e.g., `article_id`, `embedding_type`)

### Generating Python Code

**Command**:

```bash
make proto
# or
./scripts/generate_proto.sh
```

**Output**: `src/catchup_ai/api/grpc/generated/`

**IMPORTANT**: Never edit generated files manually! Regenerate from proto definitions.

### Implementing gRPC Servicers

Pattern from `article_servicer.py`:

```python
import grpc
import structlog
from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc

logger = structlog.get_logger()

class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
    """gRPC servicer for ArticleAI service."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize servicer with required services."""
        self._embedding_service = embedding_service or create_embedding_service()
        self._logger = logger.bind(servicer="article_ai")

    def EmbedArticle(
        self,
        request: article_pb2.EmbedArticleRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.EmbedArticleResponse:
        """Generate embedding for an article."""
        self._logger.info(
            "EmbedArticle request",
            article_id=request.article_id,
            title=request.title[:50],
        )

        try:
            # Business logic
            result = self._embedding_service.embed_article(...)

            return article_pb2.EmbedArticleResponse(
                article_id=request.article_id,
                success=True,
                embedding=result.vector,
                provider=result.provider,
            )

        except EmbeddingError as e:
            self._logger.error("Embedding failed", error=str(e))
            return article_pb2.EmbedArticleResponse(
                article_id=request.article_id,
                success=False,
                error_message=str(e),
            )
```

**Key Points**:
- Servicer methods use `PascalCase` (gRPC convention)
- Log request details at INFO level
- Log errors at ERROR level
- Return typed response (not raw dict)
- Handle exceptions and convert to appropriate gRPC status codes

### gRPC Client Implementation

Pattern from `embedding_client.py`:

```python
import grpc
from catchup_ai.api.grpc.generated.embedding import (
    EmbeddingServiceStub,
    SearchSimilarRequest,
)

class EmbeddingClient:
    """gRPC client for backend EmbeddingService."""

    def __init__(self, settings: BackendSettings | None = None) -> None:
        self._settings = settings or get_settings().backend
        self._channel: grpc.Channel | None = None
        self._stub: EmbeddingServiceStub | None = None

    def _ensure_connection(self) -> EmbeddingServiceStub:
        """Ensure gRPC connection is established."""
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._settings.grpc_address)
            self._stub = EmbeddingServiceStub(self._channel)
        return self._stub

    def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    def search_similar(
        self,
        embedding: list[float],
        embedding_type: str,
        limit: int = 10,
    ) -> list[SimilarArticleResult]:
        """Search for similar articles."""
        stub = self._ensure_connection()

        request = SearchSimilarRequest(
            embedding=embedding,
            embedding_type=embedding_type,
            limit=limit,
        )

        try:
            response = stub.SearchSimilar(
                request,
                timeout=self._settings.grpc_timeout,
            )
            return [
                SimilarArticleResult(
                    article_id=article.article_id,
                    similarity=article.similarity,
                )
                for article in response.articles
            ]

        except grpc.RpcError as e:
            logger.error("gRPC error", error=e.code().name)
            return []
```

**Key Points**:
- Lazy connection (only connect when needed)
- Provide `close()` method for cleanup
- Support context manager (`__enter__`, `__exit__`)
- Handle `grpc.RpcError` exceptions
- Use timeout from settings

### Testing gRPC Services

**grpcurl** (command-line gRPC client):

```bash
# Install
brew install grpcurl

# Health check
make grpcurl
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Test EmbedArticle
grpcurl -plaintext -d '{"article_id": 1, "title": "Test", "content": "Test content"}' \
    localhost:50051 catchup.ai.v1.ArticleAI/EmbedArticle

# Test SearchSimilar
grpcurl -plaintext -d '{"query": "Rust programming", "limit": 5}' \
    localhost:50051 catchup.ai.v1.ArticleAI/SearchSimilar
```

---

## Development Workflow

### Initial Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd catchup-ai

# 2. Install dependencies (including dev tools)
make dev
# or
uv sync --all-extras

# 3. Copy environment template
cp .env.example .env

# 4. Edit .env with your API keys
vim .env

# 5. Generate proto code
make proto
```

### Daily Workflow

```bash
# 1. Pull latest changes
git pull origin main

# 2. Install/update dependencies (if pyproject.toml changed)
make dev

# 3. Make code changes
vim src/catchup_ai/...

# 4. Run linter and formatter
make format
make lint

# 5. Run tests
make test

# 6. Run server locally (for manual testing)
make run

# 7. Commit changes
git add .
git commit -m "feat: Add feature X"
git push origin feature-branch
```

### Common Commands

**Development**:
- `make help` - Show all available commands
- `make dev` - Install all dependencies
- `make run` - Start gRPC server locally
- `make notebook` - Start Jupyter notebook

**Testing**:
- `make test` - Run tests with coverage
- `make lint` - Run ruff + mypy
- `make format` - Format code with ruff

**Docker**:
- `make docker-build` - Build Docker image
- `make docker-up` - Start services
- `make docker-down` - Stop services
- `make docker-logs` - View logs

**gRPC**:
- `make proto` - Generate Python code from proto files
- `make grpcurl` - Test gRPC health check
- `make grpcurl-embed` - Test EmbedArticle RPC
- `make grpcurl-search` - Test SearchSimilar RPC

### Dependency Management

**Adding Dependencies**:

```bash
# Production dependency
uv add openai

# Development dependency
uv add --dev pytest

# Optional dependency group
uv add --optional voyage httpx
```

**Updating Dependencies**:

```bash
# Update all dependencies
uv sync

# Update specific package
uv add openai@latest
```

**Checking for Updates**:

```bash
# List outdated packages
uv pip list --outdated
```

---

## Git Workflow

### Branch Naming

- **Feature**: `feature/<description>` (e.g., `feature/add-voyage-provider`)
- **Bugfix**: `fix/<description>` (e.g., `fix/embedding-retry-logic`)
- **Chore**: `chore/<description>` (e.g., `chore/update-dependencies`)
- **Docs**: `docs/<description>` (e.g., `docs/update-readme`)

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring (no behavior change)
- `test`: Add or update tests
- `chore`: Maintenance tasks (dependencies, build, etc.)

**Examples**:

```bash
feat(embedding): Add Voyage AI provider support

- Implement VoyageEmbeddingAdapter
- Add Voyage settings to configuration
- Update factory to support provider switching

Closes #123

---

fix(grpc): Handle connection timeout in EmbeddingClient

Add timeout parameter to gRPC calls and handle timeout errors gracefully.

---

chore: Update dependencies to latest versions
```

### Pre-Commit Checklist

Before committing:

1. ✅ Code passes linter: `make lint`
2. ✅ Code is formatted: `make format`
3. ✅ Tests pass: `make test`
4. ✅ No sensitive data in commit (API keys, credentials)
5. ✅ Commit message follows convention
6. ✅ Changes are logically grouped

### Pull Request Workflow

1. **Create Feature Branch**:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make Changes and Commit**:
   ```bash
   git add .
   git commit -m "feat: Add my feature"
   ```

3. **Push to Remote**:
   ```bash
   git push origin feature/my-feature
   ```

4. **Create Pull Request**:
   - Title: Short description (following commit convention)
   - Description: Detailed explanation, testing notes, screenshots
   - Link related issues

5. **Address Review Comments**:
   ```bash
   # Make changes
   git add .
   git commit -m "fix: Address review comments"
   git push origin feature/my-feature
   ```

6. **Merge** (after approval):
   - Squash and merge (for clean history)
   - Delete feature branch after merge

---

## Code Review Guidelines

### For Authors

**Before Requesting Review**:
- Run `make lint` and `make test` (all must pass)
- Self-review your code (read the diff)
- Add clear PR description and testing notes
- Link related issues/tickets
- Keep PR focused (one feature/fix per PR)

**PR Description Template**:

```markdown
## Summary
Brief description of changes

## Changes
- List of changes made
- Why these changes were necessary

## Testing
- How to test these changes
- Manual testing steps (if applicable)
- Screenshot/demo (if UI changes)

## Notes
- Any breaking changes?
- Migration required?
- Dependencies updated?
```

### For Reviewers

**What to Review**:
1. **Correctness**: Does the code do what it's supposed to?
2. **Design**: Is the approach sound? Any better alternatives?
3. **Readability**: Is the code clear and well-documented?
4. **Testing**: Are there adequate tests?
5. **Error Handling**: Are edge cases handled?
6. **Performance**: Any obvious performance issues?
7. **Security**: Any security concerns?

**Review Tone**:
- Be constructive and respectful
- Ask questions rather than make demands
- Explain the "why" behind suggestions
- Acknowledge good work

**Comments**:
- 🔴 **Blocking**: Must be addressed before merge
- 🟡 **Non-blocking**: Nice-to-have, not required
- 💡 **Suggestion**: Alternative approach to consider
- ❓ **Question**: Request for clarification

---

## Additional Resources

### Documentation
- [Python Type Hints (PEP 484)](https://peps.python.org/pep-0484/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [structlog Documentation](https://www.structlog.org/)
- [gRPC Python Tutorial](https://grpc.io/docs/languages/python/)

### Tools
- [uv Documentation](https://github.com/astral-sh/uv)
- [ruff Documentation](https://docs.astral.sh/ruff/)
- [pytest Documentation](https://docs.pytest.org/)

### Project-Specific
- API Documentation: See proto files in `proto/`
- Architecture: See `docs/architecture.md` (if available)
- Product Requirements: See `docs/product-requirements.md` (if available)

---

**Last Updated**: 2026-01-23
**Maintainer**: tsuchiya-yu2 (yuji2tsuchiya@gmail.com)
