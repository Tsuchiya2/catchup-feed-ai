"""Tests for OpenAI embedding adapter."""

from unittest.mock import MagicMock, patch

import pytest

from catchup_ai.core.embedding.openai_adapter import OpenAIEmbeddingAdapter
from catchup_ai.core.embedding.service import RateLimitError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    with patch("catchup_ai.core.embedding.openai_adapter.get_settings") as mock:
        settings = MagicMock()
        settings.openai.api_key = "sk-test-key"
        settings.openai.embedding_model = "text-embedding-3-small"
        mock.return_value = settings
        yield mock


@pytest.fixture
def mock_openai_client():
    """Create mock OpenAI client."""
    with patch("catchup_ai.core.embedding.openai_adapter.OpenAI") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


class TestOpenAIEmbeddingAdapter:
    """Tests for OpenAIEmbeddingAdapter."""

    def test_init_with_settings(self, mock_settings, mock_openai_client):
        """Test adapter initialization uses settings."""
        adapter = OpenAIEmbeddingAdapter()

        assert adapter._model == "text-embedding-3-small"
        assert adapter._api_key == "sk-test-key"

    def test_init_with_custom_params(self, mock_settings, mock_openai_client):
        """Test adapter initialization with custom parameters."""
        adapter = OpenAIEmbeddingAdapter(
            api_key="sk-custom-key",
            model="text-embedding-3-large",
        )

        assert adapter._model == "text-embedding-3-large"
        assert adapter._api_key == "sk-custom-key"

    def test_embed_text_success(self, mock_settings, mock_openai_client):
        """Test successful text embedding."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_response.model = "text-embedding-3-small"
        mock_response.usage.total_tokens = 10
        mock_openai_client.embeddings.create.return_value = mock_response

        adapter = OpenAIEmbeddingAdapter()
        result = adapter.embed_text("Hello, world!")

        assert result.vector == [0.1, 0.2, 0.3]
        assert result.model == "text-embedding-3-small"
        assert result.provider == "openai"
        assert result.tokens_used == 10

    def test_embed_texts_batch(self, mock_settings, mock_openai_client):
        """Test batch text embedding."""
        # Setup mock response for batch
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2]),
            MagicMock(embedding=[0.3, 0.4]),
        ]
        mock_response.model = "text-embedding-3-small"
        mock_response.usage.total_tokens = 20
        mock_openai_client.embeddings.create.return_value = mock_response

        adapter = OpenAIEmbeddingAdapter()
        results = adapter.embed_texts(["Text 1", "Text 2"])

        assert len(results) == 2
        assert results[0].vector == [0.1, 0.2]
        assert results[1].vector == [0.3, 0.4]

    def test_embed_texts_empty_list(self, mock_settings, mock_openai_client):
        """Test batch embedding with empty list returns empty list."""
        adapter = OpenAIEmbeddingAdapter()
        results = adapter.embed_texts([])

        assert results == []
        mock_openai_client.embeddings.create.assert_not_called()

    def test_embed_text_retries_on_rate_limit(self, mock_settings, mock_openai_client):
        """Test that rate limit errors trigger retry."""
        from openai import RateLimitError as OpenAIRateLimitError

        # First call raises rate limit, second succeeds
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1])]
        mock_response.model = "test"
        mock_response.usage.total_tokens = 5

        mock_openai_client.embeddings.create.side_effect = [
            OpenAIRateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            ),
            mock_response,
        ]

        adapter = OpenAIEmbeddingAdapter()

        with patch("catchup_ai.core.embedding.openai_adapter.time.sleep"):
            result = adapter.embed_text("Test")

        assert result.vector == [0.1]
        assert mock_openai_client.embeddings.create.call_count == 2

    def test_embed_text_raises_after_max_retries(self, mock_settings, mock_openai_client):
        """Test that persistent errors raise after max retries."""
        from openai import RateLimitError as OpenAIRateLimitError

        mock_openai_client.embeddings.create.side_effect = OpenAIRateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )

        adapter = OpenAIEmbeddingAdapter()

        with patch("catchup_ai.core.embedding.openai_adapter.time.sleep"):
            with pytest.raises(RateLimitError):
                adapter.embed_text("Test")

        assert mock_openai_client.embeddings.create.call_count == 3

    def test_calculate_retry_delay_exponential_backoff(self, mock_settings, mock_openai_client):
        """Test retry delay calculation uses exponential backoff."""
        adapter = OpenAIEmbeddingAdapter()

        # Check delays increase exponentially (with jitter, so check ranges)
        delay0 = adapter._calculate_retry_delay(0)
        delay1 = adapter._calculate_retry_delay(1)
        delay2 = adapter._calculate_retry_delay(2)

        # Base delays: 2^0=1, 2^1=2, 2^2=4, with jitter *0.5 to *1.5
        assert 0.5 <= delay0 <= 1.5  # 1 * (0.5 to 1.5)
        assert 1.0 <= delay1 <= 3.0  # 2 * (0.5 to 1.5)
        assert 2.0 <= delay2 <= 6.0  # 4 * (0.5 to 1.5)

    def test_calculate_retry_delay_capped_at_max(self, mock_settings, mock_openai_client):
        """Test retry delay is capped at maximum value."""
        adapter = OpenAIEmbeddingAdapter()

        # Very high attempt number should still be capped
        delay = adapter._calculate_retry_delay(10)

        # Max is 30, with jitter should be between 15 and 45
        assert delay <= 45.0
