# Security Standards

## Overview

This skill enforces security best practices for the catchup-ai Python service, which handles sensitive API keys (OpenAI, Voyage AI) and communicates via gRPC. Security is critical for protecting credentials, preventing data leaks, and maintaining system integrity.

## Skill Behavior

When invoked, this skill:
1. Reviews code changes for security vulnerabilities
2. Validates API key handling patterns
3. Checks for hardcoded secrets
4. Verifies input validation and sanitization
5. Ensures Docker security best practices
6. Reviews error handling for sensitive data leaks

## Security Domains

### 1. API Key Management

#### Rules

**MUST**: Store all API keys in environment variables
- Use `.env` files for local development (never commit)
- Use environment variables in Docker/production
- Load via `pydantic-settings` with validation

**MUST**: Validate API key formats before use
- OpenAI keys: Must start with `sk-`
- Voyage AI keys: Must start with `pa-`
- Return clear error messages for invalid formats

**MUST NOT**: Hardcode API keys in source code
- No API keys in Python files
- No API keys in configuration files committed to git
- No API keys in Docker images

#### Examples

**Correct**: API key validation with pydantic
```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class OpenAISettings(BaseSettings):
    """OpenAI API configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_")

    api_key: str = Field(default="", description="OpenAI API key")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        # Allow empty string when not using OpenAI provider
        if v and not v.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format (must start with sk-)")
        return v
```

**Correct**: Loading API keys from environment
```python
# In settings.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def openai(self) -> OpenAISettings:
        """OpenAI settings."""
        return OpenAISettings()

# In adapter code
def __init__(self, api_key: str | None = None):
    settings = get_settings()
    self._api_key = api_key or settings.openai.api_key
    self._client = OpenAI(api_key=self._api_key)
```

**Wrong**: Hardcoded API key
```python
# NEVER DO THIS
api_key = "sk-1234567890abcdef"
client = OpenAI(api_key=api_key)
```

**Wrong**: API key in config file
```python
# config.json - NEVER DO THIS
{
    "openai_api_key": "sk-1234567890abcdef"
}
```

### 2. Environment Variable Security

#### Rules

**MUST**: Use `.env.example` as template
- Include all required environment variables
- Use placeholder values (not real credentials)
- Document each variable's purpose

**MUST**: Add `.env` to `.gitignore`
- Prevent accidental commits of secrets
- Also ignore `.env.local`, `.env.*.local`

**MUST**: Provide clear error messages for missing keys
- Validate required environment variables at startup
- Guide users to set missing variables

**MUST**: Allow optional environment variables
- Voyage API key is optional if using OpenAI
- OpenAI API key is optional if using Voyage
- Use empty string defaults for optional keys

#### Examples

**Correct**: .env.example template
```bash
# ============================================================================
# OpenAI Configuration (when EMBEDDING_PROVIDER=openai)
# ============================================================================
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# ============================================================================
# Voyage AI Configuration (when EMBEDDING_PROVIDER=voyage)
# Get API key from: https://dash.voyageai.com/
# ============================================================================
# VOYAGE_API_KEY=pa-your-api-key-here
# VOYAGE_EMBEDDING_MODEL=voyage-3
```

**Correct**: .gitignore patterns
```
# Environment
.env
.env.local
.env.*.local

# Secrets (never commit these)
*.pem
*.key
credentials.json
```

**Correct**: Runtime validation for required keys
```python
def __init__(self, api_key: str | None = None):
    settings = get_settings()
    self._api_key = api_key or settings.voyage.api_key

    if not self._api_key:
        raise EmbeddingError(
            "Voyage API key not configured. "
            "Set VOYAGE_API_KEY in .env or pass api_key parameter."
        )
```

### 3. Logging and Error Messages

#### Rules

**MUST NOT**: Log API keys or sensitive credentials
- Never log API keys (full or partial)
- Never log password values
- Never log authorization tokens

**MUST**: Sanitize error messages
- Don't include API keys in exceptions
- Don't expose internal paths in production
- Don't leak database credentials

**MUST**: Use structured logging with safe context
- Log metadata (provider, model name, operation)
- Log IDs and counts (non-sensitive data)
- Redact sensitive fields in log context

**SHOULD**: Log security events
- Failed authentication attempts
- Rate limit violations
- Invalid API key formats

#### Examples

**Correct**: Logging without sensitive data
```python
logger = structlog.get_logger()

# Log operation metadata, not the key
self._logger = logger.bind(service="openai_embedding", model=self._model)

# Log counts and IDs
self._logger.info(
    "Embeddings generated",
    count=len(results),
    total_tokens=response.usage.total_tokens,
)

# Log article ID, not content
self._logger.info(
    "EmbedArticle request",
    article_id=request.article_id,
    title=request.title[:50] if request.title else "",  # Truncate for privacy
    embedding_type=embedding_type,
)
```

