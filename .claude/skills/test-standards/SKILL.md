# Test Coding Standards for catchup-ai

**Version**: 1.0
**Last Updated**: 2026-01-23
**Test Framework**: pytest (>=8.0.0)
**Python Version**: >=3.13
**Project**: catchup-ai (Embedding, RAG, and Article Classification service)

## Overview

This document defines testing standards for the catchup-ai project based on pytest best practices and project architecture patterns. All standards support testability through dependency injection and clean architecture principles observed in the codebase.

## Tool Configuration

### Test Framework
- **pytest**: Modern Python testing framework
- **pytest-asyncio**: For async test support (`asyncio_mode = "auto"`)
- **pytest-cov**: For coverage reporting
- Test path: `tests/` (configured in `pyproject.toml`)

### Configuration
From `/Users/yujitsuchiya/catchup-feed-ai/pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Commands
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=catchup_ai --cov-report=html

# Run specific test file
pytest tests/unit/test_embedding_service.py

# Run specific test
pytest tests/unit/test_embedding_service.py::test_embed_text_success

# Run with verbose output
pytest -v

# Run with output capture disabled (see print statements)
pytest -s

# Run only failed tests from last run
pytest --lf

# Run in parallel (requires pytest-xdist)
pytest -n auto
```

## 1. Test File Organization

### Directory Structure
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests (fast, isolated)
│   ├── __init__.py
│   ├── conftest.py          # Unit-specific fixtures
│   ├── test_embedding_service.py
│   ├── test_openai_adapter.py
│   ├── test_voyage_adapter.py
│   ├── test_article_servicer.py
│   └── test_factory.py
└── integration/             # Integration tests (slower, external deps)
    ├── __init__.py
    ├── conftest.py          # Integration-specific fixtures
    ├── test_embedding_e2e.py
    └── test_grpc_server.py
```

### File Naming Rules
- **Pattern**: `test_<module_name>.py`
- **Examples**:
  - `test_embedding_service.py` tests `core/embedding/service.py`
  - `test_openai_adapter.py` tests `core/embedding/openai_adapter.py`
  - `test_article_servicer.py` tests `api/grpc/article_servicer.py`

### Test Discovery
- pytest discovers all files matching `test_*.py` or `*_test.py`
- All test functions must start with `test_`
- All test classes must start with `Test`

## 2. Test Function Naming

### Pattern: Descriptive Names with Underscores

**Format**: `test_<function_name>_<scenario>_<expected_result>`

**Examples**:
```python
# Basic success case
def test_embed_text_success():
    """Test embedding a single text returns EmbeddingResult."""

# Error case
def test_embed_text_empty_input_raises_error():
    """Test embedding empty text raises ValueError."""

# Edge case
def test_embed_text_max_length_truncates():
    """Test text longer than max_length is truncated."""

# Multiple scenarios for same function
def test_embed_texts_batch_success():
    """Test embedding multiple texts returns list of results."""

def test_embed_texts_empty_list_returns_empty():
    """Test embedding empty list returns empty list."""

def test_embed_texts_exceeds_batch_limit_splits_batches():
    """Test texts exceeding batch limit are split into multiple API calls."""
```

**Rules**:
- Use descriptive names that explain the test scenario
- Keep names concise but clear (avoid cryptic abbreviations)
- Separate words with underscores (snake_case)
- Start with `test_` (required for pytest discovery)
- Include context: what's being tested, under what conditions, what's expected

## 3. Test Function Structure (AAA Pattern)

### Pattern: Arrange-Act-Assert

**Every test should follow this structure:**

```python
def test_embed_text_success():
    """Test embedding a single text returns EmbeddingResult."""
    # Arrange - Set up test data and dependencies
    mock_client = Mock(spec=OpenAI)
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3])]
    mock_response.model = "text-embedding-3-small"
    mock_response.usage.total_tokens = 10
    mock_client.embeddings.create.return_value = mock_response

    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    adapter._client = mock_client

    # Act - Execute the code being tested
    result = adapter.embed_text("Hello, world!")

    # Assert - Verify the results
    assert isinstance(result, EmbeddingResult)
    assert result.vector == [0.1, 0.2, 0.3]
    assert result.model == "text-embedding-3-small"
    assert result.provider == "openai"
    assert result.tokens_used == 10
```

**Benefits**:
- Clear separation of concerns
- Easy to read and understand
- Easy to debug when tests fail

**Comments**:
- Use `# Arrange`, `# Act`, `# Assert` comments for complex tests
- For simple tests, structure is obvious without comments

## 4. Fixtures

### Pattern: Shared Test Data and Dependencies

