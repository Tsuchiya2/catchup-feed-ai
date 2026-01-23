# Product Requirements Document

## 1. Product Vision

### 1.1 Product Overview

**catchup-ai** is a Python-based AI microservice that provides intelligent features for the catchup-feed ecosystem, a personal tech article aggregation and curation platform. The service specializes in embedding generation, semantic search, RAG (Retrieval-Augmented Generation), and article classification.

### 1.2 Product Goals

1. **Enable Semantic Search**: Generate high-quality embeddings to power semantic similarity search across collected articles
2. **RAG-based Q&A**: Allow users to ask questions about their article collection and receive context-aware answers
3. **Intelligent Summarization**: Generate weekly/monthly summaries of collected articles
4. **Article Classification**: Automatically categorize articles into topics (AI, Web, Infrastructure, Security, etc.)
5. **Provider Flexibility**: Support multiple embedding providers (OpenAI, Voyage AI) for cost optimization and quality comparison

### 1.3 Strategic Position

catchup-ai is a **pure AI service** with no database dependency. It operates as a microservice in the catchup-feed ecosystem:

- **Architecture Pattern**: Microservices with clear separation of concerns
- **Communication**: gRPC for high-performance inter-service communication
- **Deployment**: Google Cloud Run (serverless) for production, local Docker for development
- **Data Ownership**: catchup-feed-backend owns all persistent data; catchup-ai is stateless