**Correct**: Safe error messages
```python
except OpenAIRateLimitError as e:
    if attempt == max_retries - 1:
        raise RateLimitError() from e  # Generic error, no details

    self._logger.warning(
        "Rate limited, retrying",
        attempt=attempt + 1,
        delay=delay,
        # NO api_key, NO auth details
    )
```

**Wrong**: Logging API keys
```python
# NEVER DO THIS
logger.info(f"Using API key: {api_key}")
logger.debug(f"Auth header: {headers['Authorization']}")
```

**Wrong**: Exposing sensitive data in exceptions
```python
# NEVER DO THIS
raise ValueError(f"Authentication failed with key {api_key}")
raise EmbeddingError(f"API request failed: {response.headers}")
```

### 4. Input Validation

#### Rules

**MUST**: Validate all external inputs
- gRPC request parameters
- Environment variables
- API responses

**MUST**: Sanitize text inputs for embeddings
- Limit text length to prevent DoS
- Check for malicious content patterns
- Truncate to model limits (8000 chars default)

**MUST**: Validate numeric ranges
- Embedding dimensions (positive integers)
- Batch sizes (within provider limits)
- Timeout values (reasonable ranges)

**SHOULD**: Use Pydantic for validation
- Type checking at runtime
- Automatic validation errors
- Clear error messages

#### Examples

**Correct**: Input sanitization for articles
```python
@dataclass(frozen=True)
class ArticleEmbeddingInput:
    """Input for embedding an article."""

    article_id: int
    title: str
    content: str
    url: str | None = None

    def to_text(self, max_length: int = 8000) -> str:
        """Convert to text for embedding.

        Truncates to max_length to stay within model limits.
        """
        combined = f"Title: {self.title}\n\nContent: {self.content}"

        if len(combined) > max_length:
            # Keep full title, truncate content
            title_part = f"Title: {self.title}\n\nContent: "
            remaining = max_length - len(title_part)
            combined = title_part + self.content[:remaining] + "..."

        return combined
```

**Correct**: Pydantic validation for settings
```python
class GrpcSettings(BaseSettings):
    """gRPC server configuration."""

    host: str = Field(default="0.0.0.0", description="gRPC server host")
    port: int = Field(default=50051, description="gRPC server port")
    max_workers: int = Field(default=10, description="Maximum number of worker threads")
    max_message_size: int = Field(
        default=100 * 1024 * 1024,  # 100MB
        description="Maximum message size in bytes",
    )
```

**Correct**: Validating batch limits
```python
def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
    """Generate embeddings for multiple texts."""
    if not texts:
        return []

    # OpenAI batch limit is 2048
    batch_size = 2048
    results: list[EmbeddingResult] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_results = self._embed_with_retry(batch)
        results.extend(batch_results)

    return results
```

**Wrong**: No input validation
```python
# NEVER DO THIS
def embed_text(self, text: str) -> EmbeddingResult:
    # Direct use without validation
    response = self._client.embeddings.create(input=text, model=self._model)
    return response.data[0].embedding
```

### 5. Error Handling

#### Rules

**MUST**: Handle exceptions without leaking sensitive data
- Catch specific exceptions first
- Use generic error messages for users
- Log detailed errors internally (without secrets)

**MUST**: Implement retry logic for transient failures
- Use exponential backoff with jitter
- Cap maximum retry delay
- Limit total retry attempts

**MUST**: Distinguish between error types
- Rate limit errors (retryable)
- Authentication errors (not retryable)
- Network errors (retryable)

**SHOULD**: Clean up resources in error cases
- Close HTTP clients
- Close gRPC channels
- Release locks/semaphores

#### Examples

**Correct**: Exception hierarchy
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

**Correct**: Retry with exponential backoff
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
                error=str(e),  # Generic error string, not the exception object
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

**Correct**: Resource cleanup
```python
def __del__(self):
    """Clean up HTTP client."""
    if hasattr(self, "_client"):
        self._client.close()

def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
    """Context manager exit."""
    self.close()
```

**Wrong**: Exposing internal errors to users
```python
# NEVER DO THIS
except Exception as e:
    return {"error": str(e), "traceback": traceback.format_exc()}
```

### 6. Docker Security

#### Rules

**MUST**: Run as non-root user
- Create dedicated user in Dockerfile
- Switch to non-root before CMD
- Use UID/GID 1000 for consistency