**Example `tests/conftest.py`:**
```python
"""Shared fixtures for all tests."""

import pytest
from unittest.mock import Mock
from catchup_ai.core.embedding import (
    EmbeddingResult,
    ArticleEmbeddingInput,
)


@pytest.fixture
def sample_embedding_result() -> EmbeddingResult:
    """Sample embedding result for testing."""
    return EmbeddingResult(
        vector=[0.1, 0.2, 0.3, 0.4],
        model="text-embedding-3-small",
        provider="openai",
        tokens_used=10,
    )


@pytest.fixture
def sample_article_input() -> ArticleEmbeddingInput:
    """Sample article input for testing."""
    return ArticleEmbeddingInput(
        article_id=123,
        title="Test Article",
        content="This is test content for the article.",
        url="https://example.com/article",
    )


@pytest.fixture
def mock_openai_client() -> Mock:
    """Mock OpenAI client for testing."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3])]
    mock_response.model = "text-embedding-3-small"
    mock_response.usage.total_tokens = 10
    mock_client.embeddings.create.return_value = mock_response
    return mock_client
```

**Example `tests/unit/conftest.py`:**
```python
"""Unit test specific fixtures."""

import pytest
from unittest.mock import Mock, patch
from catchup_ai.core.embedding import OpenAIEmbeddingAdapter


@pytest.fixture
def openai_adapter_with_mock(mock_openai_client) -> OpenAIEmbeddingAdapter:
    """OpenAI adapter with mocked client."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    adapter._client = mock_openai_client
    return adapter


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("catchup_ai.infra.config.settings.get_settings") as mock:
        settings = Mock()
        settings.openai.api_key = "test-openai-key"
        settings.openai.embedding_model = "text-embedding-3-small"
        settings.voyage.api_key = "test-voyage-key"
        settings.voyage.embedding_model = "voyage-3"
        settings.embedding.provider = "openai"
        mock.return_value = settings
        yield settings
```

**Usage in tests:**
```python
def test_embed_text_with_fixture(openai_adapter_with_mock, sample_article_input):
    """Test using fixtures for setup."""
    result = openai_adapter_with_mock.embed_article(sample_article_input)
    assert isinstance(result, EmbeddingResult)
```

**Fixture Scopes**:
```python
# Function scope (default) - created/destroyed per test
@pytest.fixture
def sample_data():
    return {"key": "value"}

# Class scope - shared across test class
@pytest.fixture(scope="class")
def expensive_resource():
    resource = create_expensive_resource()
    yield resource
    resource.cleanup()

# Module scope - shared across test module
@pytest.fixture(scope="module")
def database_connection():
    conn = create_connection()
    yield conn
    conn.close()

# Session scope - shared across entire test session
@pytest.fixture(scope="session")
def global_config():
    return load_global_config()
```

**Rules**:
- Use fixtures for reusable test data and setup
- Keep fixtures focused (single responsibility)
- Use descriptive fixture names
- Document fixture purpose in docstring
- Prefer function scope unless needed otherwise
- Use `yield` for fixtures that need cleanup

## 5. Mocking External Dependencies

### Pattern: Mock External APIs and Services

**Mock OpenAI API calls:**
```python
from unittest.mock import Mock, patch
import pytest
from openai import RateLimitError as OpenAIRateLimitError


def test_embed_text_rate_limit_retry():
    """Test rate limit error triggers retry logic."""
    # Arrange
    mock_client = Mock()
    # Fail twice, succeed on third attempt
    mock_client.embeddings.create.side_effect = [
        OpenAIRateLimitError("Rate limited", response=Mock(), body=None),
        OpenAIRateLimitError("Rate limited", response=Mock(), body=None),
        Mock(
            data=[Mock(embedding=[0.1, 0.2])],
            model="text-embedding-3-small",
            usage=Mock(total_tokens=5),
        ),
    ]

    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    adapter._client = mock_client

    # Act
    result = adapter.embed_text("test")

    # Assert
    assert result.vector == [0.1, 0.2]
    assert mock_client.embeddings.create.call_count == 3


def test_embed_text_rate_limit_exhausted_raises():
    """Test rate limit errors beyond max retries raise RateLimitError."""
    # Arrange
    mock_client = Mock()
    mock_client.embeddings.create.side_effect = OpenAIRateLimitError(
        "Rate limited", response=Mock(), body=None
    )

    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    adapter._client = mock_client

    # Act & Assert
    with pytest.raises(RateLimitError):
        adapter.embed_text("test")
```