```
┌─────────────────────────────────────────────────────────────────────┐
│                      catchup-feed ecosystem                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  catchup-ai (Python)                 catchup-feed-backend (Go)      │
│  ┌──────────────────────┐            ┌────────────────────────┐    │
│  │ Responsibilities:     │   gRPC     │ Responsibilities:       │    │
│  │ ✓ Embedding generation│──────────►│ ✓ Embedding storage    │    │
│  │ ✓ Return vectors      │            │ ✓ Similarity search    │    │
│  │ ✓ RAG/LLM responses   │◄──────────│ ✓ Data management      │    │
│  │ ✓ Article classification│ gRPC    │ ✓ FK constraints       │    │
│  └──────────────────────┘            └───────────┬────────────┘    │
│                                                   │                 │
│                                                   ▼                 │
│                                      ┌────────────────────────┐    │
│                                      │ PostgreSQL 18          │    │
│                                      │ + pgvector             │    │
│                                      │                        │    │
│                                      │ • articles             │    │
│                                      │ • article_embeddings   │    │
│                                      └────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.4 Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Semantic Search Accuracy | Top-5 contains relevant articles in 90% of queries | User feedback + manual evaluation |
| RAG Answer Quality | Answers correctly cite source articles in 85% of cases | Manual evaluation |
| Classification F1 Score | > 0.8 | Automated evaluation on test set |
| Embedding Generation Latency | < 2s for single article | Server-side metrics |
| Search Latency | < 3s end-to-end | Client-side measurement |
| RAG Response Latency | < 10s | Client-side measurement |
| Service Availability | 99.5% uptime | Cloud Run monitoring |

---

## 2. Target Users and Use Cases

### 2.1 Primary User Persona

**Name**: Tech-savvy Software Engineer
**Background**: Mid to senior-level engineer who follows tech blogs and wants to stay updated
**Pain Points**:
- Overwhelmed by the volume of tech articles from multiple sources
- Difficulty finding previously read articles on specific topics
- Time-consuming to synthesize information across multiple articles
- Manual categorization is tedious and error-prone

**Needs**:
- Fast semantic search to find relevant articles by meaning, not just keywords
- Natural language Q&A over article collection
- Automated weekly/monthly summaries
- Automatic article categorization

### 2.2 Core Use Cases

#### UC-1: Semantic Article Search
**Actor**: Software Engineer
**Precondition**: Articles have been fetched and embedded
**Flow**:
1. User issues CLI command: `catchup search "Rust concurrency patterns"`
2. System generates embedding for the query
3. System searches for similar articles using cosine similarity
4. System returns top 10 most relevant articles with similarity scores
5. User views results with article titles, URLs, and relevance scores

**Acceptance Criteria**:
- Search completes in < 3 seconds
- Results are ranked by semantic similarity (0.0-1.0)
- Minimum similarity threshold is configurable
- Results include article title, URL, and similarity score

#### UC-2: RAG-based Question Answering
**Actor**: Software Engineer
**Precondition**: Article collection contains relevant content
**Flow**:
1. User asks question: `catchup ask "What are the latest developments in Rust async runtime?"`
2. System embeds the question
3. System retrieves top 5 most relevant articles as context
4. System constructs prompt with context and question
5. System generates answer using LLM (Claude/GPT)
6. System returns answer with source citations

**Acceptance Criteria**:
- Response includes specific article citations
- Answer is coherent and addresses the question
- Context articles are relevant (cosine similarity > 0.5)
- Response completes in < 10 seconds
- Confidence score is provided (0.0-1.0)

#### UC-3: Automatic Embedding Generation
**Actor**: System (Background Process)
**Precondition**: New article fetched by backend
**Flow**:
1. Backend fetches new article from RSS feed
2. Backend saves article to database
3. Backend calls catchup-ai `EmbedArticle` gRPC endpoint
4. catchup-ai generates embedding (title + content)
5. catchup-ai returns embedding vector with metadata
6. Backend stores embedding in `article_embeddings` table

**Acceptance Criteria**:
- Embedding generation completes in < 2 seconds
- Vector dimension matches configured model (1536 for OpenAI, 1024 for Voyage)
- Metadata includes provider, model, embedding_type
- Failed embeddings are retried with exponential backoff
- Text truncated to max 8000 characters if necessary

#### UC-4: Weekly Summary Generation
**Actor**: Software Engineer
**Precondition**: Articles from past week exist
**Flow**:
1. User requests summary: `catchup summarize --period=week`
2. System retrieves articles from past 7 days
3. System generates embeddings for all articles
4. System clusters similar articles
5. System generates summary using LLM
6. System returns summary with key highlights and article links

**Acceptance Criteria**:
- Summary is 200-500 words
- Highlights are bullet points (3-7 items)
- Each highlight links to relevant articles
- Summary completes in < 15 seconds
- Summary covers all major topics from the period

#### UC-5: Article Classification
**Actor**: System (Background Process)
**Precondition**: New article fetched
**Flow**:
1. Backend calls `ClassifyArticle` gRPC endpoint
2. catchup-ai analyzes article title and content
3. System predicts category using fine-tuned model
4. System returns primary category with confidence scores
5. Backend stores category metadata

**Acceptance Criteria**:
- Classification completes in < 1 second
- Categories: AI, Web, Infrastructure, Security, DevOps, Language, Database, Other
- Primary category confidence > 0.6 for acceptance
- All category scores returned for analysis
- F1 score > 0.8 on test set

---

## 3. Functional Requirements

### 3.1 Embedding Generation

#### FR-1.1: Provider-Agnostic Embedding Service
**Description**: Support multiple embedding providers with runtime configuration
**Implementation**: Factory pattern in `src/catchup_ai/core/embedding/factory.py`

```python
# Factory creates appropriate adapter based on EMBEDDING_PROVIDER env var
service = create_embedding_service()  # Uses configured provider
service = create_embedding_service("openai")  # Explicit OpenAI
service = create_embedding_service("voyage")  # Explicit Voyage AI
```

**Supported Providers**:
- **OpenAI**: `text-embedding-3-small` (1536 dimensions, default)
- **Voyage AI**: `voyage-3` (1024 dimensions, Anthropic recommended)

**Configuration**: Environment variables in `.env`
```bash
EMBEDDING_PROVIDER=openai  # or "voyage"
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSION=1536
```

#### FR-1.2: Article Embedding with Title Prioritization
**Description**: Generate embeddings that prioritize article titles for semantic quality

```python
class ArticleEmbeddingInput:
    def to_text(self, max_length: int = 8000) -> str:
        """Combine title and content, prioritizing title."""
        combined = f"Title: {self.title}\n\nContent: {self.content}"

        if len(combined) > max_length:
            # Keep full title, truncate content
            title_part = f"Title: {self.title}\n\nContent: "
            remaining = max_length - len(title_part)
            combined = title_part + self.content[:remaining] + "..."

        return combined
```

**Rationale**: Article titles are semantically richer than content fragments, improving search relevance.

#### FR-1.3: Batch Embedding Support
**Description**: Generate embeddings for multiple articles in a single API call

```python
# Single article
result = service.embed_article(article)

