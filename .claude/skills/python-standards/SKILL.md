# Python Coding Standards for catchup-ai

**Version**: 1.0
**Last Updated**: 2026-01-23
**Python Version**: >=3.13
**Project**: catchup-ai (Embedding, RAG, and Article Classification service)

## Overview

This document defines coding standards for the catchup-ai project based on actual code patterns extracted from the codebase. All standards are derived from real implementations, not assumptions.

## Tool Configuration

### Package Manager
- **uv**: Modern Python package manager
- Commands: `uv add`, `uv run`, `uv sync`

### Linter
- **ruff**: Fast Python linter and formatter
- Line length: 100 characters
- Target: Python 3.13
- Selected rules: E, F, I, N, W, UP
- Ignored: N802 (PascalCase method names for gRPC servicers)

### Type Checker
- **mypy**: Strict mode enabled
- Python version: 3.13
- `strict = true`, `warn_return_any = true`, `warn_unused_configs = true`

## 1. Module Documentation

### Pattern: Module-level Docstrings
Every Python module MUST start with a module-level docstring explaining its purpose.

**Example from `/src/catchup_ai/core/embedding/service.py`:**
```python
"""Embedding service interface.

Defines the contract for embedding providers (OpenAI, local models, etc.).
Uses Protocol for structural subtyping (duck typing with type hints).
"""
```

**Example from `/src/catchup_ai/infra/config/settings.py`:**
```python
"""Application settings using pydantic-settings.

Environment variables are loaded from .env file and can be overridden.
All settings are validated at startup.
"""
```

**Rules:**
- First line: Brief summary (one sentence)
- Blank line
- Optional: Detailed explanation, usage examples, architecture notes
- Triple double-quotes (`"""`)

## 2. Import Organization

### Pattern: Grouped Imports with Blank Lines

**Example from `/src/catchup_ai/core/embedding/openai_adapter.py`:**
```python
import random
import time

import structlog
from openai import OpenAI
from openai import RateLimitError as OpenAIRateLimitError

from catchup_ai.infra.config.settings import get_settings

from .service import (
    EmbeddingError,
    EmbeddingResult,
    EmbeddingService,
    RateLimitError,
)
```

**Rules:**
1. Standard library imports (no blank line between them)
2. Blank line
3. Third-party imports (e.g., `structlog`, `openai`, `grpc`)
4. Blank line
5. First-party absolute imports (e.g., `from catchup_ai.infra...`)
6. Blank line
7. Relative imports (e.g., `from .service import ...`)
8. Use parentheses for multi-line imports
9. Alphabetical order within each group

## 3. Type Hints

### Pattern: Modern Python 3.13 Type Syntax

**Use `|` for Union types (NOT `Union` from typing):**
```python
# Good (from actual code)
def __init__(
    self,
    api_key: str | None = None,
    model: str | None = None,
):
```

**Use `list[T]`, `dict[K, V]` (NOT `List`, `Dict` from typing):**
```python
# Good (from actual code)
def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
    results: list[EmbeddingResult] = []
    return results
```

**Protocol for duck typing:**
```python
# From /src/catchup_ai/infra/grpc/embedding_client.py
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

**Property return types:**
```python
# From /src/catchup_ai/core/embedding/service.py
@property
def dimension(self) -> int:
    """Get the dimension of the embedding vector."""
    return len(self.vector)
```

**Context manager types:**
```python
# From /src/catchup_ai/infra/grpc/embedding_client.py
def __enter__(self) -> "EmbeddingClient":
    """Context manager entry."""
    return self

def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
    """Context manager exit."""
    self.close()
```

## 4. Dataclasses

### Pattern: Frozen Dataclasses for Value Objects

**Example from `/src/catchup_ai/core/embedding/service.py`:**
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class EmbeddingResult:
    """Result of an embedding operation.

    Attributes:
        vector: The embedding vector
        model: The model used to generate the embedding
        provider: The provider that generated the embedding (e.g., "openai", "voyage")
        tokens_used: Number of tokens processed
    """

    vector: list[float]
    model: str
    provider: str
    tokens_used: int

    @property
    def dimension(self) -> int:
        """Get the dimension of the embedding vector."""
        return len(self.vector)
```

**Default values:**
```python
@dataclass(frozen=True)
class ArticleEmbeddingInput:
    """Input for embedding an article."""

    article_id: int
    title: str
    content: str
    url: str | None = None  # Optional field with default
```