**Mock HTTP requests (for Voyage adapter):**
```python
from unittest.mock import Mock, patch


def test_voyage_embed_text_success():
    """Test Voyage API embedding success."""
    # Arrange
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}],
        "usage": {"total_tokens": 8},
    }

    with patch("httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Act
        adapter = VoyageEmbeddingAdapter(api_key="test-key")
        result = adapter.embed_text("test")

        # Assert
        assert result.vector == [0.1, 0.2, 0.3]
        assert result.provider == "voyage"
        mock_client.post.assert_called_once()


def test_voyage_embed_text_429_raises_rate_limit():
    """Test Voyage API 429 status raises RateLimitError."""
    # Arrange
    mock_response = Mock()
    mock_response.status_code = 429

    with patch("httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = VoyageEmbeddingAdapter(api_key="test-key")

        # Act & Assert
        with pytest.raises(RateLimitError):
            adapter.embed_text("test")
```

**Mock settings:**
```python
from unittest.mock import patch, Mock


def test_adapter_uses_settings_default():
    """Test adapter loads API key from settings when not provided."""
    # Arrange
    with patch("catchup_ai.core.embedding.openai_adapter.get_settings") as mock_settings:
        settings = Mock()
        settings.openai.api_key = "settings-api-key"
        settings.openai.embedding_model = "text-embedding-3-small"
        mock_settings.return_value = settings

        # Act
        adapter = OpenAIEmbeddingAdapter()

        # Assert
        assert adapter._api_key == "settings-api-key"
        assert adapter._model == "text-embedding-3-small"
```

**Rules**:
- Mock external API calls (OpenAI, Voyage, gRPC)
- Mock at the boundary (client objects, not internal methods)
- Use `Mock(spec=ClassName)` for type safety
- Use `side_effect` for multiple calls or exceptions
- Verify mock calls with `assert_called_once()`, `assert_called_with()`
- Use `patch` as context manager or decorator

## 6. Testing gRPC Servicers

### Pattern: Mock Dependencies, Test Request Handling

**Example `tests/unit/test_article_servicer.py`:**
```python
"""Tests for ArticleAIServicer."""

import pytest
from unittest.mock import Mock
import grpc

from catchup_ai.api.grpc import article_pb2
from catchup_ai.api.grpc.article_servicer import ArticleAIServicer
from catchup_ai.core.embedding import (
    EmbeddingResult,
    EmbeddingError,
    RateLimitError,
)


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    return Mock()


@pytest.fixture
def mock_embedding_client():
    """Mock embedding client for backend communication."""
    return Mock()


@pytest.fixture
def servicer(mock_embedding_service, mock_embedding_client):
    """ArticleAIServicer with mocked dependencies."""
    return ArticleAIServicer(
        embedding_service=mock_embedding_service,
        embedding_client=mock_embedding_client,
    )


@pytest.fixture
def grpc_context():
    """Mock gRPC context."""
    return Mock(spec=grpc.ServicerContext)


def test_embed_article_success(servicer, mock_embedding_service, grpc_context):
    """Test successful article embedding."""
    # Arrange
    request = article_pb2.EmbedArticleRequest(
        article_id=123,
        title="Test Article",
        content="This is test content.",
        url="https://example.com",
        embedding_type="content",
    )

    mock_result = EmbeddingResult(
        vector=[0.1, 0.2, 0.3],
        model="text-embedding-3-small",
        provider="openai",
        tokens_used=10,
    )
    mock_embedding_service.embed_article.return_value = mock_result

    # Act
    response = servicer.EmbedArticle(request, grpc_context)

    # Assert
    assert response.success is True
    assert response.article_id == 123
    assert response.embedding_dimension == 3
    assert list(response.embedding) == [0.1, 0.2, 0.3]
    assert response.provider == "openai"
    assert response.model == "text-embedding-3-small"
    assert response.embedding_type == "content"


def test_embed_article_embedding_error(servicer, mock_embedding_service, grpc_context):
    """Test EmbeddingError returns error response."""
    # Arrange
    request = article_pb2.EmbedArticleRequest(
        article_id=123,
        title="Test",
        content="Content",
    )

    mock_embedding_service.embed_article.side_effect = EmbeddingError("API failed")

    # Act
    response = servicer.EmbedArticle(request, grpc_context)

    # Assert
    assert response.success is False
    assert response.article_id == 123
    assert "API failed" in response.error_message


def test_search_similar_by_query(servicer, mock_embedding_service, mock_embedding_client, grpc_context):
    """Test searching similar articles by query text."""
    # Arrange
    request = article_pb2.SearchSimilarRequest(
        query="test query",
        limit=5,
    )

    mock_embedding_result = EmbeddingResult(
        vector=[0.1, 0.2],
        model="text-embedding-3-small",
        provider="openai",
        tokens_used=3,
    )
    mock_embedding_service.embed_text.return_value = mock_embedding_result

    mock_search_results = [
        Mock(article_id=1, similarity=0.95),
        Mock(article_id=2, similarity=0.87),
    ]
    mock_embedding_client.search_similar.return_value = mock_search_results

    # Act
    response = servicer.SearchSimilar(request, grpc_context)

    # Assert
    assert len(response.articles) == 2
    assert response.articles[0].article_id == 1
    assert response.articles[0].similarity_score == 0.95
    mock_embedding_service.embed_text.assert_called_once_with("test query")
    mock_embedding_client.search_similar.assert_called_once()


def test_search_similar_unimplemented_method(servicer, grpc_context):
    """Test unimplemented RPC method sets UNIMPLEMENTED status."""
    # Arrange
    request = article_pb2.QueryArticlesRequest(query="test")

    # Act
    response = servicer.QueryArticles(request, grpc_context)

    # Assert
    grpc_context.set_code.assert_called_once_with(grpc.StatusCode.UNIMPLEMENTED)
    assert "Week 5-6" in grpc_context.set_details.call_args[0][0]
```