# Batch processing (more efficient)
results = service.embed_articles([article1, article2, ...])
```

**Batch Limits**:
- OpenAI: 2048 texts per request
- Voyage AI: 128 texts per request

#### FR-1.4: Retry Logic with Exponential Backoff
**Description**: Handle transient API failures gracefully

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
            time.sleep(delay)
```

**Backoff Strategy**: Exponential with jitter (2^attempt × random(0.5-1.5), max 30s)

### 3.2 gRPC Service API

#### FR-2.1: ArticleAI Service Definition
**Proto File**: `proto/article.proto`

```protobuf
service ArticleAI {
  // Generate embedding for an article
  rpc EmbedArticle(EmbedArticleRequest) returns (EmbedArticleResponse);

  // Search for similar articles
  rpc SearchSimilar(SearchSimilarRequest) returns (SearchSimilarResponse);

  // RAG-based question answering
  rpc QueryArticles(QueryArticlesRequest) returns (QueryArticlesResponse);

  // Generate weekly/monthly summary
  rpc GenerateWeeklySummary(GenerateWeeklySummaryRequest)
      returns (GenerateWeeklySummaryResponse);

  // Classify article into categories
  rpc ClassifyArticle(ClassifyArticleRequest) returns (ClassifyArticleResponse);
}
```

#### FR-2.2: EmbedArticle RPC
**Status**: ✅ Implemented
**Implementation**: `src/catchup_ai/api/grpc/article_servicer.py:61-127`

**Request**:
```protobuf
message EmbedArticleRequest {
  int64 article_id = 1;
  string title = 2;
  string content = 3;
  string url = 4;
  string embedding_type = 5;  // "title", "content", "summary"
}
```

**Response**:
```protobuf
message EmbedArticleResponse {
  int64 article_id = 1;
  bool success = 2;
  string error_message = 3;
  int32 embedding_dimension = 4;
  repeated float embedding = 5;  // The actual vector
  string provider = 6;  // "openai", "voyage"
  string model = 7;     // "text-embedding-3-small", "voyage-3"
  string embedding_type = 8;
}
```

**Behavior**:
- Generates embedding but does NOT store it (storage delegated to backend)
- Returns full vector to caller for storage
- Defaults to "content" embedding type if not specified
- Logs structured output with article_id, dimension, provider, model

**Error Handling**:
- Returns `success=false` with `error_message` on failure
- Does not throw gRPC exceptions for embedding errors
- Structured logging for debugging

#### FR-2.3: SearchSimilar RPC
**Status**: ✅ Implemented
**Implementation**: `src/catchup_ai/api/grpc/article_servicer.py:129-217`

**Request**:
```protobuf
message SearchSimilarRequest {
  oneof search_by {
    string query = 1;      // Text query
    int64 article_id = 2;  // Find similar to this article
  }
  int32 limit = 3;
  float min_similarity = 4;
}
```

**Response**:
```protobuf
message SearchSimilarResponse {
  repeated SimilarArticle articles = 1;
}

message SimilarArticle {
  int64 article_id = 1;
  string title = 2;           // Not populated (backend limitation)
  string url = 3;             // Not populated (backend limitation)
  float similarity_score = 4;  // Cosine similarity (0.0-1.0)
  string snippet = 5;         // Not populated (backend limitation)
}
```

**Flow**:
1. If `query` provided: Embed query text using configured provider
2. Call backend's `EmbeddingService.SearchSimilar` via gRPC client
3. Backend performs pgvector cosine similarity search
4. Return article IDs with similarity scores