**Mutable dataclasses:**
```python
# From /src/catchup_ai/infra/grpc/embedding_client.py
@dataclass
class SimilarArticleResult:
    """Result of similarity search."""

    article_id: int
    similarity: float
```

**Rules:**
- Use `frozen=True` for immutable value objects
- Document all attributes in the docstring
- Add computed properties when needed
- Optional fields: use `field_name: Type | None = None`

## 5. Pydantic Settings

### Pattern: BaseSettings with Validators

**Example from `/src/catchup_ai/infra/config/settings.py`:**
```python
from enum import Enum
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""

    OPENAI = "openai"
    VOYAGE = "voyage"  # Anthropic recommended provider


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
        # Allow empty string when not using OpenAI provider
        if v and not v.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format (must start with sk-)")
        return v
```

**Computed properties:**
```python
class GrpcSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRPC_")

    host: str = Field(default="0.0.0.0", description="gRPC server host")
    port: int = Field(default=50051, description="gRPC server port")

    @property
    def address(self) -> str:
        """Generate server address."""
        return f"{self.host}:{self.port}"
```

**Nested settings with caching:**
```python
from functools import lru_cache

class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def grpc(self) -> GrpcSettings:
        """gRPC settings."""
        return GrpcSettings()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()
```

## 6. Class Design

### Pattern: Abstract Base Classes

**Example from `/src/catchup_ai/core/embedding/service.py`:**
```python
from abc import ABC, abstractmethod

class EmbeddingService(ABC):
    """Abstract base class for embedding services.

    Implementations should handle:
    - API rate limiting
    - Retry logic
    - Token counting
    """

    @abstractmethod
    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with the vector and metadata

        Raises:
            EmbeddingError: If embedding fails
        """
        pass
```

### Pattern: Concrete Implementation

**Example from `/src/catchup_ai/core/embedding/openai_adapter.py`:**
```python
class OpenAIEmbeddingAdapter(EmbeddingService):
    """OpenAI implementation of EmbeddingService.

    Uses text-embedding-3-small by default (1536 dimensions).
    Handles rate limiting with exponential backoff.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, uses settings.
            model: Model name. If None, uses settings.
        """
        settings = get_settings()
        self._api_key = api_key or settings.openai.api_key
        self._model = model or settings.openai.embedding_model
        self._client = OpenAI(api_key=self._api_key)
        self._logger = logger.bind(service="openai_embedding", model=self._model)
```

**Rules:**
- Private attributes: prefix with `_`
- Initialize logger in `__init__` with bound context
- Accept optional dependencies via parameters with defaults from settings
- Document configuration source in docstring

## 7. Logging with structlog

### Pattern: Module-level Logger

**Initialize at module level:**
```python
import structlog

logger = structlog.get_logger()
```

**Bind context in `__init__`:**
```python
class OpenAIEmbeddingAdapter(EmbeddingService):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        # ...
        self._logger = logger.bind(service="openai_embedding", model=self._model)
```

**Log with structured data:**
```python
# Info with context
self._logger.info(
    "Embeddings generated",
    count=len(results),
    total_tokens=response.usage.total_tokens,
)

# Debug
self._logger.debug("Calling OpenAI API", text_count=len(texts))

# Warning with retry info
self._logger.warning(
    "Rate limited, retrying",
    attempt=attempt + 1,
    delay=delay,
)

# Error
self._logger.error(
    "Embedding failed",
    article_id=request.article_id,
    error=str(e),
)
```

**Configuration (from `/src/catchup_ai/__main__.py`):**
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

**Rules:**
- Use module-level `logger = structlog.get_logger()`
- Bind context (service name, model, etc.) in `__init__`
- Pass structured data as keyword arguments
- Message as first positional argument
- JSON in production, console in development

## 8. Error Handling

### Pattern: Custom Exception Hierarchy

**Example from `/src/catchup_ai/core/embedding/service.py`:**
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

### Pattern: Retry with Exponential Backoff

**Example from `/src/catchup_ai/core/embedding/openai_adapter.py`:**
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
    base_delay = 2**attempt
    max_delay = 30.0
    delay = min(base_delay, max_delay)
    return delay * random.uniform(0.5, 1.5)
```

**Rules:**
- Create domain-specific exception hierarchy
- Include context in exception `__init__`
- Use `raise ... from e` to preserve stack trace
- Implement retry with exponential backoff + jitter
- Log retry attempts with structured data
- Max retries: typically 3

## 9. Factory Pattern

### Pattern: Strategy Pattern with Factory Function

**Example from `/src/catchup_ai/core/embedding/factory.py`:**
```python
import structlog
from catchup_ai.infra.config.settings import EmbeddingProvider, get_settings
from .openai_adapter import OpenAIEmbeddingAdapter
from .service import EmbeddingService