**Rules for gRPC servicer tests**:
- Mock embedding service and clients (dependency injection)
- Create request objects using generated protobuf classes
- Mock gRPC context with `Mock(spec=grpc.ServicerContext)`
- Test success path (verify response fields)
- Test error paths (verify error handling)
- Test gRPC status codes for errors
- Verify mock calls to ensure proper delegation

## 7. Testing Async Code

### Pattern: Use pytest-asyncio

**Configuration**: `asyncio_mode = "auto"` in `pyproject.toml` enables automatic async detection.

**Example async tests:**
```python
"""Tests for async embedding operations."""

import pytest
from unittest.mock import AsyncMock, Mock


# Simple async test (auto-detected with asyncio_mode = "auto")
async def test_embed_text_async():
    """Test async embedding call."""
    # Arrange
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1, 0.2])]
    mock_response.model = "text-embedding-3-small"
    mock_response.usage.total_tokens = 5
    mock_client.embeddings.create.return_value = mock_response

    adapter = AsyncOpenAIEmbeddingAdapter(api_key="test-key")
    adapter._client = mock_client

    # Act
    result = await adapter.embed_text("test")

    # Assert
    assert result.vector == [0.1, 0.2]


# Async fixture
@pytest.fixture
async def async_adapter():
    """Async adapter fixture with cleanup."""
    adapter = AsyncOpenAIEmbeddingAdapter(api_key="test-key")
    yield adapter
    await adapter.close()


async def test_with_async_fixture(async_adapter):
    """Test using async fixture."""
    # Test code using async_adapter
    pass
```

**Rules**:
- Mark async tests with `async def test_*()`
- Use `AsyncMock` for async mock objects
- Use `await` when calling async functions
- Use `asyncio_mode = "auto"` for automatic detection
- Use async fixtures for async setup/teardown

## 8. Parametrized Tests

### Pattern: Test Multiple Scenarios with Same Logic

**Example:**
```python
import pytest


@pytest.mark.parametrize(
    "text,expected_length",
    [
        ("Hello", 5),
        ("Hello, world!", 13),
        ("", 0),
        ("Test with unicode: こんにちは", 24),
    ],
)
def test_article_to_text_format(text, expected_length):
    """Test ArticleEmbeddingInput.to_text() formatting."""
    article = ArticleEmbeddingInput(
        article_id=1,
        title="Title",
        content=text,
    )
    result = article.to_text()

    assert "Title: Title" in result
    assert "Content: " in result
    assert text in result


@pytest.mark.parametrize(
    "provider,adapter_class",
    [
        ("openai", OpenAIEmbeddingAdapter),
        ("voyage", VoyageEmbeddingAdapter),
    ],
)
def test_factory_creates_correct_adapter(mock_settings, provider, adapter_class):
    """Test factory creates correct adapter for each provider."""
    # Arrange
    mock_settings.embedding.provider = provider

    # Act
    service = create_embedding_service()

    # Assert
    assert isinstance(service, adapter_class)


@pytest.mark.parametrize(
    "attempt,expected_min,expected_max",
    [
        (0, 0.5, 1.5),      # 2^0 * [0.5, 1.5] = [0.5, 1.5]
        (1, 1.0, 3.0),      # 2^1 * [0.5, 1.5] = [1.0, 3.0]
        (2, 2.0, 6.0),      # 2^2 * [0.5, 1.5] = [2.0, 6.0]
        (5, 15.0, 30.0),    # Capped at max_delay=30
    ],
)
def test_calculate_retry_delay(attempt, expected_min, expected_max):
    """Test exponential backoff with jitter."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key")

    # Run multiple times to account for jitter
    for _ in range(10):
        delay = adapter._calculate_retry_delay(attempt)
        assert expected_min <= delay <= expected_max
```