**MUST**: Use minimal base images
- Use `python:3.13-slim` for smaller attack surface
- Multi-stage builds to exclude build tools
- Only copy necessary files to runtime image

**MUST**: Set security-related environment variables
- `PYTHONUNBUFFERED=1` for proper logging
- `PYTHONDONTWRITEBYTECODE=1` to prevent .pyc files

**MUST**: Pass secrets via environment variables
- Never bake secrets into images
- Use Docker secrets or env vars
- Document required environment variables

**SHOULD**: Use specific image tags
- Avoid `latest` tag
- Pin specific versions (`python:3.13-slim`)
- Update regularly for security patches

#### Examples

**Correct**: Multi-stage Dockerfile with non-root user
```dockerfile
# syntax=docker/dockerfile:1

# ============================================================================
# Build stage: Install dependencies with uv
# ============================================================================
FROM python:3.13-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies (without dev dependencies)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ src/
COPY proto/ proto/
COPY scripts/ scripts/

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ============================================================================
# Runtime stage: Minimal image for production
# ============================================================================
FROM python:3.13-slim AS runtime

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY --from=builder /app/src /app/src

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose gRPC port
EXPOSE 50051

# Run the application
CMD ["python", "-m", "catchup_ai"]
```

**Correct**: Docker Compose with environment variables
```yaml
services:
  catchup-ai:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
      # Pass API keys from host environment
      - EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - VOYAGE_API_KEY=${VOYAGE_API_KEY:-}
      # gRPC server config
      - GRPC_HOST=0.0.0.0
      - GRPC_PORT=50051
    ports:
      - "50051:50051"
    restart: unless-stopped
```

**Wrong**: Running as root
```dockerfile
# NEVER DO THIS
FROM python:3.13-slim

# No USER directive - runs as root by default
CMD ["python", "-m", "catchup_ai"]
```

**Wrong**: Hardcoded secrets in Dockerfile
```dockerfile
# NEVER DO THIS
ENV OPENAI_API_KEY=sk-1234567890abcdef
```

### 7. gRPC Security

#### Rules

**MUST**: Document use of insecure channels
- Add comments explaining why insecure is used
- Plan migration to TLS for production
- Note in README and deployment docs

**MUST**: Implement graceful shutdown
- Handle SIGTERM and SIGINT signals
- Allow in-flight requests to complete
- Use grace period for shutdown (30s)

**SHOULD**: Implement authentication for production
- Use TLS certificates
- Implement token-based auth
- Validate client credentials

**SHOULD**: Set message size limits
- Prevent DoS via large messages
- Use reasonable defaults (100MB)
- Document limits in API docs

#### Examples

**Correct**: Server with graceful shutdown
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

**Correct**: Documented insecure channel usage
```python
def _ensure_connection(self) -> EmbeddingServiceStub:
    """Ensure gRPC connection is established.

    Note: Uses insecure channel for local development.
    TODO: Migrate to secure channel with TLS for production.
    """
    if self._stub is None:
        # Local development - insecure channel
        # Production should use grpc.secure_channel() with certificates
        self._channel = grpc.insecure_channel(self._settings.grpc_address)
        self._stub = EmbeddingServiceStub(self._channel)
        logger.info(
            "Connected to backend EmbeddingService",
            address=self._settings.grpc_address,
        )
    return self._stub
```

**Correct**: Message size limits
```python
server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=settings.grpc.max_workers),
    options=[
        ("grpc.max_send_message_length", settings.grpc.max_message_size),
        ("grpc.max_receive_message_length", settings.grpc.max_message_size),
    ],
)
```

**Future**: TLS configuration (production)
```python
# TODO: Implement for production
def create_secure_server() -> grpc.Server:
    """Create server with TLS encryption."""
    with open('server.key', 'rb') as f:
        private_key = f.read()
    with open('server.crt', 'rb') as f:
        certificate_chain = f.read()

    server_credentials = grpc.ssl_server_credentials(
        [(private_key, certificate_chain)]
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    server.add_secure_port('[::]:50051', server_credentials)
    return server
```

## Enforcement Checklist

Use this checklist when reviewing code changes:

### API Key Security
- [ ] No API keys hardcoded in source code
- [ ] No API keys in committed config files
- [ ] API keys loaded from environment variables
- [ ] API key validation implemented with pydantic
- [ ] Clear error messages for missing/invalid keys
- [ ] `.env` file in `.gitignore`
- [ ] `.env.example` provided with placeholders

### Logging Security
- [ ] No API keys in log messages
- [ ] No credentials in log context
- [ ] Error messages don't expose secrets
- [ ] Structured logging with safe metadata
- [ ] Truncated content for privacy (titles, snippets)
- [ ] Security events logged (rate limits, auth failures)