logger = structlog.get_logger()


def create_embedding_service(
    provider: str | EmbeddingProvider | None = None,
) -> EmbeddingService:
    """Create an embedding service instance based on configuration.

    This factory function implements the Strategy Pattern, allowing
    the application to switch between embedding providers at runtime
    based on configuration.

    Args:
        provider: Embedding provider to use. If None, uses EMBEDDING_PROVIDER
                  from environment. Options: "openai", "voyage"

    Returns:
        An instance of EmbeddingService

    Raises:
        ValueError: If the specified provider is not supported

    Example:
        # Use configured provider (from .env)
        service = create_embedding_service()

        # Explicitly use OpenAI
        service = create_embedding_service("openai")

        # Explicitly use Voyage (Anthropic recommended)
        service = create_embedding_service("voyage")
    """
    settings = get_settings()

    # Determine provider
    if provider is None:
        provider = settings.embedding.provider
    elif isinstance(provider, str):
        provider = EmbeddingProvider(provider.lower())

    logger.info("Creating embedding service", provider=provider.value)

    # Create appropriate adapter
    if provider == EmbeddingProvider.OPENAI:
        return OpenAIEmbeddingAdapter()

    elif provider == EmbeddingProvider.VOYAGE:
        # Lazy import to avoid dependency when not using Voyage
        from .voyage_adapter import VoyageEmbeddingAdapter

        return VoyageEmbeddingAdapter()

    else:
        raise ValueError(
            f"Unsupported embedding provider: {provider}. "
            f"Supported providers: {[p.value for p in EmbeddingProvider]}"
        )


# Convenience alias
get_embedding_service = create_embedding_service
```

**Rules:**
- Factory function returns abstract interface, not concrete type
- Accept string or enum for provider selection
- Use settings as default, allow override
- Lazy import for optional dependencies
- Log factory decisions
- Raise `ValueError` for unsupported options with helpful message
- Provide usage examples in docstring

## 10. gRPC Servicer Pattern

### Pattern: Clean Architecture Servicer

**Example from `/src/catchup_ai/api/grpc/article_servicer.py`:**
```python
import grpc
import structlog

from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
from catchup_ai.core.embedding import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingService,
    create_embedding_service,
)

logger = structlog.get_logger()


class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
    """gRPC servicer for ArticleAI service.

    Implements all RPC methods defined in article.proto.
    Uses factory pattern to create embedding service based on configuration.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize servicer with required services.

        Args:
            embedding_service: Optional embedding service. If None, creates
                               one using the factory based on configuration.
        """
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
            title=request.title[:50] if request.title else "",
        )

        try:
            article_input = ArticleEmbeddingInput(
                article_id=request.article_id,
                title=request.title,
                content=request.content,
                url=request.url or None,
            )
            result = self._embedding_service.embed_article(article_input)

            self._logger.info(
                "Embedding generated successfully",
                article_id=request.article_id,
                dimension=result.dimension,
            )

            return article_pb2.EmbedArticleResponse(
                article_id=request.article_id,
                success=True,
                embedding_dimension=result.dimension,
                embedding=result.vector,
            )

        except EmbeddingError as e:
            self._logger.error(
                "Embedding failed",
                article_id=request.article_id,
                error=str(e),
            )
            return article_pb2.EmbedArticleResponse(
                article_id=request.article_id,
                success=False,
                error_message=str(e),
            )