**Known Limitations**:
- Search by `article_id` not yet implemented (requires backend's `GetEmbeddings`)
- Article metadata (title, url, snippet) not available in response (backend limitation)
- Caller must fetch article details separately using article IDs

#### FR-2.4: QueryArticles RPC (RAG)
**Status**: ⏳ Planned for Week 5-6
**Implementation**: Placeholder in `src/catchup_ai/api/grpc/article_servicer.py:219-237`

**Planned Flow**:
1. Embed user question
2. Retrieve top K similar articles as context (default K=5)
3. Construct prompt with context articles
4. Generate answer using Claude/GPT
5. Return answer with source citations and confidence

#### FR-2.5: GenerateWeeklySummary RPC
**Status**: ⏳ Planned for Week 5-6
**Implementation**: Placeholder in `src/catchup_ai/api/grpc/article_servicer.py:239-257`

**Planned Features**:
- Time-based filtering (week, month, custom date range)
- Topic clustering using embeddings
- LLM-based summary generation
- Key highlights extraction

#### FR-2.6: ClassifyArticle RPC
**Status**: ⏳ Planned for Week 7-8
**Implementation**: Placeholder in `src/catchup_ai/api/grpc/article_servicer.py:259-277`

**Planned Approach**:
- Fine-tune BERT model (cl-tohoku/bert-base-japanese-v3) with LoRA
- Categories: AI, Web, Infrastructure, Security, DevOps, Language, Database, Other
- Return primary category + all category scores
- Target F1 > 0.8

### 3.3 Backend Integration

#### FR-3.1: Embedding Storage Client
**Status**: ✅ Implemented
**Implementation**: `src/catchup_ai/infra/grpc/embedding_client.py`

**Purpose**: Call backend's `EmbeddingService` to store embeddings and perform similarity search

**Key Methods**:
```python
class EmbeddingClient:
    def store_embedding(
        self,
        article_id: int,
        embedding: list[float],
        embedding_type: str,
        provider: str,
        model: str,
        dimension: int,
    ) -> tuple[bool, int | None, str | None]:
        """Store embedding via backend gRPC."""

    def search_similar(
        self,
        embedding: list[float],
        embedding_type: str,
        limit: int = 10,
    ) -> list[SimilarArticleResult]:
        """Search for similar articles via backend gRPC."""
```

**Backend Endpoint**: `localhost:50052` (configurable via `BACKEND_GRPC_HOST`, `BACKEND_GRPC_PORT`)

**Backend Proto**: `proto/embedding/embedding.proto`
```protobuf
service EmbeddingService {
  rpc StoreEmbedding(StoreEmbeddingRequest) returns (StoreEmbeddingResponse);
  rpc GetEmbeddings(GetEmbeddingsRequest) returns (GetEmbeddingsResponse);
  rpc SearchSimilar(SearchSimilarRequest) returns (SearchSimilarResponse);
  rpc DeleteEmbedding(DeleteEmbeddingRequest) returns (DeleteEmbeddingResponse);
}
```

**Connection Management**:
- Lazy connection establishment on first use
- Context manager support (`with EmbeddingClient() as client:`)
- Graceful error handling for gRPC failures
- Timeout configuration (default 30s, via `BACKEND_GRPC_TIMEOUT`)

#### FR-3.2: Data Flow Architecture

**Embedding Generation Flow**:
```
1. Backend: Save new article to database
2. Backend → catchup-ai (port 50051): EmbedArticle gRPC call
3. catchup-ai: Generate embedding vector using OpenAI/Voyage
4. catchup-ai → Backend: Return embedding vector with metadata
5. Backend: Store in article_embeddings table
```

**Similarity Search Flow**:
```
1. CLI → Backend: Search query
2. Backend → catchup-ai (port 50051): SearchSimilar gRPC call
3. catchup-ai: Embed query text
4. catchup-ai → Backend (port 50052): SearchSimilar gRPC call
5. Backend: pgvector cosine similarity search
6. Backend → catchup-ai: Article IDs + similarity scores
7. catchup-ai → Backend: Article IDs + similarity scores
8. Backend: Fetch article details and return to CLI
```

### 3.4 Health Checks and Observability

#### FR-4.1: gRPC Health Check
**Status**: ✅ Implemented
**Implementation**: `src/catchup_ai/api/grpc/server.py:43-55`

```python
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
```

**Testing**:
```bash
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

#### FR-4.2: Structured Logging
**Status**: ✅ Implemented
**Implementation**: `src/catchup_ai/__main__.py:12-35`

**Features**:
- JSON logging in production (for Cloud Run)
- Console logging in development (human-readable)
- Automatic timestamp, log level, logger name
- Context binding for request tracing

```python
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        # JSON in production, console in development
        structlog.processors.JSONRenderer()
        if settings.environment == "production"
        else structlog.dev.ConsoleRenderer(),
    ],
)
```

**Log Samples**:
```json
{
  "event": "EmbedArticle request",
  "article_id": 123,
  "title": "Understanding Rust ownership",
  "embedding_type": "content",
  "timestamp": "2026-01-23T23:13:45.123Z",
  "level": "info"
}

