# gRPC Coding Standards for catchup-ai

## Overview

This document defines gRPC coding standards for the catchup-ai project based on actual implementation patterns. These standards ensure consistency, maintainability, and best practices across all gRPC services.

## Architecture

### Service Boundaries

```
catchup-ai (Python)              catchup-feed-backend (Go)
├─ ArticleAI Service             ├─ EmbeddingService
│  ├─ EmbedArticle               │  ├─ StoreEmbedding
│  ├─ SearchSimilar              │  ├─ GetEmbeddings
│  ├─ QueryArticles              │  ├─ SearchSimilar
│  ├─ GenerateWeeklySummary      │  └─ DeleteEmbedding
│  └─ ClassifyArticle            │
│                                 │
│  (Generates embeddings)         │  (Stores embeddings, search)
```

**Port Assignment:**
- catchup-ai: `50051`
- catchup-feed-backend: `50052` (configurable)

## 1. Proto File Organization

### Directory Structure

```
proto/
├── article.proto                    # ArticleAI service (catchup-ai server)
└── embedding/
    └── embedding.proto              # EmbeddingService (backend client)
```

**Rules:**
- Place service proto files at root: `proto/<service>.proto`
- Use subdirectories for client-consumed services: `proto/<namespace>/`
- One service per proto file
- Group related messages near the service definition

### Proto File Template

```protobuf
// Copyright 2026 catchup-feed. All rights reserved.
// <Service description> for gRPC communication.

syntax = "proto3";

package <namespace>;

option go_package = "<module_path>/proto/<namespace>";

// Service definition with descriptive comment
service <ServiceName> {
    // RPC method with purpose description
    rpc MethodName(MethodRequest) returns (MethodResponse);
}

// Message definitions with section dividers
// ============================================================================
// MethodName
// ============================================================================

message MethodRequest {
    // Field with comment explaining purpose
    int64 field_name = 1;
}

message MethodResponse {
    // Success indicator
    bool success = 1;
    // Error message if not successful
    string error_message = 2;
}
```

### Package Naming

**Pattern:** `<project>.<component>.<version>`

**Examples from codebase:**
- `catchup.ai.v1` - ArticleAI service
- `embedding` - EmbeddingService (backend)

**Version suffix:**
- Use `v1`, `v2` for API versioning
- Omit version for internal/utility services

### Service Naming

**Pattern:** `<Domain><Purpose>Service` or `<Domain><Purpose>`

**Examples:**
```protobuf
service ArticleAI { ... }        // Domain: Article, Purpose: AI operations
service EmbeddingService { ... }  // Domain: Embedding, Purpose: Management
```

**Rules:**
- Use PascalCase
- Suffix with `Service` for CRUD-like operations
- Omit `Service` suffix for domain-specific operations
- Service names should indicate capability, not implementation

### RPC Method Naming

**Pattern:** Verb + Noun/Domain

**Examples from article.proto:**
```protobuf
rpc EmbedArticle(...)           // Action: Embed, Target: Article
rpc SearchSimilar(...)          // Action: Search, Type: Similar
rpc QueryArticles(...)          // Action: Query, Target: Articles
rpc GenerateWeeklySummary(...)  // Action: Generate, Type: WeeklySummary
rpc ClassifyArticle(...)        // Action: Classify, Target: Article
```

**Examples from embedding.proto:**
```protobuf
rpc StoreEmbedding(...)         // Action: Store, Target: Embedding
rpc GetEmbeddings(...)          // Action: Get, Target: Embeddings (plural)
rpc SearchSimilar(...)          // Action: Search, Type: Similar
rpc DeleteEmbedding(...)        // Action: Delete, Target: Embedding
```

**Verbs:**
- CRUD: `Create`, `Get`, `Update`, `Delete`
- Generation: `Generate`, `Embed`, `Classify`
- Search: `Search`, `Query`, `Find`
- Batch: Use plural nouns (e.g., `GetEmbeddings`)

### Message Naming

**Pattern:** `<MethodName><Request|Response>`