```

**Rules:**
- Servicer class name: `<Service>Servicer`
- Inherit from generated `<Service>Servicer` base class
- Method names: PascalCase (matches protobuf, ignore N802)
- Accept optional dependencies in `__init__` for testability
- Log request start with key parameters
- Convert domain models to/from protobuf messages
- Handle domain exceptions and convert to gRPC errors
- Log success/failure with structured data
- Return success=False with error_message rather than raising for business errors

## 11. Naming Conventions

### Variables and Functions
- **snake_case** for all variables, functions, methods, and module names
- Private: prefix with `_` (e.g., `_client`, `_call_api`)
- Protected: prefix with `_` (same as private in Python)

### Classes
- **PascalCase** for class names
- Suffixes:
  - `Service`: Abstract service interfaces (e.g., `EmbeddingService`)
  - `Adapter`: Concrete implementations (e.g., `OpenAIEmbeddingAdapter`)
  - `Servicer`: gRPC servicers (e.g., `ArticleAIServicer`)
  - `Client`: gRPC clients (e.g., `EmbeddingClient`)
  - `Settings`: Configuration classes (e.g., `OpenAISettings`)
  - `Error`: Exceptions (e.g., `EmbeddingError`)
  - `Result`: Value objects for results (e.g., `EmbeddingResult`)
  - `Input`: Value objects for inputs (e.g., `ArticleEmbeddingInput`)
  - `Protocol`: Type protocols (e.g., `EmbeddingClientProtocol`)

### Constants
- **UPPER_SNAKE_CASE** for module-level constants (though not heavily used in this codebase)

### gRPC Methods
- **PascalCase** for gRPC servicer methods (e.g., `EmbedArticle`, `SearchSimilar`)
- This violates PEP 8 but is required by gRPC conventions
- Configure ruff to ignore N802 for `*_servicer.py` files

## 12. Docstring Standards

### Functions and Methods

**Format:**
```python
def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
    """Generate embeddings for multiple texts (batch).

    More efficient than calling embed_text multiple times.

    Args:
        texts: List of texts to embed

    Returns:
        List of EmbeddingResults in the same order

    Raises:
        EmbeddingError: If embedding fails
    """
```

**Sections (in order):**
1. One-line summary (imperative mood)
2. Blank line
3. Optional: Detailed explanation
4. Blank line (if detailed explanation exists)
5. `Args:` section (if parameters exist)
6. `Returns:` section (if return value)
7. `Raises:` section (if exceptions)

### Classes

**Format:**
```python
class OpenAIEmbeddingAdapter(EmbeddingService):
    """OpenAI implementation of EmbeddingService.

    Uses text-embedding-3-small by default (1536 dimensions).
    Handles rate limiting with exponential backoff.
    """
```

**Rules:**
- One-line summary
- Blank line
- Implementation details, constraints, behavior

### Dataclasses with Attributes

**Format:**
```python
@dataclass(frozen=True)
class EmbeddingResult:
    """Result of an embedding operation.

    Attributes:
        vector: The embedding vector
        model: The model used to generate the embedding
        provider: The provider that generated the embedding
        tokens_used: Number of tokens processed
    """

    vector: list[float]
    model: str
    provider: str
    tokens_used: int
```

## 13. Architecture Patterns

### Clean Architecture / Hexagonal Architecture

**Directory structure observed:**
```
src/catchup_ai/
├── core/               # Domain logic (business rules)
│   └── embedding/
│       ├── service.py       # Abstract interfaces
│       ├── factory.py       # Factory for creating services
│       ├── openai_adapter.py   # Concrete implementation
│       └── voyage_adapter.py   # Concrete implementation
├── api/                # Interface adapters (gRPC)
│   └── grpc/
│       ├── server.py        # Server setup
│       ├── article_servicer.py  # Request handler
│       └── generated/       # Auto-generated protobuf code
└── infra/              # Infrastructure (config, clients)
    ├── config/
    │   └── settings.py      # Configuration management
    └── grpc/
        └── embedding_client.py  # External service client
```

**Rules:**
- `core/`: Pure domain logic, no external dependencies
- `api/`: Adapters for incoming requests (gRPC, REST, etc.)
- `infra/`: Infrastructure concerns (config, external clients, database)
- Dependencies flow inward: `api` → `core` ← `infra`
- Use dependency injection for testability

### Adapter Pattern

**Example:**
- Interface: `EmbeddingService` (abstract base class)
- Adapters: `OpenAIEmbeddingAdapter`, `VoyageEmbeddingAdapter`
- Factory: `create_embedding_service()` selects adapter based on config

### Strategy Pattern

**Example:**
```python
# Different strategies for embedding
service = create_embedding_service(provider="openai")  # Strategy 1
service = create_embedding_service(provider="voyage")  # Strategy 2

# Both implement same interface
result = service.embed_text("Hello")  # Same interface
```

## 14. Comments and TODO Style

### TODO Comments

**Pattern from actual code:**
```python
# TODO(human): Implement retry strategy
# This function should call _call_api and handle failures
# Consider: max retries, backoff strategy, which errors to retry
```

**Format:**
- `# TODO(owner): Description`
- Multi-line TODOs: Each line starts with `#`
- Include context, considerations, or questions

### Inline Comments