{
  "event": "Embedding generated successfully",
  "article_id": 123,
  "dimension": 1536,
  "provider": "openai",
  "model": "text-embedding-3-small",
  "timestamp": "2026-01-23T23:13:47.456Z",
  "level": "info"
}
```

---

## 4. Non-Functional Requirements

### 4.1 Performance

| Metric | Target | Rationale |
|--------|--------|-----------|
| Single Embedding Generation | < 2s | OpenAI API latency + processing |
| Batch Embedding (10 articles) | < 5s | Efficient batching |
| Search Query Latency | < 3s | Embedding + pgvector lookup |
| RAG Response Latency | < 10s | Retrieval + LLM generation |
| gRPC Message Size | Max 100MB | Large article content + vectors |
| Concurrent Requests | 10 workers | Thread pool configuration |

### 4.2 Scalability

**Development**:
- Single Docker container
- Local PostgreSQL with pgvector

**Production (Cloud Run)**:
- Serverless, auto-scaling 0 → N instances
- Min instances: 0 (cost optimization)
- Max instances: 10 (limit concurrent API usage)
- Cold start: 30-60s (acceptable for CLI usage)
- CPU: 1 vCPU per instance
- Memory: 512 MB per instance

### 4.3 Reliability

**Availability Target**: 99.5% uptime

**Resilience Mechanisms**:
- Exponential backoff retry for API failures (max 3 attempts)
- Graceful degradation (return partial results if some embeddings fail)
- gRPC timeout configuration (30s default)
- Circuit breaker pattern for external APIs (future enhancement)

**Error Handling**:
- All gRPC errors are caught and logged
- Structured error messages returned to caller
- No silent failures

**Graceful Shutdown**:
```python
def shutdown_handler(signum, frame):
    logger.info("Shutdown signal received", signal=signum)
    event = server.stop(grace=30)  # 30s grace period
    event.wait()
    logger.info("Server stopped gracefully")
    sys.exit(0)
```

### 4.4 Security

**Authentication**:
- Development: No authentication (localhost only)
- Production: Cloud Run authentication tokens (future)

**API Keys**:
- Stored in environment variables (`.env` file, not committed)
- Validated at startup (format checks)
- OpenAI keys must start with `sk-`
- Voyage keys must start with `pa-`

**Network**:
- Development: Insecure gRPC (localhost)
- Production: TLS-encrypted gRPC (Cloud Run)
- No public endpoints exposed

**Docker Security**:
```dockerfile
# Non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

USER appuser
```

### 4.5 Maintainability

**Code Quality**:
- Type hints throughout (Python 3.13+)
- Strict mypy checking enabled
- Ruff linting and formatting
- Test coverage target: > 70% (current: 28%)

**Development Tools**:
```bash
make dev      # Install dependencies
make test     # Run tests with coverage
make lint     # Run linter and type checker
make format   # Auto-format code
make run      # Start server locally
```

**Documentation**:
- Docstrings for all public functions
- Architecture notes in code comments
- Proto file documentation
- README with setup instructions

### 4.6 Deployment

**Docker Image**:
- Multi-stage build for small image size
- Python 3.13-slim base (security updates)
- uv for fast dependency installation
- Health check endpoint

**Environment Variables**:
```bash
# Required
OPENAI_API_KEY=sk-...
EMBEDDING_PROVIDER=openai

# Optional (with defaults)
GRPC_HOST=0.0.0.0
GRPC_PORT=50051
BACKEND_GRPC_HOST=localhost
BACKEND_GRPC_PORT=50052
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO
```

**Cloud Run Deployment** (Planned Week 7-8):
```bash
gcloud run deploy catchup-ai \
  --source . \
  --region asia-northeast1 \
  --platform managed \
  --allow-unauthenticated \
  --port 50051 \
  --use-http2 \
  --set-env-vars "OPENAI_API_KEY=xxx,EMBEDDING_PROVIDER=openai"
