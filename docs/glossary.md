# Glossary

**Project**: catchup-ai
**Purpose**: AI service for catchup-feed ecosystem - Embedding, RAG, and Article Classification
**Last Updated**: 2026-01-23

This glossary defines domain-specific terms, technical terminology, entities, and acronyms used throughout the catchup-ai project.

---

## Table of Contents
- [Domain Terms](#domain-terms)
- [Technical Terms](#technical-terms)
- [Entities & Data Structures](#entities--data-structures)
- [API & Services](#api--services)
- [Configuration & Settings](#configuration--settings)
- [Acronyms & Abbreviations](#acronyms--abbreviations)
- [AI/ML Terminology](#aiml-terminology)

---

## Domain Terms

### Article
A piece of content from the catchup-feed ecosystem that can be embedded and searched. Articles have a unique ID, title, content, and optional URL. Articles are the primary unit of content processed by catchup-ai.

**Code Reference**: `proto/article.proto`, `ArticleEmbeddingInput` in `src/catchup_ai/core/embedding/service.py`

### Embedding
A dense vector representation of text that captures semantic meaning. In catchup-ai, embeddings are generated from article titles and content to enable similarity search and RAG operations.

**Dimensions**:
- OpenAI `text-embedding-3-small`: 1536 dimensions
- Voyage `voyage-3`: 1024 dimensions
- Voyage `voyage-3-lite`: 512 dimensions

**Code Reference**: `src/catchup_ai/core/embedding/service.py`, `proto/embedding/embedding.proto`

### Embedding Type
Categorization of what part of an article was embedded. Valid values:
- `title`: Embedding generated from article title only
- `content`: Embedding generated from article content (or title + content combined)
- `summary`: Embedding generated from article summary

**Code Reference**: `proto/embedding/embedding.proto` (line 42-43), `proto/article.proto` (line 38-40)

### Similarity Search
Finding articles that are semantically similar to a query (either text or another article) by comparing embedding vectors using cosine similarity. Results are ranked by similarity score (0.0 to 1.0, where 1.0 is most similar).

**Code Reference**: `proto/embedding/embedding.proto` (SearchSimilar RPC), `src/catchup_ai/infra/grpc/embedding_client.py`

### RAG (Retrieval-Augmented Generation)
A technique that combines similarity search with language model generation. First, relevant articles are retrieved via embedding similarity, then used as context for generating answers to user questions.

**Status**: Planned for Week 5-6 (not yet implemented)

**Code Reference**: `proto/article.proto` (QueryArticles RPC), `src/catchup_ai/api/grpc/article_servicer.py` (line 219-237)

---

## Technical Terms

### gRPC (gRPC Remote Procedure Call)
High-performance, open-source RPC framework used for communication between catchup-ai (Python) and catchup-feed-backend (Go). Uses Protocol Buffers for serialization.

**Server Port**: 50051 (catchup-ai), 50052 (catchup-feed-backend)

**Code Reference**: `src/catchup_ai/api/grpc/server.py`, `compose.yml`

### Protocol Buffers (Protobuf)
Language-neutral, platform-neutral serialization format used to define gRPC service contracts. Catchup-ai uses `.proto` files to define the ArticleAI service and EmbeddingService client.

**Code Reference**: `proto/article.proto`, `proto/embedding/embedding.proto`

### pgvector
PostgreSQL extension that enables efficient storage and similarity search of vector embeddings. Used by catchup-feed-backend for storing article embeddings.

**Note**: catchup-ai generates embeddings but does NOT store them. Storage is handled by catchup-feed-backend using pgvector.

**Code Reference**: `proto/embedding/embedding.proto` (line 150 - cosine distance comment)

### Cosine Similarity
Metric used to measure similarity between two embedding vectors. Calculated as `1 - cosine_distance`. Values range from 0.0 (completely different) to 1.0 (identical).

**Implementation**: Performed by pgvector in catchup-feed-backend.

**Code Reference**: `proto/embedding/embedding.proto` (line 148-150)

### Adapter Pattern
Design pattern used to wrap external embedding providers (OpenAI, Voyage) with a common interface (`EmbeddingService`). Enables easy switching between providers without changing application code.

**Code Reference**: `src/catchup_ai/core/embedding/openai_adapter.py`, `src/catchup_ai/core/embedding/voyage_adapter.py`

### Factory Pattern
Design pattern used in `create_embedding_service()` to instantiate the appropriate embedding provider based on configuration. Implements the Strategy Pattern for runtime provider selection.

**Code Reference**: `src/catchup_ai/core/embedding/factory.py`

### Exponential Backoff
Retry strategy that exponentially increases delay between retry attempts (2^attempt seconds). Used in embedding adapters to handle transient API failures. Includes jitter to prevent thundering herd problems.

**Code Reference**: `src/catchup_ai/core/embedding/openai_adapter.py` (line 138-157), `src/catchup_ai/core/embedding/voyage_adapter.py` (line 135-140)

### Structured Logging
Logging approach that outputs logs as structured data (JSON in production, console in development). Uses `structlog` library for consistent, queryable logs.

**Code Reference**: `src/catchup_ai/__main__.py` (configure_logging function)

### Health Check
gRPC service that allows clients to verify server availability. Implements `grpc.health.v1.Health` protocol for monitoring and load balancing.

**Code Reference**: `src/catchup_ai/api/grpc/server.py` (line 43-55)

---

## Entities & Data Structures

### ArticleEmbeddingInput
Input dataclass for embedding an article. Combines title and content for richer semantic representation.

**Fields**:
- `article_id` (int): Unique identifier from catchup-feed-backend
- `title` (str): Article title
- `content` (str): Article content
- `url` (str | None): Optional article URL

**Method**: `to_text(max_length: int = 8000)` - Converts to text for embedding, prioritizing title and truncating content if needed.

**Code Reference**: `src/catchup_ai/core/embedding/service.py` (line 34-60)

### EmbeddingResult
Result dataclass returned from embedding operations.

**Fields**:
- `vector` (list[float]): The embedding vector
- `model` (str): Model used to generate the embedding (e.g., "text-embedding-3-small")
- `provider` (str): Provider that generated the embedding ("openai" or "voyage")
- `tokens_used` (int): Number of tokens processed

**Property**: `dimension` - Returns the length of the embedding vector.

**Code Reference**: `src/catchup_ai/core/embedding/service.py` (line 11-30)

### SimilarArticleResult
Result dataclass for similarity search operations.

**Fields**:
- `article_id` (int): ID of the similar article
- `similarity` (float): Cosine similarity score (0.0 to 1.0)

**Code Reference**: `src/catchup_ai/infra/grpc/embedding_client.py` (line 25-30)

### ArticleEmbedding
Protocol Buffer message representing a stored embedding with full metadata.

**Fields**: id, article_id, embedding_type, provider, model, dimension, embedding, created_at, updated_at

**Code Reference**: `proto/embedding/embedding.proto` (line 113-141)

### SimilarArticle
Protocol Buffer message representing a similar article with its similarity score.

**Fields**: article_id, similarity (for backend EmbeddingService) OR article_id, title, url, similarity_score, snippet (for ArticleAI service)

**Code Reference**: `proto/embedding/embedding.proto` (line 143-152), `proto/article.proto` (line 85-96)

---

## API & Services

### ArticleAI Service
Main gRPC service provided by catchup-ai. Handles article embedding, similarity search, RAG queries, weekly summaries, and article classification.

**RPC Methods**:
- `EmbedArticle`: Generate embedding for an article (implemented)
- `SearchSimilar`: Find similar articles (implemented)
- `QueryArticles`: RAG-based Q&A (Week 5-6)
- `GenerateWeeklySummary`: Generate periodic summaries (Week 5-6)
- `ClassifyArticle`: Categorize articles (Week 7-8)

**Code Reference**: `proto/article.proto`, `src/catchup_ai/api/grpc/article_servicer.py`

### EmbeddingService (Backend)
gRPC service provided by catchup-feed-backend for embedding storage and similarity search. Catchup-ai acts as a client to this service.

**RPC Methods**:
- `StoreEmbedding`: Store or update an embedding
- `GetEmbeddings`: Retrieve all embeddings for an article
- `SearchSimilar`: Find similar articles using cosine similarity
- `DeleteEmbedding`: Remove embeddings for an article

**Code Reference**: `proto/embedding/embedding.proto`, `src/catchup_ai/infra/grpc/embedding_client.py`

### EmbeddingService (Interface)
Abstract base class defining the contract for embedding providers. All providers (OpenAI, Voyage, future local models) implement this interface.

**Methods**:
- `embed_text(text: str) -> EmbeddingResult`: Generate single embedding
- `embed_texts(texts: list[str]) -> list[EmbeddingResult]`: Batch embedding
- `embed_article(article: ArticleEmbeddingInput) -> EmbeddingResult`: Article-specific embedding
- `embed_articles(articles: list[ArticleEmbeddingInput]) -> list[EmbeddingResult]`: Batch article embedding

**Code Reference**: `src/catchup_ai/core/embedding/service.py` (line 63-128)

### ArticleAIServicer
gRPC servicer implementation that handles incoming RPC requests for the ArticleAI service. Uses factory pattern to create embedding service based on configuration.

**Architecture**: Generates embeddings but does NOT store them. Storage is delegated to catchup-feed-backend via EmbeddingClient.

**Code Reference**: `src/catchup_ai/api/grpc/article_servicer.py`

### EmbeddingClient
gRPC client for communicating with catchup-feed-backend's EmbeddingService. Provides methods for storing embeddings and searching similar articles.

**Methods**:
- `store_embedding()`: Store embedding in backend
- `search_similar()`: Search for similar articles

**Connection**: Uses insecure gRPC channel to `BACKEND_GRPC_HOST:BACKEND_GRPC_PORT` (default: localhost:50052)

**Code Reference**: `src/catchup_ai/infra/grpc/embedding_client.py`

---

## Configuration & Settings

### Settings
Main application configuration loaded from environment variables (`.env` file). Uses Pydantic for validation.

**Sub-settings**:
- `embedding`: Embedding service configuration
- `openai`: OpenAI API configuration
- `voyage`: Voyage AI API configuration
- `grpc`: gRPC server configuration
- `backend`: Backend gRPC client configuration

**Code Reference**: `src/catchup_ai/infra/config/settings.py`

### EmbeddingProvider
Enum defining supported embedding providers.

**Values**:
- `OPENAI`: OpenAI embedding service
- `VOYAGE`: Voyage AI (Anthropic recommended provider)

**Environment Variable**: `EMBEDDING_PROVIDER` (default: "openai")

**Code Reference**: `src/catchup_ai/infra/config/settings.py` (line 14-18)

### OpenAI Settings
Configuration for OpenAI embedding provider.

**Environment Variables**:
- `OPENAI_API_KEY`: API key (must start with "sk-")
- `OPENAI_EMBEDDING_MODEL`: Model name (default: "text-embedding-3-small")
- `OPENAI_EMBEDDING_DIMENSION`: Vector dimension (default: 1536)
- `OPENAI_CHAT_MODEL`: Chat model for RAG (default: "gpt-4o-mini")

**Code Reference**: `src/catchup_ai/infra/config/settings.py` (line 36-61)

### Voyage Settings
Configuration for Voyage AI embedding provider (Anthropic recommended).

**Environment Variables**:
- `VOYAGE_API_KEY`: API key (must start with "pa-")
- `VOYAGE_EMBEDDING_MODEL`: Model name (default: "voyage-3")
- `VOYAGE_EMBEDDING_DIMENSION`: Vector dimension (default: 1024)

**Models Available**:
- `voyage-3`: General purpose, 1024 dimensions (recommended)
- `voyage-3-lite`: Faster, lower cost, 512 dimensions
- `voyage-code-3`: Optimized for code, 1024 dimensions

**Code Reference**: `src/catchup_ai/infra/config/settings.py` (line 64-89), `src/catchup_ai/core/embedding/voyage_adapter.py` (line 1-14)

### GRPC Settings
Configuration for the gRPC server.

**Environment Variables**:
- `GRPC_HOST`: Server host (default: "0.0.0.0")
- `GRPC_PORT`: Server port (default: 50051)
- `GRPC_MAX_WORKERS`: Thread pool size (default: 10)
- `GRPC_MAX_MESSAGE_SIZE`: Max message size in bytes (default: 100MB)

**Code Reference**: `src/catchup_ai/infra/config/settings.py` (line 92-108)

### Backend Settings
Configuration for connecting to catchup-feed-backend.

**Environment Variables**:
- `BACKEND_GRPC_HOST`: Backend host (default: "localhost")
- `BACKEND_GRPC_PORT`: Backend port (default: 50052)
- `BACKEND_GRPC_TIMEOUT`: RPC timeout in seconds (default: 30.0)

**Code Reference**: `src/catchup_ai/infra/config/settings.py` (line 111-123)

---

## Acronyms & Abbreviations

### AI
Artificial Intelligence. In catchup-ai, refers to embedding generation, similarity search, RAG, and classification capabilities.

### API
Application Programming Interface. Catchup-ai exposes a gRPC API for article processing.

### gRPC
gRPC Remote Procedure Call. High-performance RPC framework used for inter-service communication.

### HTTP/2
Protocol underlying gRPC, providing multiplexing, streaming, and header compression.

### LLM
Large Language Model. Used in catchup-ai for RAG operations (Week 5-6) and classification (Week 7-8).

### NLP
Natural Language Processing. The field of AI focused on text understanding, embedding, and generation.

### RAG
Retrieval-Augmented Generation. Technique combining similarity search with LLM generation for question answering.

### RPC
Remote Procedure Call. Method for invoking functions on remote servers as if they were local.

### REST
Representational State Transfer. Alternative API pattern not used in catchup-ai (uses gRPC instead).

### TLS
Transport Layer Security. Not currently used (insecure channels), but should be added for production.

### UUID
Universally Unique Identifier. Not currently used; catchup-ai uses integer IDs from backend.

---

## AI/ML Terminology

### Batch Embedding
Generating embeddings for multiple texts in a single API call. More efficient than individual calls.

**Batch Limits**:
- OpenAI: 2048 texts per request
- Voyage AI: 128 texts per request

**Code Reference**: `src/catchup_ai/core/embedding/openai_adapter.py` (line 64-90), `src/catchup_ai/core/embedding/voyage_adapter.py` (line 85-102)

### Cosine Distance
Measure of dissimilarity between two vectors. Related to cosine similarity by: `similarity = 1 - distance`.

**Code Reference**: `proto/embedding/embedding.proto` (line 150)

### Dimension
The size (length) of an embedding vector. Higher dimensions can capture more nuanced semantic information but require more storage and computation.

**Code Reference**: `EmbeddingResult.dimension` property

### Model
Specific AI model used to generate embeddings or perform other AI tasks.

**Embedding Models**:
- OpenAI: `text-embedding-3-small`, `text-embedding-3-large`
- Voyage: `voyage-3`, `voyage-3-lite`, `voyage-code-3`

**Chat Models** (for RAG):
- OpenAI: `gpt-4o-mini`, `gpt-4o`

### Provider
The AI service company providing embedding or LLM APIs.

**Supported Providers**:
- `openai`: OpenAI
- `voyage`: Voyage AI (Anthropic recommended)

### Rate Limit
API restriction on the number of requests allowed per time period. Catchup-ai handles rate limits with exponential backoff retry logic.

**Code Reference**: `RateLimitError` in `src/catchup_ai/core/embedding/service.py`, retry logic in adapters

### Semantic Search
Search technique that finds results based on meaning rather than keyword matching. Uses embedding similarity to find conceptually related content.

### Token
Unit of text processed by AI models. Roughly equivalent to a word or word fragment. Used for API billing and input limits.

**Code Reference**: `EmbeddingResult.tokens_used`

### Vector
Numerical array representing text in embedding space. Enables mathematical operations like similarity comparison.

**Code Reference**: `EmbeddingResult.vector` (list[float])

### Vector Database
Database optimized for storing and searching high-dimensional vectors. Catchup-feed-backend uses PostgreSQL with pgvector extension.

---

## Error Types

### EmbeddingError
Base exception for all embedding-related errors.

**Code Reference**: `src/catchup_ai/core/embedding/service.py` (line 131-134)

### RateLimitError
Raised when API rate limit is exceeded. Includes optional `retry_after` field indicating when to retry.

**Code Reference**: `src/catchup_ai/core/embedding/service.py` (line 137-142)

### TokenLimitError
Raised when text exceeds the model's token limit.

**Code Reference**: `src/catchup_ai/core/embedding/service.py` (line 145-151)

---

## Architecture Patterns

### Layered Architecture
Catchup-ai follows a layered architecture:
- **API Layer**: gRPC servicers and server (`src/catchup_ai/api/grpc/`)
- **Core/Domain Layer**: Embedding services and business logic (`src/catchup_ai/core/`)
- **Infrastructure Layer**: Configuration, external clients (`src/catchup_ai/infra/`)

**Code Reference**: `src/catchup_ai/` directory structure

### Service-Oriented Architecture (SOA)
Catchup-ai is a microservice in the catchup-feed ecosystem:
- **catchup-ai**: AI processing (embedding, RAG, classification)
- **catchup-feed-backend**: Data storage, API gateway
- Communication via gRPC

**Code Reference**: `compose.yml`, `proto/` directory

### Strategy Pattern
Used in embedding service factory to select provider at runtime based on configuration.

**Code Reference**: `src/catchup_ai/core/embedding/factory.py`

### Protocol-Oriented Design
Uses Python `Protocol` for structural subtyping (duck typing with type hints).

**Code Reference**: `EmbeddingClientProtocol` in `src/catchup_ai/infra/grpc/embedding_client.py`

---

## Development Tools

### uv
Fast Python package installer and resolver. Used for dependency management and running scripts.

**Commands**: `uv sync`, `uv run`, `uv add`

**Code Reference**: `pyproject.toml`, `Makefile`

### Ruff
Fast Python linter and formatter. Replaces multiple tools (flake8, black, isort).

**Configuration**: `pyproject.toml` (line 47-62)

### mypy
Static type checker for Python. Enforces strict type checking.

**Configuration**: `pyproject.toml` (line 64-68)

### pytest
Testing framework used for unit and integration tests.

**Configuration**: `pyproject.toml` (line 70-72)

### structlog
Structured logging library providing JSON output in production and console output in development.

**Code Reference**: `src/catchup_ai/__main__.py`

### grpcurl
Command-line tool for testing gRPC services (like curl for HTTP).

**Usage**: `make grpcurl` to test health check

**Code Reference**: `Makefile` (line 66-76)

### Docker Compose
Tool for defining and running multi-container Docker applications.

**Code Reference**: `compose.yml`

---

## Status Indicators

### Implemented
- Article embedding generation (OpenAI, Voyage)
- Similarity search (via backend)
- gRPC server with health checks
- Provider switching (OpenAI ↔ Voyage)

### Planned (Week 5-6)
- RAG-based question answering (`QueryArticles`)
- Weekly summary generation (`GenerateWeeklySummary`)

### Planned (Week 7-8)
- Article classification (`ClassifyArticle`)

**Code Reference**: `src/catchup_ai/api/grpc/article_servicer.py` (UNIMPLEMENTED status codes)