**Pattern from actual code:**
```python
# Title is more important for semantic meaning
combined = f"Title: {self.title}\n\nContent: {self.content}"

# Lazy import to avoid dependency when not using Voyage
from .voyage_adapter import VoyageEmbeddingAdapter

# Grace period for in-flight requests
event = server.stop(grace=30)
```

**Rules:**
- Explain **why**, not **what**
- Place above the code it explains
- Complete sentences with proper capitalization
- No redundant comments (code should be self-documenting)

## 15. File Organization

### Module `__init__.py`

**Example from `/src/catchup_ai/core/embedding/__init__.py`:**
```python
"""Embedding module for catchup-ai.

Provides text embedding generation functionality.

Supported providers:
- OpenAI (text-embedding-3-small)
- Voyage AI (voyage-3) - Anthropic recommended

Usage:
    from catchup_ai.core.embedding import create_embedding_service

    service = create_embedding_service()
    result = service.embed_text("Hello, world!")
"""

from .factory import create_embedding_service, get_embedding_service
from .openai_adapter import OpenAIEmbeddingAdapter
from .service import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingResult,
    EmbeddingService,
    RateLimitError,
    TokenLimitError,
)

__all__ = [
    # Factory
    "create_embedding_service",
    "get_embedding_service",
    # Service interface
    "EmbeddingService",
    # ... more exports
]
```

**Rules:**
- Module docstring with usage examples
- Import public API from submodules
- Define `__all__` for explicit public API
- Group exports by category with comments
- Lazy imports for optional dependencies (in comments)

## Enforcement Checklist

Before committing code, ensure:

### Code Quality
- [ ] All files have module-level docstrings
- [ ] All public classes, functions, and methods have docstrings
- [ ] Type hints on all function signatures
- [ ] No `typing.List`, `typing.Dict`, `typing.Union` (use built-in `list`, `dict`, `|`)
- [ ] Private attributes/methods prefixed with `_`
- [ ] No lines exceed 100 characters

### Imports
- [ ] Imports organized: stdlib → third-party → first-party → relative
- [ ] Blank lines between import groups
- [ ] No unused imports

### Logging
- [ ] Module-level logger: `logger = structlog.get_logger()`
- [ ] Logger bound with context in `__init__`
- [ ] Structured logging with keyword arguments
- [ ] Appropriate log levels (debug, info, warning, error)

### Error Handling
- [ ] Domain-specific exceptions defined
- [ ] Retry logic with exponential backoff for external APIs
- [ ] Exceptions logged with structured context
- [ ] Use `raise ... from e` to preserve stack trace

### Architecture
- [ ] Domain logic in `core/` (no external dependencies)
- [ ] API adapters in `api/`
- [ ] Infrastructure in `infra/`
- [ ] Dependency injection used for testability
- [ ] Factory pattern for strategy selection

### Testing
- [ ] All public methods have tests
- [ ] Dependencies injected (not hardcoded) for mocking
- [ ] Use pytest fixtures

### Tools
- [ ] `ruff check .` passes with no errors
- [ ] `ruff format .` applied
- [ ] `mypy .` passes in strict mode
- [ ] Tests pass: `pytest`

## Quick Reference

### Commands
```bash
# Install dependencies
uv sync

# Run linter
ruff check .

# Format code
ruff format .

# Type check
mypy .

# Run tests
pytest

# Run application
uv run python -m catchup_ai
```

### Common Patterns

**Settings:**
```python
from catchup_ai.infra.config.settings import get_settings

settings = get_settings()
api_key = settings.openai.api_key
```

**Logging:**
```python
import structlog

logger = structlog.get_logger()

# In __init__
self._logger = logger.bind(service="my_service")

# Usage
self._logger.info("Action completed", count=42, status="success")
```

**Factory:**
```python
from catchup_ai.core.embedding import create_embedding_service

service = create_embedding_service()  # Uses env config
service = create_embedding_service("openai")  # Explicit provider
```

**Dataclass:**
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class MyData:
    """Immutable data class."""

    field1: str
    field2: int
    optional: str | None = None
```

**Error Handling:**
```python
max_retries = 3
for attempt in range(max_retries):
    try:
        return self._call_api()
    except SomeError as e:
        if attempt == max_retries - 1:
            raise MyError("Failed") from e
        delay = 2 ** attempt * random.uniform(0.5, 1.5)
        time.sleep(delay)
```

---

**Note**: These standards are living documentation. Update them as the codebase evolves and new patterns emerge.
