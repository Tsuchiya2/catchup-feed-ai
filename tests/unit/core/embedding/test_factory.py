"""Tests for embedding service factory."""

from unittest.mock import MagicMock, patch

import pytest

from catchup_ai.core.embedding.factory import create_embedding_service, get_embedding_service
from catchup_ai.core.embedding.openai_adapter import OpenAIEmbeddingAdapter
from catchup_ai.core.embedding.service import EmbeddingError
from catchup_ai.infra.config.settings import EmbeddingProvider


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    with patch("catchup_ai.core.embedding.factory.get_settings") as mock:
        settings = MagicMock()
        settings.embedding.provider = EmbeddingProvider.OPENAI
        settings.openai.api_key = "sk-test-key"
        settings.openai.embedding_model = "text-embedding-3-small"
        settings.voyage.api_key = "pa-test-key"
        settings.voyage.embedding_model = "voyage-3"
        mock.return_value = settings
        yield settings, mock


class TestCreateEmbeddingService:
    """Tests for create_embedding_service function."""

    def test_create_openai_service(self, mock_settings):
        """Test creating OpenAI embedding service."""
        settings, _ = mock_settings
        settings.embedding.provider = EmbeddingProvider.OPENAI

        with patch(
            "catchup_ai.core.embedding.factory.OpenAIEmbeddingAdapter"
        ) as mock_adapter:
            mock_adapter.return_value = MagicMock(spec=OpenAIEmbeddingAdapter)
            service = create_embedding_service()

            mock_adapter.assert_called_once()
            assert service is not None

    def test_create_voyage_service(self, mock_settings):
        """Test creating Voyage embedding service."""
        settings, _ = mock_settings
        settings.embedding.provider = EmbeddingProvider.VOYAGE

        # Voyage adapter is lazy-imported inside the function
        with patch(
            "catchup_ai.core.embedding.voyage_adapter.VoyageEmbeddingAdapter"
        ) as mock_adapter:
            mock_adapter.return_value = MagicMock()
            service = create_embedding_service()

            mock_adapter.assert_called_once()
            assert service is not None

    def test_create_service_with_custom_provider(self, mock_settings):
        """Test creating service with explicit provider override."""
        settings, _ = mock_settings
        settings.embedding.provider = EmbeddingProvider.OPENAI  # Default

        # Voyage adapter is lazy-imported inside the function
        with patch(
            "catchup_ai.core.embedding.voyage_adapter.VoyageEmbeddingAdapter"
        ) as mock_adapter:
            mock_adapter.return_value = MagicMock()
            # Override with voyage
            service = create_embedding_service(provider=EmbeddingProvider.VOYAGE)

            mock_adapter.assert_called_once()
            assert service is not None

    def test_openai_missing_api_key_raises_error(self, mock_settings):
        """Test that missing OpenAI API key raises error."""
        settings, _ = mock_settings
        settings.embedding.provider = EmbeddingProvider.OPENAI
        settings.openai.api_key = ""

        with patch(
            "catchup_ai.core.embedding.factory.OpenAIEmbeddingAdapter"
        ) as mock_adapter:
            mock_adapter.side_effect = EmbeddingError("API key not configured")

            with pytest.raises(EmbeddingError, match="API key"):
                create_embedding_service()


class TestGetEmbeddingService:
    """Tests for get_embedding_service alias function."""

    def test_get_service_is_alias_for_create(self, mock_settings):
        """Test that get_embedding_service is an alias for create_embedding_service."""
        # Verify it's the same function
        assert get_embedding_service is create_embedding_service

    def test_get_service_creates_new_instance_each_call(self, mock_settings):
        """Test that each call creates a new service instance (no caching)."""
        with patch(
            "catchup_ai.core.embedding.factory.OpenAIEmbeddingAdapter"
        ) as mock_adapter:
            mock_adapter.return_value = MagicMock(spec=OpenAIEmbeddingAdapter)

            service1 = get_embedding_service()
            service2 = get_embedding_service()

            # Each call creates a new instance
            assert mock_adapter.call_count == 2
            # Verify both services were created
            assert service1 is not None
            assert service2 is not None
