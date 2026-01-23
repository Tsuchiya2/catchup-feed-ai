"""Tests for EmbeddingClient gRPC client."""

from unittest.mock import MagicMock, patch

import pytest

from catchup_ai.infra.grpc.embedding_client import EmbeddingClient, SimilarArticleResult


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    with patch("catchup_ai.infra.grpc.embedding_client.get_settings") as mock:
        settings = MagicMock()
        settings.backend.grpc_address = "localhost:50052"
        settings.backend.grpc_timeout = 30.0
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_grpc_channel():
    """Create mock gRPC channel."""
    with patch("catchup_ai.infra.grpc.embedding_client.grpc.insecure_channel") as mock:
        channel = MagicMock()
        mock.return_value = channel
        yield channel, mock


@pytest.fixture
def mock_stub():
    """Create mock EmbeddingServiceStub."""
    with patch(
        "catchup_ai.infra.grpc.embedding_client.EmbeddingServiceStub"
    ) as mock_class:
        stub = MagicMock()
        mock_class.return_value = stub
        yield stub


class TestSimilarArticleResult:
    """Tests for SimilarArticleResult dataclass."""

    def test_create_result(self):
        """Test creating a SimilarArticleResult."""
        result = SimilarArticleResult(article_id=123, similarity=0.95)

        assert result.article_id == 123
        assert result.similarity == 0.95


class TestEmbeddingClient:
    """Tests for EmbeddingClient."""

    def test_init_with_default_settings(self, mock_settings, mock_grpc_channel):
        """Test client initialization with default settings."""
        client = EmbeddingClient()

        assert client._settings.grpc_address == "localhost:50052"
        assert client._channel is None
        assert client._stub is None

    def test_init_with_custom_settings(self, mock_grpc_channel):
        """Test client initialization with custom settings."""
        custom_settings = MagicMock()
        custom_settings.grpc_address = "custom:9090"
        custom_settings.grpc_timeout = 60.0

        client = EmbeddingClient(settings=custom_settings)

        assert client._settings.grpc_address == "custom:9090"

    def test_ensure_connection_creates_channel(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test that _ensure_connection creates channel and stub."""
        channel, channel_mock = mock_grpc_channel

        client = EmbeddingClient()
        stub = client._ensure_connection()

        channel_mock.assert_called_once_with("localhost:50052")
        assert client._channel is channel
        assert client._stub is stub

    def test_ensure_connection_reuses_existing(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test that _ensure_connection reuses existing connection."""
        channel, channel_mock = mock_grpc_channel

        client = EmbeddingClient()
        stub1 = client._ensure_connection()
        stub2 = client._ensure_connection()

        # Should only create channel once
        channel_mock.assert_called_once()
        assert stub1 is stub2

    def test_close_closes_channel(self, mock_settings, mock_grpc_channel, mock_stub):
        """Test that close() closes the channel."""
        channel, _ = mock_grpc_channel

        client = EmbeddingClient()
        client._ensure_connection()
        client.close()

        channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None

    def test_context_manager(self, mock_settings, mock_grpc_channel, mock_stub):
        """Test using client as context manager."""
        channel, _ = mock_grpc_channel

        with EmbeddingClient() as client:
            client._ensure_connection()

        channel.close.assert_called_once()

    def test_store_embedding_success(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test successful embedding storage."""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.embedding_id = 42
        mock_stub.StoreEmbedding.return_value = mock_response

        client = EmbeddingClient()
        success, embedding_id, error = client.store_embedding(
            article_id=123,
            embedding=[0.1, 0.2, 0.3],
            embedding_type="content",
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
        )

        assert success is True
        assert embedding_id == 42
        assert error is None
        mock_stub.StoreEmbedding.assert_called_once()

    def test_store_embedding_failure(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test embedding storage failure."""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error_message = "Article not found"
        mock_stub.StoreEmbedding.return_value = mock_response

        client = EmbeddingClient()
        success, embedding_id, error = client.store_embedding(
            article_id=999,
            embedding=[0.1],
            embedding_type="content",
            provider="openai",
            model="test",
            dimension=1536,
        )

        assert success is False
        assert embedding_id is None
        assert error == "Article not found"

    def test_store_embedding_grpc_error(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test embedding storage with gRPC error."""
        import grpc

        # Create a custom RpcError subclass for testing
        class MockRpcError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.UNAVAILABLE

            def details(self):
                return "Service unavailable"

        mock_stub.StoreEmbedding.side_effect = MockRpcError()

        client = EmbeddingClient()
        success, embedding_id, error = client.store_embedding(
            article_id=123,
            embedding=[0.1],
            embedding_type="content",
            provider="openai",
            model="test",
            dimension=1536,
        )

        assert success is False
        assert embedding_id is None
        assert "gRPC error" in error

    def test_search_similar_success(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test successful similarity search."""
        mock_article1 = MagicMock()
        mock_article1.article_id = 1
        mock_article1.similarity = 0.95

        mock_article2 = MagicMock()
        mock_article2.article_id = 2
        mock_article2.similarity = 0.85

        mock_response = MagicMock()
        mock_response.articles = [mock_article1, mock_article2]
        mock_stub.SearchSimilar.return_value = mock_response

        client = EmbeddingClient()
        results = client.search_similar(
            embedding=[0.1, 0.2, 0.3],
            embedding_type="content",
            limit=10,
        )

        assert len(results) == 2
        assert results[0].article_id == 1
        assert results[0].similarity == 0.95
        assert results[1].article_id == 2
        mock_stub.SearchSimilar.assert_called_once()

    def test_search_similar_empty_results(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test similarity search with no results."""
        mock_response = MagicMock()
        mock_response.articles = []
        mock_stub.SearchSimilar.return_value = mock_response

        client = EmbeddingClient()
        results = client.search_similar(
            embedding=[0.1],
            embedding_type="content",
            limit=10,
        )

        assert results == []

    def test_search_similar_grpc_error(
        self, mock_settings, mock_grpc_channel, mock_stub
    ):
        """Test similarity search with gRPC error returns empty list."""
        import grpc

        # Create a custom RpcError subclass for testing
        class MockRpcError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.INTERNAL

            def details(self):
                return "Internal error"

        mock_stub.SearchSimilar.side_effect = MockRpcError()

        client = EmbeddingClient()
        results = client.search_similar(
            embedding=[0.1],
            embedding_type="content",
            limit=10,
        )

        assert results == []