```

---

## 5. Technical Constraints

### 5.1 Programming Language and Framework

- **Language**: Python 3.13+ (type hints, performance improvements)
- **Package Manager**: uv (fast, modern, lockfile support)
- **RPC Framework**: gRPC with Protocol Buffers
- **Async**: Not used (gRPC uses thread pool, no async/await)

### 5.2 External Dependencies

**Core Dependencies** (from `pyproject.toml`):
```toml
[project.dependencies]
openai = ">=1.0.0"                     # Embedding API
grpcio = ">=1.60.0"                    # gRPC server
grpcio-tools = ">=1.60.0"              # Proto compilation
grpcio-health-checking = ">=1.60.0"    # Health checks
pydantic = ">=2.0.0"                   # Data validation
pydantic-settings = ">=2.0.0"          # Config management
python-dotenv = ">=1.0.0"              # .env loading
structlog = ">=24.0.0"                 # Structured logging
```

**Optional Dependencies**:
```toml
[project.optional-dependencies]
voyage = ["httpx>=0.27.0"]  # Voyage AI support
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "jupyter>=1.0.0",
]
```

### 5.3 Infrastructure Dependencies

**Development**:
- Docker Compose for local orchestration
- PostgreSQL 18 with pgvector extension (managed by backend)

**Production**:
- Google Cloud Run (serverless container platform)
- Backend service on RPi5 with Cloudflare Tunnel
- Cloud Storage for fine-tuned model storage (future)

### 5.4 API Rate Limits

**OpenAI**:
- Free tier: 3 requests/min, 200 requests/day
- Paid tier: 3,500 requests/min (tier 1)
- Retry with exponential backoff on 429 errors

**Voyage AI**:
- Batch limit: 128 texts per request
- Rate limits vary by plan
- Exponential backoff on rate limit errors

### 5.5 Database Schema (Managed by Backend)

**article_embeddings table**:
```sql
CREATE TABLE article_embeddings (
    id              SERIAL PRIMARY KEY,
    article_id      BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    embedding_type  VARCHAR(50) NOT NULL,   -- 'title', 'content', 'summary'
    provider        VARCHAR(50) NOT NULL,   -- 'openai', 'voyage'
    model           VARCHAR(100) NOT NULL,  -- 'text-embedding-3-small'
    dimension       INT NOT NULL,           -- 1536, 1024, etc.
    embedding       vector(1536) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(article_id, embedding_type, provider, model)
);

CREATE INDEX idx_article_embeddings_vector
ON article_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

---

## 6. Out of Scope

The following features are explicitly **not included** in this phase:

1. **Real-time Streaming**: No streaming RPCs (all unary)
2. **User Authentication**: No user accounts or API key management
3. **Web UI**: CLI-only interface
4. **Multi-tenancy**: Single-user system
5. **Custom Embedding Models**: No locally hosted models (API-only)
6. **Batch Job Management**: No background job queue (all synchronous)
7. **Advanced Analytics**: No metrics dashboards or reporting
8. **Multi-language Support**: English/Japanese only
9. **Vector Database Migration**: No support for switching between pgvector and alternatives

---

## 7. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| OpenAI API rate limits | High | Medium | Implement exponential backoff, use batching, consider Voyage AI alternative |
| Cloud Run cold start latency | Medium | High | Acceptable for CLI (30-60s), consider min-instances=1 if needed |
| Backend-AI communication failure | High | Low | Implement retry logic, graceful degradation, circuit breaker |
| Embedding quality issues | Medium | Medium | A/B test providers (OpenAI vs Voyage), evaluate on test set |
| Database migration complexity | Low | Low | Backend owns schema, catchup-ai is stateless |
| Cost overruns (API usage) | Medium | Low | Monitor usage, set budget alerts, optimize batch sizes |
| Fine-tuning data insufficiency | Medium | Medium | Manual labeling of 200+ articles, data augmentation |

---

## 8. Implementation Roadmap

### Phase 1: Core Embedding Service (Weeks 1-2) ✅ COMPLETE

- [x] Project setup with uv
- [x] Proto definitions for ArticleAI and EmbeddingService
- [x] OpenAI embedding adapter
- [x] Voyage AI embedding adapter
- [x] Factory pattern for provider switching
- [x] gRPC server with health checks
- [x] Backend gRPC client (EmbeddingClient)
- [x] Configuration management with pydantic-settings
- [x] Docker containerization
- [x] Structured logging

### Phase 2: Embedding Integration (Weeks 3-4) 🔄 IN PROGRESS

- [x] EmbedArticle RPC implementation
- [x] SearchSimilar RPC implementation (via backend)
- [ ] Unit tests for embedding service
- [ ] Integration tests for gRPC endpoints
- [ ] Backend integration (AI client in Go)
- [ ] Automatic embedding on article creation