**Examples:**
```protobuf
rpc EmbedArticle(EmbedArticleRequest) returns (EmbedArticleResponse);
rpc StoreEmbedding(StoreEmbeddingRequest) returns (StoreEmbeddingResponse);
```

**Shared Messages:**
```protobuf
// Domain object (no Request/Response suffix)
message SimilarArticle {
    int64 article_id = 1;
    float similarity_score = 2;
}

// Reusable utility message
message DateRange {
    string start_date = 1;
    string end_date = 2;
}
```

### Field Naming and Documentation

**Examples from codebase:**

```protobuf
message StoreEmbeddingRequest {
    // Required: ID of the article this embedding belongs to.
    // Must be a positive integer referencing an existing article.
    int64 article_id = 1;

    // Required: Type of content that was embedded.
    // Valid values: "title", "content", "summary"
    string embedding_type = 2;

    // Optional: Maximum number of results.
    // Default: 10, Maximum: 100
    int32 limit = 3;
}
```

**Documentation pattern:**
1. **Requirement level:** `Required:` or `Optional:`
2. **Purpose:** What the field represents
3. **Constraints:** Validation rules, valid values
4. **Defaults:** Default behavior if not provided

**Field naming:**
- Use `snake_case`
- Boolean fields: Use `is_*`, `has_*`, or verb form
- IDs: Always `*_id`, not `id_*`
- Counts: Use `*_count`, `max_*`, `min_*`
- Scores: Use `*_score`, `*_confidence`

### Response Message Patterns

**Standard success/error pattern:**
```protobuf
message OperationResponse {
    // True if the operation succeeded
    bool success = 1;

    // Error message if success is false
    // Empty if success is true
    string error_message = 2;

    // Operation-specific fields
    // ...
}
```

**Examples:**
- `StoreEmbeddingResponse` - Returns `success`, `embedding_id`, `error_message`
- `EmbedArticleResponse` - Returns `success`, `error_message`, plus embedding data
- `DeleteEmbeddingResponse` - Returns `success`, `deleted_count`, `error_message`

**List response pattern:**
```protobuf
message SearchResponse {
    // List of results (may be empty)
    repeated ResultItem items = 1;
}
```

### Using oneof for Variants

```protobuf
message SearchSimilarRequest {
    // Search by text query OR article ID
    oneof search_by {
        string query = 1;
        int64 article_id = 2;
    }
    int32 limit = 3;
}
```

**Usage:**
- Use `oneof` for mutually exclusive options
- Document the choice in comment above
- Name the oneof field descriptively (`search_by`, `filter_by`)

## 2. Generated Code Organization

### Directory Structure

```
src/catchup_ai/api/grpc/
├── generated/                      # Generated code (DO NOT EDIT)
│   ├── __init__.py
│   ├── article_pb2.py              # Generated messages
│   ├── article_pb2.pyi             # Type stubs
│   ├── article_pb2_grpc.py         # Generated service code
│   └── embedding/                  # Nested package for clients
│       ├── __init__.py
│       ├── embedding_pb2.py
│       ├── embedding_pb2.pyi
│       └── embedding_pb2_grpc.py
├── article_servicer.py             # Service implementation
└── server.py                       # Server setup
```

**Rules:**
- Mark `generated/` as generated code with `# Generated by ... DO NOT EDIT!`
- Create `__init__.py` exports for clean imports
- Use subdirectories for client-only proto files
- Keep servicer implementations separate from generated code

### Generated Code Init Pattern

From `src/catchup_ai/api/grpc/generated/embedding/__init__.py`:

```python
"""Generated gRPC code for backend EmbeddingService client."""

from .embedding_pb2 import (
    StoreEmbeddingRequest,
    StoreEmbeddingResponse,
    # ... all messages
)
from .embedding_pb2_grpc import (
    EmbeddingServiceStub,
    EmbeddingServiceServicer,
    add_EmbeddingServiceServicer_to_server,
)

__all__ = [
    # Messages
    "StoreEmbeddingRequest",
    # ...
    # Service
    "EmbeddingServiceStub",
    # ...
]
```

**Rules:**
- Create `__init__.py` for every proto package
- Export all messages and service classes
- Group exports with comments: `# Messages`, `# Service`
- Include docstring describing the package purpose