### Input Validation
- [ ] All gRPC inputs validated
- [ ] Text truncated to safe limits
- [ ] Numeric ranges checked
- [ ] Batch sizes within provider limits
- [ ] Pydantic models used for validation
- [ ] Clear validation error messages

### Error Handling
- [ ] Specific exceptions caught first
- [ ] Generic error messages for users
- [ ] Detailed errors logged internally (no secrets)
- [ ] Retry logic with exponential backoff
- [ ] Resource cleanup in error cases
- [ ] Exception hierarchy for error types

### Docker Security
- [ ] Non-root user created and used
- [ ] Minimal base image (`python:3.13-slim`)
- [ ] Multi-stage build used
- [ ] Security env vars set (`PYTHONUNBUFFERED`, etc.)
- [ ] Secrets passed via environment (not baked in)
- [ ] Specific image tags (not `latest`)
- [ ] Only necessary files copied to runtime

### gRPC Security
- [ ] Insecure channel usage documented
- [ ] Graceful shutdown implemented
- [ ] Message size limits set
- [ ] Plan for TLS migration noted
- [ ] Authentication strategy documented
- [ ] Resource cleanup on shutdown

### General
- [ ] Dependencies regularly updated
- [ ] Security vulnerabilities scanned
- [ ] Principle of least privilege followed
- [ ] Defense in depth applied
- [ ] Security comments and TODOs documented

## Common Vulnerabilities to Avoid

### 1. Hardcoded Secrets
**Risk**: Secrets in source code can be exposed via git history, logs, or repository access.

**Prevention**:
- Use environment variables exclusively
- Add `.env` to `.gitignore`
- Scan commits for secrets before pushing
- Use git hooks to prevent secret commits

### 2. Information Disclosure
**Risk**: Detailed error messages can reveal system internals to attackers.

**Prevention**:
- Generic error messages for external users
- Detailed errors only in internal logs
- No stack traces in API responses
- Sanitize all error messages

### 3. Insufficient Input Validation
**Risk**: Malformed inputs can cause crashes, DoS, or injection attacks.

**Prevention**:
- Validate all external inputs
- Use Pydantic for type checking
- Sanitize and truncate text inputs
- Set reasonable size limits

### 4. Denial of Service
**Risk**: Large requests or rate limit abuse can exhaust resources.

**Prevention**:
- Set message size limits
- Implement rate limiting
- Use timeouts for all operations
- Batch size limits enforced

### 5. Running as Root in Containers
**Risk**: Container breakout could compromise the host system.

**Prevention**:
- Always create and use non-root user
- Use minimal base images
- Apply security updates regularly
- Scan images for vulnerabilities

### 6. Insecure Communication
**Risk**: Unencrypted gRPC traffic can be intercepted.

**Prevention**:
- Document insecure channel usage
- Plan TLS migration for production
- Use VPNs or private networks
- Implement authentication

## Security Testing

### Manual Testing
1. **Environment validation**: Try running without required API keys
2. **Invalid inputs**: Send malformed gRPC requests
3. **Rate limiting**: Trigger rate limits and verify retry logic
4. **Error messages**: Verify no secrets in error responses
5. **Docker user**: Verify container runs as non-root (`docker exec <container> whoami`)

### Automated Testing
```python
def test_api_key_validation():
    """Test that invalid API keys are rejected."""
    with pytest.raises(ValueError, match="Invalid OpenAI API key format"):
        OpenAISettings(api_key="invalid-key")

def test_no_api_key_in_logs(caplog):
    """Test that API keys are not logged."""
    api_key = "sk-test123"
    adapter = OpenAIEmbeddingAdapter(api_key=api_key)

    # Perform operations
    adapter.embed_text("test")

    # Check logs don't contain API key
    assert api_key not in caplog.text

def test_input_truncation():
    """Test that long inputs are truncated."""
    article = ArticleEmbeddingInput(
        article_id=1,
        title="Title",
        content="A" * 10000,
    )
    text = article.to_text(max_length=8000)
    assert len(text) <= 8000
```

### Security Scanning
```bash
# Scan dependencies for vulnerabilities
uv run pip-audit

# Scan Docker images
docker scan catchup-ai:latest

# Check for secrets in git history
git secrets --scan

# Static analysis
bandit -r src/
```

## References

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [gRPC Authentication Guide](https://grpc.io/docs/guides/auth/)
- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Python Logging Security](https://owasp.org/www-community/vulnerabilities/Log_Injection)

## Version History

- **v1.0** (2026-01-23): Initial security standards based on catchup-ai codebase analysis