**Rules**:
- Use `@pytest.mark.parametrize` for multiple test cases
- First argument: parameter names (comma-separated string)
- Second argument: list of test values (tuples for multiple params)
- Test function receives parameters as arguments
- Each parameter set runs as separate test
- Useful for boundary values, edge cases, multiple inputs

## 9. Exception Testing

### Pattern: Assert Exceptions with pytest.raises

**Example:**
```python
import pytest
from catchup_ai.core.embedding import (
    EmbeddingError,
    RateLimitError,
    TokenLimitError,
)


def test_empty_text_raises_error():
    """Test embedding empty text raises ValueError."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key")

    with pytest.raises(ValueError, match="Text cannot be empty"):
        adapter.embed_text("")


def test_rate_limit_error_includes_retry_after():
    """Test RateLimitError includes retry_after attribute."""
    with pytest.raises(RateLimitError) as exc_info:
        raise RateLimitError(retry_after=30.0)

    assert exc_info.value.retry_after == 30.0
    assert "30.0" in str(exc_info.value)


def test_token_limit_error_includes_details():
    """Test TokenLimitError includes token count details."""
    with pytest.raises(TokenLimitError) as exc_info:
        raise TokenLimitError(tokens=10000, limit=8000)

    assert exc_info.value.tokens == 10000
    assert exc_info.value.limit == 8000
    assert "10000" in str(exc_info.value)
    assert "8000" in str(exc_info.value)


def test_invalid_api_key_raises_embedding_error():
    """Test invalid API key raises EmbeddingError."""
    mock_client = Mock()
    mock_client.embeddings.create.side_effect = Exception("Invalid API key")

    adapter = OpenAIEmbeddingAdapter(api_key="invalid")
    adapter._client = mock_client

    with pytest.raises(EmbeddingError, match="Failed after 3 attempts"):
        adapter.embed_text("test")
```

**Rules**:
- Use `with pytest.raises(ExceptionType):` to assert exceptions
- Use `match` parameter for error message regex matching
- Capture exception details with `as exc_info`
- Access exception: `exc_info.value`
- Access type: `exc_info.type`
- Access traceback: `exc_info.traceback`

## 10. Test Markers

### Pattern: Organize and Filter Tests

**Example:**
```python
import pytest


# Mark slow tests
@pytest.mark.slow
def test_embed_large_batch():
    """Test embedding 1000 texts (slow)."""
    # Test code
    pass


# Skip tests conditionally
@pytest.mark.skipif(
    not has_voyage_api_key(),
    reason="VOYAGE_API_KEY not set",
)
def test_voyage_real_api():
    """Test with real Voyage API."""
    # Test code
    pass


# Mark as expected failure
@pytest.mark.xfail(reason="Known issue with Unicode handling")
def test_unicode_edge_case():
    """Test Unicode edge case (currently fails)."""
    # Test code
    pass


# Mark integration tests
@pytest.mark.integration
def test_grpc_server_integration():
    """Integration test for gRPC server."""
    # Test code
    pass


# Mark tests requiring external services
@pytest.mark.requires_openai
def test_with_real_openai_api():
    """Test with real OpenAI API."""
    # Test code
    pass
```

**Running tests by marker:**
```bash
# Run only fast tests (exclude slow)
pytest -m "not slow"

# Run only integration tests
pytest -m integration

# Run slow or integration tests
pytest -m "slow or integration"

# Skip tests requiring external services
pytest -m "not requires_openai"
```

**Register custom markers in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "requires_openai: marks tests that need OpenAI API key",
    "requires_voyage: marks tests that need Voyage API key",
]
```

## 11. Coverage Requirements

### Pattern: Measure Test Coverage

**Run coverage:**
```bash
# Run with coverage report
pytest --cov=catchup_ai --cov-report=html

# View HTML report
open htmlcov/index.html