### Proto Generation Script

**Location:** `scripts/generate_proto.sh`

**Key patterns from actual script:**

```bash
# Generate Python code for server proto
python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --pyi_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/article.proto"

# Fix imports (grpc_tools generates absolute imports)
sed -i '' 's/^import article_pb2/from . import article_pb2/' \
    "$OUTPUT_DIR/article_pb2_grpc.py"

# For nested packages
sed -i '' 's/from embedding import embedding_pb2/from . import embedding_pb2/' \
    "$OUTPUT_DIR/embedding/embedding_pb2_grpc.py"
```

**Rules:**
- Always generate type stubs with `--pyi_out`
- Fix imports to use relative imports
- Create `__init__.py` files after generation
- Make script idempotent

## 3. Servicer Implementation Patterns

### Servicer Class Structure

From `src/catchup_ai/api/grpc/article_servicer.py`:

```python
"""gRPC Article AI Servicer implementation.

Handles incoming gRPC requests and delegates to domain services.

Architecture:
    - catchup-ai: Embedding generation (this service)
    - catchup-feed-backend: Embedding storage & similarity search

Flow:
    1. Backend calls EmbedArticle → generates embedding → returns vector
    2. Backend stores embedding in article_embeddings table
    3. For SearchSimilar, embeds query → calls backend's SearchSimilar
"""

import grpc
import structlog

from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
from catchup_ai.core.embedding import EmbeddingService, create_embedding_service
from catchup_ai.infra.config.settings import get_settings

logger = structlog.get_logger()


class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
    """gRPC servicer for ArticleAI service.

    Implements all RPC methods defined in article.proto.
    Uses factory pattern to create embedding service based on configuration.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        embedding_client: EmbeddingClient | None = None,
    ):
        """Initialize servicer with required services.

        Args:
            embedding_service: Optional embedding service. If None, creates
                               one using the factory based on configuration.
            embedding_client: Optional backend client. If None, creates one.
        """
        self._embedding_service = embedding_service or create_embedding_service()
        self._embedding_client = embedding_client or EmbeddingClient()
        self._settings = get_settings()
        self._logger = logger.bind(servicer="article_ai")
```

**Rules:**
- Inherit from generated servicer base class
- Accept optional service dependencies for testing
- Use factory functions for default dependencies
- Bind structured logger with servicer context
- Private attributes with underscore prefix
- Document architecture and flow in module docstring

### RPC Method Implementation Pattern

```python
def EmbedArticle(
    self,
    request: article_pb2.EmbedArticleRequest,
    context: grpc.ServicerContext,
) -> article_pb2.EmbedArticleResponse:
    """Generate embedding for an article.

    Note: This method generates embeddings but does NOT store them.
    The caller (backend) is responsible for storing via EmbeddingService.

    Args:
        request: EmbedArticleRequest with article data
        context: gRPC context

    Returns:
        EmbedArticleResponse with embedding vector and metadata
    """
    # 1. Extract and validate input
    embedding_type = request.embedding_type if request.embedding_type else "content"

    # 2. Log request (include trace info)
    self._logger.info(
        "EmbedArticle request",
        article_id=request.article_id,
        title=request.title[:50] if request.title else "",
        embedding_type=embedding_type,
    )

    try:
        # 3. Business logic (delegate to domain service)
        article_input = ArticleEmbeddingInput(
            article_id=request.article_id,
            title=request.title,
            content=request.content,
            url=request.url or None,
        )
        result = self._embedding_service.embed_article(article_input)

        # 4. Log success
        self._logger.info(
            "Embedding generated successfully",
            article_id=request.article_id,
            dimension=result.dimension,
            provider=result.provider,
        )

        # 5. Return response
        return article_pb2.EmbedArticleResponse(
            article_id=request.article_id,
            success=True,
            embedding_dimension=result.dimension,
            embedding=result.vector,
            provider=result.provider,
            model=result.model,
            embedding_type=embedding_type,
        )

    except EmbeddingError as e:
        # 6. Handle domain errors (return error response)
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

**Implementation pattern:**
1. **Extract input:** Get fields from request, apply defaults
2. **Log request:** Use structured logging with key fields
3. **Delegate logic:** Convert to domain objects, call service
4. **Log success:** Log result details
5. **Return response:** Build response message
6. **Handle errors:** Catch domain exceptions, return error response

### Error Handling: Status Codes vs Error Fields

**Use error response fields (success/error_message) for:**
- Business logic errors (validation, not found, etc.)
- Errors that caller should handle gracefully
- Errors where partial data can be returned

```python
except EmbeddingError as e:
    # Domain error - return error in response
    return article_pb2.EmbedArticleResponse(
        article_id=request.article_id,
        success=False,
        error_message=str(e),
    )
