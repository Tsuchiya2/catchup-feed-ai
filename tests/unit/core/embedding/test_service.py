"""Tests for embedding service interfaces and data classes."""

import pytest

from catchup_ai.core.embedding.service import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingResult,
    RateLimitError,
    TokenLimitError,
)


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_create_embedding_result(self):
        """Test creating an EmbeddingResult with valid data."""
        vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = EmbeddingResult(
            vector=vector,
            model="text-embedding-3-small",
            provider="openai",
            tokens_used=10,
        )

        assert result.vector == vector
        assert result.model == "text-embedding-3-small"
        assert result.provider == "openai"
        assert result.tokens_used == 10

    def test_embedding_result_dimension(self):
        """Test dimension property returns correct vector length."""
        vector = [0.1] * 1536  # OpenAI default dimension
        result = EmbeddingResult(
            vector=vector,
            model="text-embedding-3-small",
            provider="openai",
            tokens_used=100,
        )

        assert result.dimension == 1536

    def test_embedding_result_is_frozen(self):
        """Test that EmbeddingResult is immutable."""
        result = EmbeddingResult(
            vector=[0.1, 0.2],
            model="test",
            provider="openai",
            tokens_used=5,
        )

        with pytest.raises(AttributeError):
            result.model = "different"  # type: ignore

    def test_embedding_result_equality(self):
        """Test that two EmbeddingResults with same data are equal."""
        result1 = EmbeddingResult(
            vector=[0.1, 0.2],
            model="test",
            provider="openai",
            tokens_used=5,
        )
        result2 = EmbeddingResult(
            vector=[0.1, 0.2],
            model="test",
            provider="openai",
            tokens_used=5,
        )

        assert result1 == result2


class TestArticleEmbeddingInput:
    """Tests for ArticleEmbeddingInput dataclass."""

    def test_create_article_embedding_input(self):
        """Test creating an ArticleEmbeddingInput with required fields."""
        article = ArticleEmbeddingInput(
            article_id=123,
            title="Test Article",
            content="This is the content of the test article.",
        )

        assert article.article_id == 123
        assert article.title == "Test Article"
        assert article.content == "This is the content of the test article."
        assert article.url is None

    def test_create_article_embedding_input_with_url(self):
        """Test creating an ArticleEmbeddingInput with optional URL."""
        article = ArticleEmbeddingInput(
            article_id=123,
            title="Test Article",
            content="Content here.",
            url="https://example.com/article",
        )

        assert article.url == "https://example.com/article"

    def test_to_text_combines_title_and_content(self):
        """Test that to_text combines title and content correctly."""
        article = ArticleEmbeddingInput(
            article_id=1,
            title="My Title",
            content="My content here.",
        )

        text = article.to_text()

        assert "Title: My Title" in text
        assert "Content: My content here." in text

    def test_to_text_truncates_long_content(self):
        """Test that to_text truncates content exceeding max_length."""
        long_content = "A" * 10000
        article = ArticleEmbeddingInput(
            article_id=1,
            title="Short Title",
            content=long_content,
        )

        text = article.to_text(max_length=500)

        assert len(text) <= 503  # 500 + "..."
        assert text.endswith("...")
        assert "Title: Short Title" in text

    def test_to_text_preserves_short_content(self):
        """Test that to_text doesn't truncate short content."""
        article = ArticleEmbeddingInput(
            article_id=1,
            title="Title",
            content="Short content.",
        )

        text = article.to_text(max_length=8000)

        assert not text.endswith("...")
        assert "Short content." in text


class TestEmbeddingExceptions:
    """Tests for embedding exception classes."""

    def test_embedding_error(self):
        """Test EmbeddingError base exception."""
        error = EmbeddingError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert isinstance(error, Exception)

    def test_rate_limit_error_with_retry_after(self):
        """Test RateLimitError with retry_after value."""
        error = RateLimitError(retry_after=30.0)

        assert error.retry_after == 30.0
        assert "30.0s" in str(error)
        assert isinstance(error, EmbeddingError)

    def test_rate_limit_error_without_retry_after(self):
        """Test RateLimitError without retry_after value."""
        error = RateLimitError()

        assert error.retry_after is None
        assert isinstance(error, EmbeddingError)

    def test_token_limit_error(self):
        """Test TokenLimitError with token counts."""
        error = TokenLimitError(tokens=10000, limit=8192)

        assert error.tokens == 10000
        assert error.limit == 8192
        assert "10000 > 8192" in str(error)
        assert isinstance(error, EmbeddingError)
