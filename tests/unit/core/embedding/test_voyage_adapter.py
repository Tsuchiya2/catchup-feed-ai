"""Tests for Voyage AI embedding adapter.

Note: These tests require httpx to be installed.
Run: uv pip install httpx
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Skip all tests if httpx is not available
pytest.importorskip("httpx")


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    with patch("catchup_ai.core.embedding.voyage_adapter.get_settings") as mock:
        settings = MagicMock()
        settings.voyage.api_key = "pa-test-key"
        settings.voyage.embedding_model = "voyage-3"
        mock.return_value = settings
        yield mock


@pytest.fixture
def mock_httpx():
    """Mock httpx module for testing."""
    mock_module = MagicMock()
    mock_client = MagicMock()
    mock_module.Client.return_value = mock_client

    with patch.dict(sys.modules, {"httpx": mock_module}):
        yield mock_client


class TestVoyageEmbeddingAdapterInit:
    """Tests for VoyageEmbeddingAdapter initialization."""

    def test_init_without_api_key_raises_error(self, mock_settings, mock_httpx):
        """Test that missing API key raises error."""
        from catchup_ai.core.embedding.service import EmbeddingError
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        mock_settings.return_value.voyage.api_key = ""

        with pytest.raises(EmbeddingError, match="Voyage API key not configured"):
            VoyageEmbeddingAdapter()


class TestVoyageRetryLogic:
    """Tests for retry logic in VoyageEmbeddingAdapter."""

    def test_calculate_retry_delay_exponential_backoff(self, mock_settings, mock_httpx):
        """Test retry delay calculation uses exponential backoff."""
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        adapter = VoyageEmbeddingAdapter()

        # Check delays increase exponentially (with jitter)
        delay0 = adapter._calculate_retry_delay(0)
        delay1 = adapter._calculate_retry_delay(1)
        delay2 = adapter._calculate_retry_delay(2)

        # Base delays: 2^0=1, 2^1=2, 2^2=4, with jitter *0.5 to *1.5
        assert 0.5 <= delay0 <= 1.5
        assert 1.0 <= delay1 <= 3.0
        assert 2.0 <= delay2 <= 6.0

    def test_calculate_retry_delay_capped_at_max(self, mock_settings, mock_httpx):
        """Test retry delay is capped at maximum value."""
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        adapter = VoyageEmbeddingAdapter()

        # Very high attempt number should still be capped at max (30)
        delay = adapter._calculate_retry_delay(10)

        # Max is 30, with jitter should be between 15 and 45
        assert delay <= 45.0


class TestVoyageEmbedding:
    """Tests for embedding generation."""

    def test_embed_texts_empty_list(self, mock_settings, mock_httpx):
        """Test batch embedding with empty list returns empty list."""
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        adapter = VoyageEmbeddingAdapter()

        results = adapter.embed_texts([])
        assert results == []

    def test_embed_text_success(self, mock_settings, mock_httpx):
        """Test successful single text embedding."""
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "usage": {"total_tokens": 10},
        }
        mock_httpx.post.return_value = mock_response

        adapter = VoyageEmbeddingAdapter()
        result = adapter.embed_text("test text")

        assert result.vector == [0.1, 0.2, 0.3]
        assert result.provider == "voyage"
        assert result.model == "voyage-3"

    def test_embed_texts_batch_success(self, mock_settings, mock_httpx):
        """Test successful batch text embedding."""
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
            ],
            "usage": {"total_tokens": 20},
        }
        mock_httpx.post.return_value = mock_response

        adapter = VoyageEmbeddingAdapter()
        results = adapter.embed_texts(["text1", "text2"])

        assert len(results) == 2
        assert results[0].vector == [0.1, 0.2]
        assert results[1].vector == [0.3, 0.4]

    def test_embed_texts_rate_limit_error(self, mock_settings, mock_httpx):
        """Test rate limit error triggers retry."""
        from catchup_ai.core.embedding.service import RateLimitError
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_httpx.post.return_value = mock_response

        adapter = VoyageEmbeddingAdapter()

        with patch.object(adapter, "_calculate_retry_delay", return_value=0.01):
            with pytest.raises(RateLimitError):
                adapter.embed_text("test")

    def test_embed_texts_api_error(self, mock_settings, mock_httpx):
        """Test API error handling."""
        from catchup_ai.core.embedding.service import EmbeddingError
        from catchup_ai.core.embedding.voyage_adapter import VoyageEmbeddingAdapter

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_httpx.post.return_value = mock_response

        adapter = VoyageEmbeddingAdapter()

        with patch.object(adapter, "_calculate_retry_delay", return_value=0.01):
            with pytest.raises(EmbeddingError, match="Voyage API error"):
                adapter.embed_text("test")