```

**Use gRPC status codes for:**
- Protocol errors (invalid arguments, not implemented)
- System errors (internal failures, unavailable services)
- Client errors (unauthenticated, permission denied)

```python
if request.HasField("article_id"):
    # Feature not implemented
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details("Search by article_id not yet implemented")
    return article_pb2.SearchSimilarResponse()

if not request.query and not request.article_id:
    # Client error - invalid request
    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
    context.set_details("Either query or article_id must be provided")
    return article_pb2.SearchSimilarResponse()

except Exception as e:
    # Unexpected error
    self._logger.error("Unexpected error", error=str(e))
    context.set_code(grpc.StatusCode.INTERNAL)
    context.set_details(str(e))
    return article_pb2.SearchSimilarResponse()
```

**Status code mapping:**
- `INVALID_ARGUMENT` - Client sent invalid data
- `NOT_FOUND` - Requested resource doesn't exist
- `ALREADY_EXISTS` - Resource already exists (for creates)
- `PERMISSION_DENIED` - Client lacks permission
- `UNAUTHENTICATED` - Client not authenticated
- `UNIMPLEMENTED` - Method not yet implemented
- `INTERNAL` - Server error
- `UNAVAILABLE` - Service temporarily unavailable
- `DEADLINE_EXCEEDED` - Request timeout

### Unimplemented Methods Pattern

```python
def QueryArticles(
    self,
    request: article_pb2.QueryArticlesRequest,
    context: grpc.ServicerContext,
) -> article_pb2.QueryArticlesResponse:
    """RAG-based question answering (placeholder for Week 5-6).

    Args:
        request: QueryArticlesRequest
        context: gRPC context

    Returns:
        QueryArticlesResponse
    """
    # TODO: Implement in Week 5-6 (RAG pipeline)
    self._logger.info("QueryArticles request (not yet implemented)")
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details("QueryArticles will be implemented in Week 5-6")
    return article_pb2.QueryArticlesResponse()
```

**Rules:**
- Return empty response message
- Set `UNIMPLEMENTED` status code
- Include timeline in details message
- Add TODO comment with context

## 4. Client Implementation Patterns

### Client Class Structure

From `src/catchup_ai/infra/grpc/embedding_client.py`:

```python
"""gRPC client for backend EmbeddingService.

This client communicates with catchup-feed-backend's EmbeddingService
to store embeddings and perform similarity searches.
"""

from dataclasses import dataclass
from typing import Protocol

import grpc
import structlog

from catchup_ai.api.grpc.generated.embedding import (
    EmbeddingServiceStub,
    SearchSimilarRequest,
    StoreEmbeddingRequest,
)
from catchup_ai.infra.config.settings import BackendSettings, get_settings

logger = structlog.get_logger(__name__)


@dataclass
class SimilarArticleResult:
    """Result of similarity search."""
    article_id: int
    similarity: float


class EmbeddingClientProtocol(Protocol):
    """Protocol for embedding client implementations."""

    def store_embedding(...) -> tuple[bool, int | None, str | None]:
        """Store an embedding in the backend."""
        ...