### Phase 3: RAG Implementation (Weeks 5-6) ⏳ PLANNED

- [ ] RAG pipeline (retriever + generator)
- [ ] QueryArticles RPC implementation
- [ ] GenerateWeeklySummary RPC implementation
- [ ] Prompt engineering and optimization
- [ ] Context window management
- [ ] CLI commands (search, ask, summarize)

### Phase 4: Classification & Deployment (Weeks 7-8) ⏳ PLANNED

- [ ] Fine-tune BERT model with LoRA
- [ ] ClassifyArticle RPC implementation
- [ ] Model storage in Cloud Storage
- [ ] Cloud Run deployment
- [ ] E2E testing
- [ ] Performance optimization
- [ ] Documentation and technical blog post

---

## 9. Acceptance Criteria Summary

The product is considered complete and ready for production when:

1. **Embedding Generation**:
   - [x] Single article embedding completes in < 2s
   - [x] Batch embedding supported (up to batch limits)
   - [x] Both OpenAI and Voyage providers work
   - [x] Provider switching via environment variable
   - [x] Retry logic handles API failures
   - [ ] Test coverage > 70%

2. **gRPC Service**:
   - [x] EmbedArticle RPC returns embedding vectors
   - [x] SearchSimilar RPC works via backend
   - [ ] QueryArticles RPC generates RAG answers
   - [ ] GenerateWeeklySummary RPC creates summaries
   - [ ] ClassifyArticle RPC predicts categories
   - [x] Health check endpoint responds correctly
   - [ ] All RPCs have integration tests

3. **Backend Integration**:
   - [x] EmbeddingClient stores embeddings via gRPC
   - [x] EmbeddingClient performs similarity search
   - [ ] Backend automatically embeds new articles
   - [ ] CLI commands work end-to-end

4. **Quality Metrics**:
   - [ ] Semantic search: Top-5 accuracy > 90%
   - [ ] RAG: Source citation accuracy > 85%
   - [ ] Classification: F1 score > 0.8
   - [ ] Search latency < 3s
   - [ ] RAG latency < 10s

5. **Deployment**:
   - [x] Docker image builds successfully
   - [x] Docker Compose works locally
   - [ ] Cloud Run deployment successful
   - [ ] E2E tests pass in production environment
   - [ ] Monitoring and logging configured

---

## 10. Appendix

### 10.1 Key Files and Locations

**Proto Definitions**:
- `/Users/yujitsuchiya/catchup-feed-ai/proto/article.proto` (ArticleAI service)
- `/Users/yujitsuchiya/catchup-feed-ai/proto/embedding/embedding.proto` (Backend EmbeddingService)

**Core Services**:
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/core/embedding/service.py` (EmbeddingService interface)
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/core/embedding/openai_adapter.py` (OpenAI implementation)
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/core/embedding/voyage_adapter.py` (Voyage implementation)
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/core/embedding/factory.py` (Provider factory)

**gRPC Server**:
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/api/grpc/server.py` (Server setup)
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/api/grpc/article_servicer.py` (RPC handlers)

**Backend Integration**:
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/infra/grpc/embedding_client.py` (Backend gRPC client)

**Configuration**:
- `/Users/yujitsuchiya/catchup-feed-ai/src/catchup_ai/infra/config/settings.py` (Settings management)
- `/Users/yujitsuchiya/catchup-feed-ai/.env.example` (Environment variable template)

**Deployment**:
- `/Users/yujitsuchiya/catchup-feed-ai/Dockerfile` (Multi-stage Docker build)
- `/Users/yujitsuchiya/catchup-feed-ai/compose.yml` (Docker Compose configuration)
- `/Users/yujitsuchiya/catchup-feed-ai/Makefile` (Development commands)

### 10.2 References

- **Project Plan**: `/Users/yujitsuchiya/catchup-feed-ai/plan.md`
- **OpenAI Embeddings**: https://platform.openai.com/docs/guides/embeddings
- **Voyage AI**: https://www.voyageai.com/
- **pgvector**: https://github.com/pgvector/pgvector
- **gRPC Python**: https://grpc.io/docs/languages/python/
- **Protocol Buffers**: https://protobuf.dev/
- **Google Cloud Run**: https://cloud.google.com/run/docs
