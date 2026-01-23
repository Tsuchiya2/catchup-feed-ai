# Architecture Documentation

## Table of Contents
- [System Overview](#system-overview)
- [Architecture Pattern](#architecture-pattern)
- [Component Architecture](#component-architecture)
- [Technology Stack](#technology-stack)
- [Design Decisions](#design-decisions)
- [Data Flow](#data-flow)
- [Deployment Architecture](#deployment-architecture)
- [Integration Points](#integration-points)
- [Security Considerations](#security-considerations)

---

## System Overview

**catchup-ai** is a pure AI service within the catchup-feed ecosystem, responsible for generating embeddings, performing semantic search, and (future) RAG-based question answering and article classification. It operates as a stateless microservice with no database, delegating all persistence operations to the catchup-feed-backend Go service.

### Core Responsibilities
- **Embedding Generation**: Convert article text to vector embeddings using OpenAI or Voyage AI
- **Semantic Search**: Find similar articles based on query embeddings
- **RAG Pipeline**: (Week 5-6) Question answering over articles
- **Classification**: (Week 7-8) Categorize articles using fine-tuned models

### Key Characteristics
- **Stateless**: No database, no persistence layer
- **gRPC-based**: High-performance binary protocol for inter-service communication
- **Provider-agnostic**: Supports multiple embedding providers via adapter pattern
- **Containerized**: Docker-based deployment with multi-stage builds

---

## Architecture Pattern

### Clean Architecture (Layered + Dependency Inversion)

```
┌─────────────────────────────────────────────────────────────┐
│                     API Layer (Interface)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  ArticleAIServicer (gRPC)                             │  │
│  │  - EmbedArticle()                                      │  │
│  │  - SearchSimilar()                                     │  │
│  │  - QueryArticles() [future]                            │  │
│  │  - ClassifyArticle() [future]                          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Layer (Domain)                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  EmbeddingService (ABC)                               │  │
│  │  - embed_text()                                        │  │
│  │  - embed_texts()                                       │  │
│  │  - embed_article()                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Factory Pattern                                       │  │
│  │  create_embedding_service(provider) → EmbeddingService │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Infrastructure Layer (Adapters)                │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │ OpenAIEmbedding     │  │ VoyageEmbedding             │  │
│  │ Adapter             │  │ Adapter                     │  │
│  │ - text-embedding-   │  │ - voyage-3                  │  │
│  │   3-small           │  │ - Anthropic recommended     │  │
│  │ - 1536 dimensions   │  │ - 1024 dimensions           │  │
│  │ - Retry + backoff   │  │ - Retry + backoff           │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  EmbeddingClient (gRPC Client)                        │  │
│  │  - Calls catchup-feed-backend                         │  │
│  │  - store_embedding()                                   │  │
│  │  - search_similar()                                    │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Configuration (Pydantic Settings)                    │  │
│  │  - Environment-based config                           │  │
│  │  - Validation at startup                              │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Layered Architecture Principles

1. **API Layer**: Handles protocol-level concerns (gRPC marshalling, error codes)
2. **Core Layer**: Business logic and domain models (provider-agnostic)
3. **Infrastructure Layer**: External integrations (OpenAI, Voyage, backend gRPC)

**Dependency Flow**: API → Core → Infrastructure (dependencies point inward)

---

## Component Architecture

### Ecosystem Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     catchup-feed Ecosystem                       │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  catchup-feed   │         │   catchup-ai    │         │  External APIs  │
│    -backend     │  gRPC   │  (This Service) │  HTTPS  │                 │
│   (Go Service)  │◄───────►│  (Python gRPC)  │────────►│  - OpenAI API   │
│                 │ :50052  │                 │         │  - Voyage AI    │
│  - Article CRUD │         │  - Embedding    │         │                 │
│  - Feed mgmt    │         │    Generation   │         └─────────────────┘
│  - User mgmt    │         │  - Similarity   │
│  - Storage      │         │    Search       │
└────────┬────────┘         └─────────────────┘
         │
         │ TCP
         ▼
┌─────────────────┐
│   PostgreSQL    │
│   + pgvector    │
│                 │
│  - articles     │
│  - embeddings   │
│  - users        │
│  - feeds        │
└─────────────────┘
```

### Internal Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         catchup-ai                               │
│                        (port 50051)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    gRPC Server                            │  │
│  │  - ThreadPoolExecutor (10 workers)                        │  │
│  │  - Health Check Service                                   │  │
│  │  - Graceful Shutdown (30s grace)                          │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼─────────────────────────────────────┐  │
│  │           ArticleAIServicer                               │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │ EmbedArticle                                        │  │  │
│  │  │  1. Receive article (id, title, content, url)      │  │  │
│  │  │  2. Format text for embedding                       │  │  │
│  │  │  3. Call embedding service                          │  │  │
│  │  │  4. Return vector to caller                         │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │ SearchSimilar                                       │  │  │
│  │  │  1. Receive query text or article_id               │  │  │
│  │  │  2. Generate query embedding                        │  │  │
│  │  │  3. Call backend's SearchSimilar via EmbeddingClient│  │  │
│  │  │  4. Return article IDs + similarity scores          │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼─────────────────────────────────────┐  │
│  │         EmbeddingService (Factory-created)                │  │
│  │  ┌──────────────────┐    ┌──────────────────────────┐   │  │
│  │  │ OpenAIAdapter    │    │ VoyageAdapter            │   │  │
│  │  │ - API client     │ OR │ - httpx client           │   │  │
│  │  │ - Retry logic    │    │ - Retry logic            │   │  │
│  │  │ - Batch support  │    │ - Batch support          │   │  │
│  │  │ - 2048/batch max │    │ - 128/batch max          │   │  │
│  │  └──────────────────┘    └──────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         EmbeddingClient (Backend gRPC Client)             │  │
│  │  - Connects to catchup-feed-backend:50052                 │  │
│  │  - StoreEmbedding(article_id, vector, metadata)          │  │
│  │  - SearchSimilar(query_vector, limit)                     │  │
│  │  - GetEmbeddings(article_id)                              │  │
│  │  - DeleteEmbedding(article_id)                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Configuration (Pydantic)                     │  │
│  │  - Settings loaded from .env                              │  │
│  │  - Validated at startup                                   │  │
│  │  - Cached with lru_cache                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Language & Runtime
- **Python 3.13**: Modern type hints, improved performance
- **uv**: Fast Python package installer and resolver
- **structlog**: Structured logging for observability

### Communication Protocol
- **gRPC**: High-performance RPC framework
  - Binary protocol (Protocol Buffers)
  - HTTP/2-based
  - Built-in health checking
  - Language-agnostic (Python ↔ Go interop)

### AI & Embedding Providers
- **OpenAI**: text-embedding-3-small (1536 dimensions)
- **Voyage AI**: voyage-3 (1024 dimensions, Anthropic recommended)

### Configuration & Validation
- **Pydantic v2**: Runtime type validation
- **pydantic-settings**: Environment-based configuration
- **python-dotenv**: .env file loading

### Development Tools
- **Ruff**: Fast Python linter and formatter
- **mypy**: Static type checking
- **pytest**: Testing framework with coverage support
- **Docker**: Multi-stage builds for production

---

## Design Decisions

### 1. Pure AI Service (No Database)

**Decision**: catchup-ai has no database; all persistence delegated to backend.

**Rationale**:
- **Separation of Concerns**: AI logic separated from data storage
- **Scalability**: Stateless services scale horizontally easily
- **Single Source of Truth**: Backend owns all data, preventing consistency issues
- **Simplified Operations**: No database migrations, backups in AI service

**Trade-offs**:
- Network latency for backend calls
- Cannot query embeddings directly (must go through backend)

### 2. Factory Pattern for Embedding Providers

**Decision**: Use factory pattern to create embedding service based on configuration.

**Implementation**:
```python
# src/catchup_ai/core/embedding/factory.py
def create_embedding_service(provider: str | None = None) -> EmbeddingService:
    if provider == "openai":
        return OpenAIEmbeddingAdapter()
    elif provider == "voyage":
        return VoyageEmbeddingAdapter()
```

**Rationale**:
- **Provider Flexibility**: Switch between OpenAI and Voyage AI without code changes
- **Testability**: Easy to inject mock services for testing
- **Extensibility**: Add new providers by implementing EmbeddingService interface

**Configuration-driven**:
```bash
# .env
EMBEDDING_PROVIDER=openai  # or "voyage"
```

### 3. Adapter Pattern for External APIs

**Decision**: Wrap external APIs (OpenAI, Voyage) in adapter classes implementing common interface.

**Interface**:
```python
class EmbeddingService(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> EmbeddingResult: ...

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]: ...
```

**Adapters**:
- `OpenAIEmbeddingAdapter`: Wraps OpenAI client
- `VoyageEmbeddingAdapter`: Wraps httpx client for Voyage AI

**Rationale**:
- **Consistent Interface**: Same API regardless of provider
- **Error Handling**: Standardized retry logic and error types
- **Rate Limiting**: Exponential backoff with jitter in all adapters

### 4. gRPC for Service Communication

**Decision**: Use gRPC instead of REST for inter-service communication.

**Rationale**:
- **Performance**: Binary protocol faster than JSON
- **Type Safety**: Protocol Buffers provide schema validation
- **Bi-directional Streaming**: Supports future real-time features
- **Language Agnostic**: Python ↔ Go interop without serialization issues

**Proto Definitions**:
- `proto/article.proto`: catchup-ai's API (exposed to backend)
- `proto/embedding/embedding.proto`: backend's API (consumed by catchup-ai)

### 5. Retry Logic with Exponential Backoff

**Decision**: Implement retry mechanism for transient API failures.

**Implementation**:
```python
def _calculate_retry_delay(self, attempt: int) -> float:
    base_delay = 2 ** attempt  # Exponential: 1s, 2s, 4s, 8s...
    max_delay = 30.0           # Cap at 30 seconds
    jitter = random.uniform(0.5, 1.5)  # Prevent thundering herd
    return min(base_delay, max_delay) * jitter
```

**Rationale**:
- **Transient Failures**: Network issues, rate limits
- **Thundering Herd**: Jitter prevents synchronized retries
- **Bounded Retries**: Max 3 attempts with 30s cap

### 6. Multi-stage Docker Build

**Decision**: Use multi-stage Dockerfile with builder and runtime stages.

**Implementation**:
```dockerfile
FROM python:3.13-slim AS builder
# Install dependencies with uv

FROM python:3.13-slim AS runtime
# Copy only .venv and source code
```

**Rationale**:
- **Image Size**: Runtime image excludes build tools (30% smaller)
- **Security**: Non-root user, minimal attack surface
- **Build Cache**: Dependencies cached separately from source

### 7. Pydantic for Configuration Management

**Decision**: Use pydantic-settings for environment-based configuration.

**Benefits**:
- **Type Validation**: Invalid config fails at startup
- **Auto-loading**: Reads from .env automatically
- **Nested Settings**: Organized by concern (OpenAI, Voyage, gRPC)
- **Caching**: Settings loaded once with lru_cache

**Example**:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    @property
    def embedding(self) -> EmbeddingSettings: ...

    @property
    def openai(self) -> OpenAISettings: ...
```

---

## Data Flow

### 1. EmbedArticle Flow

```
┌──────────────┐
│   Backend    │
│  (Go gRPC)   │
└──────┬───────┘
       │
       │ 1. EmbedArticle(article_id, title, content, url)
       │    embedding_type="content"
       ▼
┌──────────────────────────────────────────────────────────────┐
│                     catchup-ai                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ArticleAIServicer.EmbedArticle()                        │  │
│  │  1. Create ArticleEmbeddingInput                        │  │
│  │     - Combine: "Title: {title}\n\nContent: {content}"  │  │
│  │     - Truncate to 8000 chars if needed                 │  │
│  └─────────────────────┬──────────────────────────────────┘  │
│                        │                                        │
│                        ▼                                        │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ EmbeddingService (OpenAI or Voyage)                    │   │
│  │  1. Call API: embeddings.create(input=text, model=...) │   │
│  │  2. Retry with backoff if rate limited                 │   │
│  │  3. Return EmbeddingResult(vector, model, provider)    │   │
│  └─────────────────────┬──────────────────────────────────┘   │
│                        │                                        │
└────────────────────────┼────────────────────────────────────────┘
                         │
                         │ 2. Return EmbedArticleResponse
                         │    - article_id
                         │    - embedding: [0.123, 0.456, ...]
                         │    - dimension: 1536
                         │    - provider: "openai"
                         │    - model: "text-embedding-3-small"
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Backend (Go gRPC Server)                        │
│  1. Receive embedding vector from catchup-ai                 │
│  2. Call own EmbeddingService.StoreEmbedding()              │
│  3. Store in PostgreSQL article_embeddings table             │
│     INSERT INTO article_embeddings (                         │
│       article_id, embedding_type, provider, model,           │
│       dimension, embedding                                   │
│     ) VALUES ($1, $2, $3, $4, $5, $6::vector)               │
└──────────────────────────────────────────────────────────────┘
```

### 2. SearchSimilar Flow

```
┌──────────────┐
│   Backend    │
│  (Go gRPC)   │
└──────┬───────┘
       │
       │ 1. SearchSimilar(query="Rust programming", limit=5)
       ▼
┌──────────────────────────────────────────────────────────────┐
│                     catchup-ai                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ArticleAIServicer.SearchSimilar()                       │  │
│  │  1. Validate request (query or article_id)             │  │
│  └─────────────────────┬──────────────────────────────────┘  │
│                        │                                        │
│                        ▼                                        │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ EmbeddingService.embed_text(query)                     │   │
│  │  1. Generate embedding for query text                  │   │
│  │  2. Return query_vector: [0.111, 0.222, ...]          │   │
│  └─────────────────────┬──────────────────────────────────┘   │
│                        │                                        │
│                        ▼                                        │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ EmbeddingClient.search_similar()                       │   │
│  │  - Call backend's EmbeddingService.SearchSimilar       │   │
│  │  - Pass query_vector and limit                         │   │
│  └─────────────────────┬──────────────────────────────────┘   │
└────────────────────────┼────────────────────────────────────────┘
                         │
                         │ 2. gRPC call to backend:50052
                         ▼
┌──────────────────────────────────────────────────────────────┐
│         Backend EmbeddingService (Go gRPC)                   │
│  1. Receive SearchSimilarRequest                             │
│     - embedding: [0.111, 0.222, ...]                         │
│     - embedding_type: "content"                              │
│     - limit: 5                                               │
│                                                              │
│  2. Query PostgreSQL with pgvector                           │
│     SELECT article_id,                                       │
│            1 - (embedding <=> $1::vector) AS similarity      │
│     FROM article_embeddings                                  │
│     WHERE embedding_type = $2                                │
│     ORDER BY embedding <=> $1::vector                        │
│     LIMIT $3                                                 │
│                                                              │
│  3. Return SearchSimilarResponse                             │
│     - articles: [{article_id: 42, similarity: 0.89}, ...]   │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   │ 3. Return results to catchup-ai
                   ▼
┌──────────────────────────────────────────────────────────────┐
│         catchup-ai ArticleAIServicer                         │
│  1. Receive SimilarArticle results                           │
│  2. Convert to SearchSimilarResponse                         │
│  3. Return to original caller (backend)                      │
│     Note: title, url, snippet not available                  │
│           (backend must fetch separately)                    │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   │ 4. Return SearchSimilarResponse
                   ▼
┌──────────────┐
│   Backend    │
│  (Go gRPC)   │
└──────────────┘
```

### 3. Embedding Storage Flow (Backend-initiated)

```
┌──────────────┐
│   Backend    │  (After receiving embedding from catchup-ai)
└──────┬───────┘
       │
       │ 1. Call own EmbeddingService.StoreEmbedding()
       │    (Backend is gRPC client to itself)
       ▼
┌──────────────────────────────────────────────────────┐
│     Backend EmbeddingService (Go gRPC Server)        │
│  ┌────────────────────────────────────────────────┐  │
│  │ StoreEmbedding()                               │  │
│  │  1. Validate request                           │  │
│  │  2. Check if embedding exists (upsert logic)   │  │
│  │  3. INSERT or UPDATE article_embeddings        │  │
│  └────────────────────────────────────────────────┘  │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│         PostgreSQL + pgvector Extension              │
│  ┌────────────────────────────────────────────────┐  │
│  │ article_embeddings table                       │  │
│  │ ┌──────────────────────────────────────────┐  │  │
│  │ │ id (bigserial)                            │  │  │
│  │ │ article_id (bigint, FK)                   │  │  │
│  │ │ embedding_type (text)                     │  │  │
│  │ │ provider (text) "openai" | "voyage"       │  │  │
│  │ │ model (text) "text-embedding-3-small"     │  │  │
│  │ │ dimension (int) 1536 | 1024               │  │  │
│  │ │ embedding (vector)  ← pgvector type       │  │  │
│  │ │ created_at (timestamptz)                  │  │  │
│  │ │ updated_at (timestamptz)                  │  │  │
│  │ └──────────────────────────────────────────┘  │  │
│  │                                                │  │
│  │ Indexes:                                       │  │
│  │ - (article_id, embedding_type, provider, model)│  │
│  │   → UNIQUE constraint                          │  │
│  │ - embedding vector_cosine_ops                  │  │
│  │   → HNSW index for similarity search           │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## Deployment Architecture

### Local Development

```
┌─────────────────────────────────────────────────────────────┐
│                    Developer Machine                         │
│                                                              │
│  ┌──────────────────────┐         ┌──────────────────────┐ │
│  │   catchup-ai         │  gRPC   │ catchup-feed-backend │ │
│  │   (Python venv)      │◄───────►│   (Go binary)        │ │
│  │   localhost:50051    │         │   localhost:50052    │ │
│  └──────────────────────┘         └───────────┬──────────┘ │
│                                                │             │
│                                                │ TCP         │
│                                                ▼             │
│                                    ┌──────────────────────┐ │
│                                    │   PostgreSQL         │ │
│                                    │   + pgvector         │ │
│                                    │   localhost:5432     │ │
│                                    └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

Commands:
  make run              # Start catchup-ai
  make db-up            # Start PostgreSQL (if using docker compose)
```

### Docker Compose (Local)

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                           │
│                                                              │
│  ┌──────────────────────┐         ┌──────────────────────┐ │
│  │   catchup-ai         │  gRPC   │ catchup-feed-backend │ │
│  │   (Container)        │◄───────►│   (Container)        │ │
│  │   0.0.0.0:50051      │         │   0.0.0.0:50052      │ │
│  │                      │         │                      │ │
│  │ ENV:                 │         │ ENV:                 │ │
│  │ - EMBEDDING_PROVIDER │         │ - DB_HOST=postgres   │ │
│  │ - OPENAI_API_KEY     │         │ - DB_PORT=5432       │ │
│  │ - BACKEND_GRPC_HOST  │         │                      │ │
│  │   =host.docker.      │         │                      │ │
│  │   internal           │         │                      │ │
│  └──────────────────────┘         └───────────┬──────────┘ │
│                                                │             │
│                                                │ TCP         │
│                                                ▼             │
│                                    ┌──────────────────────┐ │
│                                    │   postgres           │ │
│                                    │   (Container)        │ │
│                                    │   port: 5432         │ │
│                                    │                      │ │
│                                    │ Volumes:             │ │
│                                    │ - postgres_data      │ │
│                                    └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

Commands:
  docker compose up -d      # Start all services
  docker compose logs -f    # View logs
```

### Production Deployment (Kubernetes - Future)

```
┌─────────────────────────────────────────────────────────────┐
│                  Kubernetes Cluster                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │               LoadBalancer Service                    │  │
│  │               (External gRPC traffic)                 │  │
│  └─────────────────────┬────────────────────────────────┘  │
│                        │                                    │
│                        ▼                                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          catchup-feed-backend Deployment             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │   Pod 1     │  │   Pod 2     │  │   Pod 3     │  │  │
│  │  │   Go:50052  │  │   Go:50052  │  │   Go:50052  │  │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │  │
│  │         │                │                │          │  │
│  └─────────┼────────────────┼────────────────┼──────────┘  │
│            │                │                │              │
│            │ gRPC calls to catchup-ai Service │             │
│            │                │                │              │
│            ▼                ▼                ▼              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           catchup-ai Service (ClusterIP)             │  │
│  │               catchup-ai:50051                       │  │
│  └─────────────────────┬────────────────────────────────┘  │
│                        │                                    │
│                        ▼                                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              catchup-ai Deployment                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │   Pod 1     │  │   Pod 2     │  │   Pod 3     │  │  │
│  │  │   Py:50051  │  │   Py:50051  │  │   Py:50051  │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  │                                                       │  │
│  │  ConfigMap:                Secrets:                  │  │
│  │  - EMBEDDING_PROVIDER      - OPENAI_API_KEY          │  │
│  │  - GRPC_PORT               - VOYAGE_API_KEY          │  │
│  │  - LOG_LEVEL                                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          PostgreSQL StatefulSet + pgvector           │  │
│  │  - Persistent Volume Claims                          │  │
│  │  - Backup sidecar                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

Key Features:
- Horizontal Pod Autoscaling for catchup-ai (CPU/Memory based)
- Health checks via gRPC health probe
- Rolling updates with zero downtime
- Resource limits: 1 CPU, 2GB RAM per pod (tunable)
```

### Docker Image Layers

```
catchup-ai:latest
├── Runtime Stage (python:3.13-slim)
│   ├── Base OS (~80MB)
│   ├── Python 3.13 runtime
│   ├── Non-root user (appuser:1000)
│   ├── .venv/ (from builder) (~150MB)
│   │   ├── openai
│   │   ├── grpcio
│   │   ├── pydantic
│   │   └── structlog
│   └── src/catchup_ai/ (~100KB)
│       ├── __main__.py
│       ├── api/grpc/
│       ├── core/embedding/
│       └── infra/
└── Total: ~250MB

Builder Stage (discarded)
├── python:3.13-slim + uv
├── Dependencies installed with uv
└── Proto compilation artifacts
```

---

## Integration Points

### 1. catchup-feed-backend (Go Service)

**Protocol**: gRPC over TCP

**Backend → catchup-ai (Client → Server)**:
```protobuf
service ArticleAI {
  rpc EmbedArticle(EmbedArticleRequest) returns (EmbedArticleResponse);
  rpc SearchSimilar(SearchSimilarRequest) returns (SearchSimilarResponse);
  // Future: QueryArticles, GenerateWeeklySummary, ClassifyArticle
}
```

**catchup-ai → Backend (Client → Server)**:
```protobuf
service EmbeddingService {
  rpc StoreEmbedding(StoreEmbeddingRequest) returns (StoreEmbeddingResponse);
  rpc SearchSimilar(SearchSimilarRequest) returns (SearchSimilarResponse);
  rpc GetEmbeddings(GetEmbeddingsRequest) returns (GetEmbeddingsResponse);
  rpc DeleteEmbedding(DeleteEmbeddingRequest) returns (DeleteEmbeddingResponse);
}
```

**Connection Configuration**:
```bash
# .env
BACKEND_GRPC_HOST=localhost       # or "host.docker.internal" in Docker
BACKEND_GRPC_PORT=50052
BACKEND_GRPC_TIMEOUT=30.0         # seconds
```

**Error Handling**:
- Connection errors: Retry with exponential backoff
- Timeout errors: Return gRPC DEADLINE_EXCEEDED
- Backend unavailable: Return gRPC UNAVAILABLE

### 2. OpenAI API

**Protocol**: HTTPS (REST)

**Endpoint**: `https://api.openai.com/v1/embeddings`

**Authentication**: Bearer token (API key in header)

**Request**:
```json
{
  "input": ["Title: ...\n\nContent: ..."],
  "model": "text-embedding-3-small"
}
```

**Response**:
```json
{
  "data": [
    {
      "embedding": [0.123, 0.456, ...],
      "index": 0
    }
  ],
  "model": "text-embedding-3-small",
  "usage": {
    "prompt_tokens": 150,
    "total_tokens": 150
  }
}
```

**Rate Limits**:
- Tier 1: 3,500 RPM, 1M TPM
- Tier 2: 5,000 RPM, 5M TPM
- Handled via exponential backoff + jitter

### 3. Voyage AI API

**Protocol**: HTTPS (REST)

**Endpoint**: `https://api.voyageai.com/v1/embeddings`

**Authentication**: Bearer token (API key in header)

**Request**:
```json
{
  "input": ["Title: ...\n\nContent: ..."],
  "model": "voyage-3"
}
```

**Response**:
```json
{
  "data": [
    {
      "embedding": [0.123, 0.456, ...],
      "index": 0
    }
  ],
  "model": "voyage-3",
  "usage": {
    "total_tokens": 150
  }
}
```

**Rate Limits**:
- Free tier: 300 RPM
- Paid tier: Custom limits
- Handled via exponential backoff + jitter

### 4. PostgreSQL + pgvector (via Backend)

catchup-ai does NOT connect directly to PostgreSQL. All database operations are proxied through catchup-feed-backend.

**Indirect Access Pattern**:
```
catchup-ai → Backend gRPC → Backend Service Layer → PostgreSQL
```

**Why Indirect?**:
- Centralized data access control
- Single connection pool
- Consistent transaction handling
- Simplified security (fewer credentials)

---

## Security Considerations

### 1. API Key Management

**Current Implementation** (Development):
- API keys stored in `.env` file
- Loaded via pydantic-settings
- Not committed to version control (`.gitignore`)

**Production Recommendations**:
- Use Kubernetes Secrets or AWS Secrets Manager
- Rotate keys regularly (90 days)
- Use separate keys per environment (dev/staging/prod)
- Monitor API usage for anomalies

**Example Kubernetes Secret**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: catchup-ai-secrets
type: Opaque
data:
  OPENAI_API_KEY: <base64-encoded>
  VOYAGE_API_KEY: <base64-encoded>
```

### 2. gRPC Security

**Current**: Insecure (plaintext) gRPC connections

**Production Recommendations**:
- Enable TLS for gRPC (mutual TLS recommended)
- Use service mesh (Istio, Linkerd) for automatic mTLS
- Implement authentication tokens in gRPC metadata
- Rate limiting per client

**mTLS Example**:
```python
# Server-side TLS
with open('server.key', 'rb') as f:
    private_key = f.read()
with open('server.crt', 'rb') as f:
    certificate_chain = f.read()

credentials = grpc.ssl_server_credentials([(private_key, certificate_chain)])
server.add_secure_port('0.0.0.0:50051', credentials)
```

### 3. Container Security

**Current Implementation**:
- Non-root user (UID 1000)
- Minimal base image (python:3.13-slim)
- No shell in container (CMD uses Python directly)

**Additional Recommendations**:
- Scan images with Trivy or Clair
- Use distroless images for even smaller attack surface
- Read-only root filesystem
- Drop all capabilities except NET_BIND_SERVICE

**Example Security Context**:
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

### 4. Input Validation

**Current Implementation**:
- gRPC proto definitions enforce types
- Pydantic validates configuration

**Additional Validation**:
- Max text length enforcement (8000 chars)
- Sanitize article content (remove malicious scripts)
- Rate limiting per client IP

### 5. Logging & Monitoring

**Current**: Structured logging with structlog

**Production Recommendations**:
- Redact sensitive data (API keys, embeddings)
- Centralized logging (ELK, Loki)
- Audit logs for security events
- Alert on anomalous API usage

**Example Log Sanitization**:
```python
def sanitize_logs(event_dict):
    # Redact API keys
    if 'api_key' in event_dict:
        event_dict['api_key'] = '***REDACTED***'
    # Truncate embeddings
    if 'embedding' in event_dict:
        event_dict['embedding'] = '<vector[1536]>'
    return event_dict
```

---

## Future Architecture Enhancements

### 1. RAG Pipeline (Week 5-6)

**Components to Add**:
- VectorStore abstraction (currently delegated to backend)
- ContextRetriever (fetch relevant articles)
- PromptTemplate engine
- LLM client (OpenAI GPT-4o-mini)
- Response streaming

**Architecture Changes**:
```
┌─────────────────────────────────────┐
│         RAG Service                 │
│  ┌──────────────────────────────┐  │
│  │ 1. Embed query               │  │
│  │ 2. Search similar (top-5)    │  │
│  │ 3. Fetch article content     │  │
│  │ 4. Build context prompt      │  │
│  │ 5. Call LLM (GPT-4o-mini)    │  │
│  │ 6. Stream response           │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 2. Classification Service (Week 7-8)

**Components to Add**:
- Fine-tuned model adapter
- Category taxonomy
- Confidence scoring
- Batch classification

### 3. Caching Layer

**Problem**: Redundant embedding calls for same text

**Solution**: Redis cache for embeddings
```
Cache Key: sha256(provider + model + text)
Cache Value: EmbeddingResult (serialized)
TTL: 7 days
```

**Benefits**:
- Reduce API costs (OpenAI charges per token)
- Faster response times
- Rate limit protection

### 4. Observability

**Metrics to Add**:
- Embedding generation latency (p50, p95, p99)
- API error rates per provider
- gRPC request duration
- Token usage per day
- Cache hit rate

**Tools**:
- Prometheus + Grafana
- OpenTelemetry for distributed tracing
- Sentry for error tracking

---

## Appendix: Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Runtime environment |
| `DEBUG` | `false` | Enable debug logging |
| `LOG_LEVEL` | `INFO` | Logging level |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider (openai/voyage) |
| `OPENAI_API_KEY` | - | OpenAI API key (required if provider=openai) |
| `VOYAGE_API_KEY` | - | Voyage AI API key (required if provider=voyage) |
| `GRPC_HOST` | `0.0.0.0` | gRPC server bind address |
| `GRPC_PORT` | `50051` | gRPC server port |
| `GRPC_MAX_WORKERS` | `10` | Thread pool size |
| `BACKEND_GRPC_HOST` | `localhost` | Backend gRPC address |
| `BACKEND_GRPC_PORT` | `50052` | Backend gRPC port |
| `BACKEND_GRPC_TIMEOUT` | `30.0` | Backend call timeout (seconds) |

### gRPC Health Check

```bash
# Install grpcurl
brew install grpcurl

# Check server health
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Response:
{
  "status": "SERVING"
}
```

### Testing gRPC Endpoints

```bash
# Embed article
grpcurl -plaintext -d '{
  "article_id": 1,
  "title": "Introduction to Rust",
  "content": "Rust is a systems programming language...",
  "embedding_type": "content"
}' localhost:50051 catchup.ai.v1.ArticleAI/EmbedArticle

# Search similar
grpcurl -plaintext -d '{
  "query": "Rust programming",
  "limit": 5
}' localhost:50051 catchup.ai.v1.ArticleAI/SearchSimilar
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-01-23 | Initial architecture (embedding + search) |

---

**Document Status**: Active
**Last Updated**: 2026-01-23
**Maintained By**: catchup-ai team