class EmbeddingClient:
    """gRPC client for backend EmbeddingService.

    Example:
        client = EmbeddingClient()
        success, embedding_id, error = client.store_embedding(
            article_id=123,
            embedding=[0.1, 0.2, ...],
            embedding_type="content",
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
        )
    """

    def __init__(self, settings: BackendSettings | None = None) -> None:
        """Initialize the embedding client.

        Args:
            settings: Backend settings. If None, uses default settings.
        """
        self._settings = settings or get_settings().backend
        self._channel: grpc.Channel | None = None
        self._stub: EmbeddingServiceStub | None = None

    def _ensure_connection(self) -> EmbeddingServiceStub:
        """Ensure gRPC connection is established."""
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._settings.grpc_address)
            self._stub = EmbeddingServiceStub(self._channel)
            logger.info(
                "Connected to backend EmbeddingService",
                address=self._settings.grpc_address,
            )
        return self._stub

    def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> "EmbeddingClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
```

**Rules:**
- Define result dataclasses for clean return types
- Define protocol for testability
- Accept optional settings for configuration
- Lazy connection initialization with `_ensure_connection()`
- Implement context manager for resource cleanup
- Log connection establishment

### Client Method Implementation

```python
def store_embedding(
    self,
    article_id: int,
    embedding: list[float],
    embedding_type: str,
    provider: str,
    model: str,
    dimension: int,
) -> tuple[bool, int | None, str | None]:
    """Store an embedding in the backend.

    Args:
        article_id: ID of the article this embedding belongs to
        embedding: The embedding vector
        embedding_type: Type of content ("title", "content", "summary")
        provider: Embedding provider ("openai", "voyage")
        model: Model name used for embedding
        dimension: Dimension of the embedding vector

    Returns:
        Tuple of (success, embedding_id, error_message)
    """
    stub = self._ensure_connection()

    # Build request
    request = StoreEmbeddingRequest(
        article_id=article_id,
        embedding_type=embedding_type,
        provider=provider,
        model=model,
        dimension=dimension,
        embedding=embedding,
    )

    try:
        # Make RPC call
        response: StoreEmbeddingResponse = stub.StoreEmbedding(
            request,
            timeout=self._settings.grpc_timeout,
        )

        # Handle success
        if response.success:
            logger.info(
                "Stored embedding successfully",
                article_id=article_id,
                embedding_id=response.embedding_id,
                embedding_type=embedding_type,
            )
            return True, response.embedding_id, None

        # Handle business error
        else:
            logger.warning(
                "Failed to store embedding",
                article_id=article_id,
                error=response.error_message,
            )
            return False, None, response.error_message

    except grpc.RpcError as e:
        # Handle RPC error
        error_msg = f"gRPC error: {e.code().name} - {e.details()}"
        logger.error(
            "gRPC error while storing embedding",
            article_id=article_id,
            error=error_msg,
        )
        return False, None, error_msg
```

**Pattern:**
1. Ensure connection with `_ensure_connection()`
2. Build request message
3. Make RPC call with timeout
4. Check response success field
5. Log success/failure
6. Return tuple or domain objects
7. Catch and handle `grpc.RpcError`

**Error handling:**
- Check `response.success` first (business errors)
- Catch `grpc.RpcError` for protocol/network errors
- Extract error details: `e.code().name` and `e.details()`
- Return structured error information

## 5. Server Setup Patterns

### Server Creation and Configuration

From `src/catchup_ai/api/grpc/server.py`:

```python
def create_server() -> grpc.Server:
    """Create and configure the gRPC server.

    Returns:
        Configured gRPC server (not yet started)
    """
    settings = get_settings()

    # Create server with thread pool
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc.max_workers),
        options=[
            ("grpc.max_send_message_length", settings.grpc.max_message_size),
            ("grpc.max_receive_message_length", settings.grpc.max_message_size),
        ],
    )

    # Register ArticleAI service
    article_servicer = ArticleAIServicer()
    article_pb2_grpc.add_ArticleAIServicer_to_server(article_servicer, server)

    # Register health check service
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Set service health status
    health_servicer.set(
        "catchup.ai.v1.ArticleAI",
        health_pb2.HealthCheckResponse.SERVING,
    )
    health_servicer.set(
        "",  # Overall server health
        health_pb2.HealthCheckResponse.SERVING,
    )

    # Add port
    server.add_insecure_port(settings.grpc.address)

    logger.info(
        "gRPC server configured",
        address=settings.grpc.address,
        max_workers=settings.grpc.max_workers,
    )

    return server