# Show missing lines in terminal
pytest --cov=catchup_ai --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=catchup_ai --cov-fail-under=80
```

**Configuration in `pyproject.toml`:**
```toml
[tool.coverage.run]
source = ["src/catchup_ai"]
omit = [
    "*/tests/*",
    "*/generated/*",
    "*/__pycache__/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

**Coverage goals**:
- **Overall**: 80%+ coverage
- **Core domain logic** (`core/`): 90%+ coverage
- **API adapters** (`api/`): 80%+ coverage
- **Infrastructure** (`infra/`): 70%+ coverage
- **Generated code**: Exclude from coverage

## 12. Test Documentation

### Pattern: Clear Test Docstrings

**Every test must have a docstring explaining what it tests:**

```python
def test_embed_text_success():
    """Test embedding a single text returns EmbeddingResult with correct structure.

    Verifies that:
    - Result is EmbeddingResult instance
    - Vector contains expected values
    - Metadata (model, provider, tokens) is populated
    """
    # Test code
    pass


def test_retry_logic_exponential_backoff():
    """Test retry mechanism uses exponential backoff with jitter.

    This test verifies the retry logic:
    1. Retries on transient failures (rate limit, network error)
    2. Uses exponential backoff (2^attempt)
    3. Adds jitter to prevent thundering herd
    4. Caps delay at max_delay (30 seconds)
    5. Raises after max_retries exhausted
    """
    # Test code
    pass
```

**Docstring guidelines**:
- Start with one-line summary
- Use imperative mood ("Test X returns Y", not "Tests X")
- Add details for complex test scenarios
- Document what's being verified
- Include context if test setup is non-obvious

## 13. Concrete Test Examples

### Example 1: Testing EmbeddingService Abstract Class

**File**: `tests/unit/test_embedding_service.py`
```python
"""Tests for embedding service core functionality."""

import pytest
from catchup_ai.core.embedding import (
    ArticleEmbeddingInput,
    EmbeddingResult,
    EmbeddingService,
)


class TestArticleEmbeddingInput:
    """Tests for ArticleEmbeddingInput."""

    def test_to_text_combines_title_and_content(self):
        """Test to_text() combines title and content with labels."""
        # Arrange
        article = ArticleEmbeddingInput(
            article_id=1,
            title="Test Title",
            content="Test content here.",
        )

        # Act
        result = article.to_text()

        # Assert
        assert "Title: Test Title" in result
        assert "Content: Test content here." in result

    def test_to_text_truncates_long_content(self):
        """Test to_text() truncates content exceeding max_length."""
        # Arrange
        long_content = "x" * 10000
        article = ArticleEmbeddingInput(
            article_id=1,
            title="Short Title",
            content=long_content,
        )

        # Act
        result = article.to_text(max_length=100)

        # Assert
        assert len(result) <= 100
        assert "Title: Short Title" in result
        assert result.endswith("...")

    def test_to_text_preserves_full_title(self):
        """Test to_text() always keeps full title even when truncating."""
        # Arrange
        article = ArticleEmbeddingInput(
            article_id=1,
            title="This is a longer title that should be preserved",
            content="x" * 1000,
        )

        # Act
        result = article.to_text(max_length=100)

        # Assert
        assert article.title in result


class TestEmbeddingResult:
    """Tests for EmbeddingResult."""

    def test_dimension_returns_vector_length(self):
        """Test dimension property returns length of vector."""
        # Arrange
        result = EmbeddingResult(
            vector=[0.1, 0.2, 0.3, 0.4],
            model="test-model",
            provider="test",
            tokens_used=10,
        )

        # Act & Assert
        assert result.dimension == 4

    def test_immutable_frozen_dataclass(self):
        """Test EmbeddingResult is immutable (frozen)."""
        # Arrange
        result = EmbeddingResult(
            vector=[0.1],
            model="test",
            provider="test",
            tokens_used=1,
        )

        # Act & Assert
        with pytest.raises(AttributeError):
            result.model = "changed"
```

### Example 2: Testing OpenAI Adapter with Mocks

**File**: `tests/unit/test_openai_adapter.py`
```python
"""Tests for OpenAI embedding adapter."""

import pytest
from unittest.mock import Mock, patch
from openai import RateLimitError as OpenAIRateLimitError

from catchup_ai.core.embedding import (
    OpenAIEmbeddingAdapter,
    EmbeddingResult,
    RateLimitError,
    EmbeddingError,
)


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client with successful response."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1, 0.2, 0.3]),
    ]
    mock_response.model = "text-embedding-3-small"
    mock_response.usage.total_tokens = 10
    mock_client.embeddings.create.return_value = mock_response
    return mock_client


class TestOpenAIEmbeddingAdapter:
    """Tests for OpenAIEmbeddingAdapter."""

    def test_embed_text_success(self, mock_openai_client):
        """Test successful single text embedding."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        adapter._client = mock_openai_client

        # Act
        result = adapter.embed_text("Hello")

        # Assert
        assert isinstance(result, EmbeddingResult)
        assert result.vector == [0.1, 0.2, 0.3]
        assert result.model == "text-embedding-3-small"
        assert result.provider == "openai"
        assert result.tokens_used == 10
        mock_openai_client.embeddings.create.assert_called_once()

    def test_embed_texts_batch_success(self, mock_openai_client):
        """Test batch embedding of multiple texts."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        mock_openai_client.embeddings.create.return_value.data = [
            Mock(embedding=[0.1, 0.2]),
            Mock(embedding=[0.3, 0.4]),
        ]
        adapter._client = mock_openai_client

        # Act
        results = adapter.embed_texts(["Text 1", "Text 2"])

        # Assert
        assert len(results) == 2
        assert all(isinstance(r, EmbeddingResult) for r in results)
        assert results[0].vector == [0.1, 0.2]
        assert results[1].vector == [0.3, 0.4]

    def test_embed_texts_empty_list(self):
        """Test embedding empty list returns empty list."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")

        # Act
        results = adapter.embed_texts([])

        # Assert
        assert results == []

    def test_rate_limit_retry_succeeds(self, mock_openai_client):
        """Test retry logic succeeds after rate limit errors."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        mock_openai_client.embeddings.create.side_effect = [
            OpenAIRateLimitError("Rate limited", response=Mock(), body=None),
            OpenAIRateLimitError("Rate limited", response=Mock(), body=None),
            Mock(
                data=[Mock(embedding=[0.5, 0.6])],
                model="text-embedding-3-small",
                usage=Mock(total_tokens=5),
            ),
        ]
        adapter._client = mock_openai_client

        # Act
        result = adapter.embed_text("test")

        # Assert
        assert result.vector == [0.5, 0.6]
        assert mock_openai_client.embeddings.create.call_count == 3

    def test_rate_limit_max_retries_exceeded(self, mock_openai_client):
        """Test max retries exceeded raises RateLimitError."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        mock_openai_client.embeddings.create.side_effect = OpenAIRateLimitError(
            "Rate limited", response=Mock(), body=None
        )
        adapter._client = mock_openai_client

        # Act & Assert
        with pytest.raises(RateLimitError):
            adapter.embed_text("test")

        # Should try 3 times (max_retries = 3)
        assert mock_openai_client.embeddings.create.call_count == 3

    def test_generic_error_raises_embedding_error(self, mock_openai_client):
        """Test generic API error raises EmbeddingError after retries."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        mock_openai_client.embeddings.create.side_effect = Exception("API error")
        adapter._client = mock_openai_client

        # Act & Assert
        with pytest.raises(EmbeddingError, match="Failed after 3 attempts"):
            adapter.embed_text("test")

    @pytest.mark.parametrize("attempt,min_delay,max_delay", [
        (0, 0.5, 1.5),
        (1, 1.0, 3.0),
        (2, 2.0, 6.0),
    ])
    def test_calculate_retry_delay_exponential(self, attempt, min_delay, max_delay):
        """Test retry delay uses exponential backoff with jitter."""
        # Arrange
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")

        # Act - run multiple times due to jitter
        delays = [adapter._calculate_retry_delay(attempt) for _ in range(10)]

        # Assert
        assert all(min_delay <= d <= max_delay for d in delays)

    def test_uses_settings_by_default(self):
        """Test adapter loads API key from settings when not provided."""
        # Arrange
        with patch("catchup_ai.core.embedding.openai_adapter.get_settings") as mock:
            settings = Mock()
            settings.openai.api_key = "settings-key"
            settings.openai.embedding_model = "text-embedding-3-small"
            mock.return_value = settings

            # Act
            adapter = OpenAIEmbeddingAdapter()

            # Assert
            assert adapter._api_key == "settings-key"
            assert adapter._model == "text-embedding-3-small"
```

### Example 3: Testing Factory Pattern

**File**: `tests/unit/test_factory.py`
```python
"""Tests for embedding service factory."""

import pytest
from unittest.mock import Mock, patch

from catchup_ai.core.embedding import (
    create_embedding_service,
    OpenAIEmbeddingAdapter,
    EmbeddingService,
)
from catchup_ai.infra.config.settings import EmbeddingProvider


class TestEmbeddingServiceFactory:
    """Tests for create_embedding_service factory function."""

    def test_creates_openai_adapter_by_default(self):
        """Test factory creates OpenAI adapter when provider is openai."""
        # Arrange
        with patch("catchup_ai.core.embedding.factory.get_settings") as mock:
            settings = Mock()
            settings.embedding.provider = EmbeddingProvider.OPENAI
            settings.openai.api_key = "test-key"
            settings.openai.embedding_model = "text-embedding-3-small"
            mock.return_value = settings

            # Act
            service = create_embedding_service()

            # Assert
            assert isinstance(service, OpenAIEmbeddingAdapter)
            assert isinstance(service, EmbeddingService)

    def test_creates_voyage_adapter_when_specified(self):
        """Test factory creates Voyage adapter when provider is voyage."""
        # Arrange
        with patch("catchup_ai.core.embedding.factory.get_settings") as mock:
            settings = Mock()
            settings.voyage.api_key = "test-voyage-key"
            settings.voyage.embedding_model = "voyage-3"
            mock.return_value = settings

            # Act
            service = create_embedding_service(provider="voyage")

            # Assert
            from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter
            assert isinstance(service, VoyageEmbeddingAdapter)

    def test_raises_error_for_unsupported_provider(self):
        """Test factory raises ValueError for unsupported provider."""
        # Act & Assert
        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            create_embedding_service(provider="unsupported")

    @pytest.mark.parametrize("provider_str,expected_enum", [
        ("openai", EmbeddingProvider.OPENAI),
        ("OPENAI", EmbeddingProvider.OPENAI),
        ("voyage", EmbeddingProvider.VOYAGE),
        ("Voyage", EmbeddingProvider.VOYAGE),
    ])
    def test_accepts_string_or_enum_provider(self, provider_str, expected_enum):
        """Test factory accepts both string and enum for provider."""
        # Arrange
        with patch("catchup_ai.core.embedding.factory.get_settings") as mock:
            settings = Mock()
            settings.openai.api_key = "test"
            settings.openai.embedding_model = "model"
            settings.voyage.api_key = "test"
            settings.voyage.embedding_model = "model"
            mock.return_value = settings

            # Act
            service = create_embedding_service(provider=provider_str)

            # Assert
            assert isinstance(service, EmbeddingService)
```

## 14. Enforcement Checklist

Before committing code, ensure all tests follow these standards:

### Test Organization
- [ ] Test files in `tests/unit/` or `tests/integration/`
- [ ] Test file names match `test_<module>.py` pattern
- [ ] Test function names match `test_<function>_<scenario>_<result>` pattern
- [ ] Tests organized by class/module under test

### Test Structure
- [ ] All tests follow AAA pattern (Arrange-Act-Assert)
- [ ] Each test has clear docstring explaining what it tests
- [ ] Tests are independent (no shared state)
- [ ] Tests clean up after themselves (use fixtures with yield)

### Mocking
- [ ] External APIs and services are mocked
- [ ] Mocks use `Mock(spec=ClassName)` for type safety
- [ ] Mock calls are verified with assertions
- [ ] Settings are mocked when needed

### Coverage
- [ ] Core domain logic (`core/`) has 90%+ coverage
- [ ] API adapters (`api/`) have 80%+ coverage
- [ ] New code has accompanying tests
- [ ] Edge cases and error paths are tested

### Fixtures
- [ ] Reusable test data in fixtures
- [ ] Fixtures have descriptive names and docstrings
- [ ] Fixture scope appropriate for use case
- [ ] Fixtures in appropriate `conftest.py` file

### Assertions
- [ ] Assertions are specific and clear
- [ ] Error messages tested with `pytest.raises(match=...)`
- [ ] Multiple related assertions grouped logically
- [ ] No unnecessary assertions

### Documentation
- [ ] Every test has a docstring
- [ ] Complex test setup is commented
- [ ] Test markers are documented
- [ ] Fixtures are documented

### Tools
- [ ] `pytest` runs without errors
- [ ] `pytest --cov=catchup_ai` shows adequate coverage
- [ ] No warnings from pytest
- [ ] Tests run fast (unit tests < 1s each)

## Quick Reference

### Common Test Patterns

**Basic unit test:**
```python
def test_function_success():
    """Test function returns expected result."""
    # Arrange
    input_data = "test"

    # Act
    result = my_function(input_data)

    # Assert
    assert result == "expected"
```

**Test with fixture:**
```python
def test_with_fixture(sample_data):
    """Test using fixture."""
    result = process(sample_data)
    assert result is not None
```

**Test with mock:**
```python
def test_with_mock():
    """Test with mocked dependency."""
    mock_client = Mock()
    mock_client.method.return_value = "mocked"

    service = MyService(client=mock_client)
    result = service.do_something()

    assert result == "mocked"
    mock_client.method.assert_called_once()
```

**Test exception:**
```python
def test_raises_error():
    """Test function raises ValueError."""
    with pytest.raises(ValueError, match="Invalid input"):
        my_function("invalid")
```

**Parametrized test:**
```python
@pytest.mark.parametrize("input,expected", [
    ("a", 1),
    ("b", 2),
])
def test_parametrized(input, expected):
    """Test with multiple inputs."""
    assert my_function(input) == expected
```

### Commands Quick Reference

```bash
# Run all tests
pytest

# Run specific file
pytest tests/unit/test_embedding_service.py

# Run specific test
pytest tests/unit/test_embedding_service.py::test_embed_text_success

# Run with coverage
pytest --cov=catchup_ai --cov-report=html

# Run verbose
pytest -v

# Run parallel (requires pytest-xdist)
pytest -n auto

# Run only failed tests
pytest --lf

# Run by marker
pytest -m "not slow"
```

---

**Note**: These standards should be followed for all new tests and applied when modifying existing tests. Update this document as testing patterns evolve.