```

**Rules:**
- Create server with `ThreadPoolExecutor`
- Configure message size limits
- Register all servicers (business + health check)
- Set health status for each service
- Use insecure port for development
- Log configuration details
- Return unconfigured server (don't start in factory)

### Graceful Shutdown

```python
def serve() -> None:
    """Start the gRPC server and block until shutdown."""
    settings = get_settings()
    server = create_server()

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received", signal=signum)
        # Grace period for in-flight requests
        event = server.stop(grace=30)
        event.wait()
        logger.info("Server stopped gracefully")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Start server
    server.start()
    logger.info(
        "gRPC server started",
        address=settings.grpc.address,
        environment=settings.environment,
    )

    # Block until shutdown
    server.wait_for_termination()
```

**Rules:**
- Handle `SIGTERM` and `SIGINT` for graceful shutdown
- Use 30-second grace period for in-flight requests
- Wait for shutdown to complete
- Log startup and shutdown events
- Exit cleanly with `sys.exit(0)`

### Health Check Integration

```python
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# In server setup
health_servicer = health.HealthServicer()
health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

# Set health for each service
health_servicer.set(
    "catchup.ai.v1.ArticleAI",  # Fully qualified service name
    health_pb2.HealthCheckResponse.SERVING,
)

health_servicer.set(
    "",  # Overall server health
    health_pb2.HealthCheckResponse.SERVING,
)
```

**Testing:**
```bash
# Using grpcurl
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

## 6. Testing with grpcurl

### Makefile Integration

From `Makefile`:

```makefile
# Health check
grpcurl:
	grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Test EmbedArticle
grpcurl-embed:
	grpcurl -plaintext -d '{"article_id": 1, "title": "Test", "content": "Test content"}' \
		localhost:50051 catchup.ai.v1.ArticleAI/EmbedArticle

# Test SearchSimilar
grpcurl-search:
	grpcurl -plaintext -d '{"query": "Rust programming", "limit": 5}' \
		localhost:50051 catchup.ai.v1.ArticleAI/SearchSimilar
```

**Rules:**
- Add grpcurl targets to Makefile
- Use `-plaintext` for insecure connections
- Use `-d` for JSON request data
- Include health check target
- Test each RPC method

## 7. Logging Standards

### Structured Logging with structlog

```python
import structlog

logger = structlog.get_logger()

# In servicer __init__
self._logger = logger.bind(servicer="article_ai")

# In methods
self._logger.info(
    "EmbedArticle request",
    article_id=request.article_id,
    title=request.title[:50] if request.title else "",
    embedding_type=embedding_type,
)

self._logger.error(
    "Embedding failed",
    article_id=request.article_id,
    error=str(e),
)
```

**Rules:**
- Use structlog for structured logging
- Bind context in `__init__`: `logger.bind(servicer="...")`
- Log key request fields (IDs, types)
- Truncate long strings: `text[:50]`
- Include error details in error logs
- Log success with result details

### Log Levels

- `debug` - Detailed diagnostic information
- `info` - Request/response, normal operations
- `warning` - Business errors, retryable failures
- `error` - System errors, unrecoverable failures

**Examples:**
```python
# Request received
self._logger.info("EmbedArticle request", article_id=1)

# Business error (warning)
self._logger.warning("Failed to store embedding", error=response.error_message)

# System error
self._logger.error("gRPC error while storing embedding", error=error_msg)
```

## 8. Import Organization

### Servicer Imports

```python
# Standard library
import signal
import sys
from concurrent import futures

# Third-party
import grpc
import structlog
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# Generated code (relative import from generated package)
from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc

# Domain services (absolute import)
from catchup_ai.core.embedding import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingService,
    create_embedding_service,
)

# Infrastructure
from catchup_ai.infra.config.settings import get_settings
from catchup_ai.infra.grpc import EmbeddingClient
```

### Client Imports

```python
# Standard library
from dataclasses import dataclass
from typing import Protocol

# Third-party
import grpc
import structlog

# Generated code (relative import from embedding package)
from catchup_ai.api.grpc.generated.embedding import (
    EmbeddingServiceStub,
    SearchSimilarRequest,
    StoreEmbeddingRequest,
)

# Configuration
from catchup_ai.infra.config.settings import BackendSettings, get_settings
```

**Rules:**
- Group imports: stdlib → third-party → generated → domain → infra
- Use relative imports for generated code within package
- Use absolute imports for project code
- Sort alphabetically within groups

## Enforcement Checklist

### Proto Files
- [ ] Proto file follows template structure
- [ ] Package name uses `<project>.<component>.v<version>` pattern
- [ ] Service name is PascalCase and descriptive
- [ ] RPC methods use Verb+Noun pattern
- [ ] Message names follow `<Method><Request|Response>` pattern
- [ ] All fields have descriptive comments
- [ ] Comments include requirement level (Required/Optional)
- [ ] Comments document valid values and defaults
- [ ] Field names use snake_case
- [ ] Response messages include success/error_message pattern
- [ ] Section dividers separate RPC method groups
- [ ] Copyright header present

### Generated Code
- [ ] Generated code in `generated/` directory
- [ ] `__init__.py` exports all messages and services
- [ ] `__all__` list includes all exports
- [ ] Package docstring describes purpose
- [ ] Import fixes applied (relative imports)
- [ ] Type stubs (`.pyi`) generated

### Servicer Implementation
- [ ] Inherits from generated servicer base class
- [ ] Accepts optional dependencies for testing
- [ ] Uses structured logging with context binding
- [ ] Module docstring documents architecture
- [ ] Each RPC method follows 6-step pattern:
  1. Extract/validate input
  2. Log request
  3. Delegate to domain service
  4. Log success
  5. Return response
  6. Handle errors
- [ ] Domain errors return error response fields
- [ ] Protocol errors set gRPC status codes
- [ ] Unimplemented methods set UNIMPLEMENTED status
- [ ] Includes TODO comments with timeline

### Client Implementation
- [ ] Defines result dataclasses
- [ ] Defines protocol for interface
- [ ] Accepts optional settings
- [ ] Lazy connection with `_ensure_connection()`
- [ ] Implements context manager
- [ ] Logs connection establishment
- [ ] Methods handle both success and error responses
- [ ] Catches `grpc.RpcError` for RPC failures
- [ ] Returns structured results (tuples or dataclasses)

### Server Setup
- [ ] Factory function returns unconfigured server
- [ ] Thread pool executor configured
- [ ] Message size limits set
- [ ] All servicers registered
- [ ] Health check service registered
- [ ] Health status set for each service
- [ ] Graceful shutdown handlers registered
- [ ] 30-second grace period for shutdown
- [ ] Logs startup and shutdown events

### Testing
- [ ] grpcurl targets in Makefile
- [ ] Health check target present
- [ ] Test targets for each RPC method
- [ ] Example request data provided

### Logging
- [ ] Uses structlog
- [ ] Context bound in `__init__`
- [ ] Request logging includes key fields
- [ ] Long strings truncated
- [ ] Error logs include error details
- [ ] Success logs include result details
- [ ] Appropriate log levels used

### Imports
- [ ] Grouped: stdlib → third-party → generated → domain → infra
- [ ] Sorted alphabetically within groups
- [ ] Relative imports for generated code
- [ ] Absolute imports for project code

## References

**Actual Files:**
- Proto: `/Users/yujitsuchiya/catchup-feed-ai/proto/article.proto`
- Proto: `/Users/yujitsuchiya/catchup-feed-ai/proto/embedding/embedding.proto`
- Servicer: `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/api/grpc/article_servicer.py`
- Server: `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/api/grpc/server.py`
- Client: `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/infra/grpc/embedding_client.py`
- Script: `/Users/yujitsuchiya/catchup-feed-ai/scripts/generate_proto.sh`
- Build: `/Users/yujitsuchiya/catchup-feed-ai/Makefile`

**External:**
- gRPC Status Codes: https://grpc.io/docs/guides/error/
- Protocol Buffers Style Guide: https://protobuf.dev/programming-guides/style/
- structlog Documentation: https://www.structlog.org/
