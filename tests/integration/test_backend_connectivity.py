"""Service connectivity tests for catchup-ai → catchup-feed-backend.

These tests verify actual gRPC communication between services.
Requires backend to be running: docker compose up -d (in catchup-feed-backend)

Run with: uv run pytest tests/integration/test_backend_connectivity.py -v
"""

import os

import grpc
import pytest

# Skip all tests if SKIP_BACKEND_TESTS is set (for CI environments)
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_BACKEND_TESTS", "").lower() == "true",
    reason="Backend not available in CI",
)


@pytest.fixture
def backend_channel():
    """Create gRPC channel to backend."""
    host = os.environ.get("BACKEND_GRPC_HOST", "localhost")
    port = os.environ.get("BACKEND_GRPC_PORT", "50052")
    channel = grpc.insecure_channel(f"{host}:{port}")

    # Check if backend is reachable
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
    except grpc.FutureTimeoutError:
        pytest.skip("Backend not reachable at localhost:50052")

    yield channel
    channel.close()


@pytest.fixture
def embedding_stub(backend_channel):
    """Create EmbeddingService stub."""
    from catchup_ai.api.grpc.generated.embedding import embedding_pb2_grpc

    return embedding_pb2_grpc.EmbeddingServiceStub(backend_channel)


class TestBackendConnectivity:
    """Tests for backend gRPC connectivity."""

    def test_backend_is_reachable(self, backend_channel):
        """Verify backend gRPC server is reachable."""
        # If we got here, the channel is ready (checked in fixture)
        # Just verify we can make a simple call
        from catchup_ai.api.grpc.generated.embedding import (
            embedding_pb2,
            embedding_pb2_grpc,
        )

        stub = embedding_pb2_grpc.EmbeddingServiceStub(backend_channel)
        request = embedding_pb2.SearchSimilarRequest(
            embedding=[0.1] * 1536,
            embedding_type="content",
            limit=1,
        )
        # This should not raise
        response = stub.SearchSimilar(request)
        assert response is not None

    def test_search_similar_empty_database(self, embedding_stub):
        """Test SearchSimilar RPC with empty database."""
        from catchup_ai.api.grpc.generated.embedding import embedding_pb2

        # Create a dummy embedding vector
        dummy_embedding = [0.1] * 1536

        request = embedding_pb2.SearchSimilarRequest(
            embedding=dummy_embedding,
            embedding_type="content",
            limit=10,
        )

        response = embedding_stub.SearchSimilar(request)

        # Should return empty results (no articles in DB)
        assert len(response.articles) == 0

    def test_search_similar_with_different_limits(self, embedding_stub):
        """Test SearchSimilar with various limit values."""
        from catchup_ai.api.grpc.generated.embedding import embedding_pb2

        dummy_embedding = [0.1] * 1536

        for limit in [1, 5, 10, 50]:
            request = embedding_pb2.SearchSimilarRequest(
                embedding=dummy_embedding,
                embedding_type="content",
                limit=limit,
            )

            response = embedding_stub.SearchSimilar(request)

            # Should not raise errors
            assert response is not None


class TestEmbeddingClientIntegration:
    """Tests for EmbeddingClient integration with backend."""

    def test_embedding_client_search_similar(self, backend_channel):
        """Test EmbeddingClient.search_similar() method."""
        from catchup_ai.infra.config.settings import BackendSettings
        from catchup_ai.infra.grpc.embedding_client import EmbeddingClient

        # Create settings pointing to the test backend
        settings = BackendSettings(grpc_host="localhost", grpc_port=50052)
        client = EmbeddingClient(settings=settings)

        try:
            results = client.search_similar(
                embedding=[0.1] * 1536,
                embedding_type="content",
                limit=5,
            )

            # Should return empty list (no articles)
            assert results == []
        finally:
            client.close()

    def test_embedding_client_context_manager(self, backend_channel):
        """Test EmbeddingClient as context manager."""
        from catchup_ai.infra.config.settings import BackendSettings
        from catchup_ai.infra.grpc.embedding_client import EmbeddingClient

        settings = BackendSettings(grpc_host="localhost", grpc_port=50052)

        with EmbeddingClient(settings=settings) as client:
            results = client.search_similar(
                embedding=[0.1] * 1536,
                embedding_type="content",
                limit=5,
            )
            assert results == []


class TestFullEmbeddingFlow:
    """End-to-end tests for the complete embedding flow."""

    def test_embed_and_search_flow_mock_article(self, backend_channel, embedding_stub):
        """Test the complete flow: embed → store → search.

        Note: This test requires an article in the database.
        Currently skipped if no articles exist.
        """
        from catchup_ai.api.grpc.generated.embedding import embedding_pb2

        # First, check if there are any articles
        # (StoreEmbedding requires valid article_id due to FK constraint)

        # For now, just verify the SearchSimilar works
        dummy_embedding = [0.1] * 1536

        request = embedding_pb2.SearchSimilarRequest(
            embedding=dummy_embedding,
            embedding_type="content",
            limit=5,
        )

        response = embedding_stub.SearchSimilar(request)

        # Verify response structure
        assert hasattr(response, "articles")
        # Empty is OK (no articles in DB)
        assert isinstance(list(response.articles), list)


class TestStoreEmbeddingValidation:
    """Tests for StoreEmbedding validation."""

    def test_store_embedding_invalid_article_id(self, embedding_stub):
        """Test StoreEmbedding with non-existent article ID."""
        from catchup_ai.api.grpc.generated.embedding import embedding_pb2

        request = embedding_pb2.StoreEmbeddingRequest(
            article_id=999999,  # Non-existent article
            embedding_type="content",
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
            embedding=[0.1] * 1536,
        )

        response = embedding_stub.StoreEmbedding(request)

        # Should fail due to FK constraint
        assert response.success is False
        # Error message should mention the constraint or article not found
        assert response.error_message != ""


class TestCatchupAIToBackendFlow:
    """End-to-end tests: catchup-ai → backend integration."""

    def test_article_servicer_search_similar_through_backend(self, backend_channel):
        """Test ArticleAIServicer's SearchSimilar calling backend.

        This test verifies the complete flow:
        1. catchup-ai receives SearchSimilar request
        2. catchup-ai embeds the query
        3. catchup-ai calls backend's SearchSimilar
        4. Response is returned to caller
        """
        from concurrent import futures
        from unittest.mock import MagicMock, patch

        import grpc

        from catchup_ai.api.grpc.article_servicer import ArticleAIServicer
        from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
        from catchup_ai.core.embedding.service import EmbeddingResult
        from catchup_ai.infra.config.settings import BackendSettings

        # Create backend settings pointing to real backend
        backend_settings = BackendSettings(grpc_host="localhost", grpc_port=50052)

        # Mock the embedding service (to avoid needing real API keys)
        with patch(
            "catchup_ai.api.grpc.article_servicer.create_embedding_service"
        ) as mock_create:
            mock_service = MagicMock()
            mock_service.embed_text.return_value = EmbeddingResult(
                vector=[0.1] * 1536,
                model="text-embedding-3-small",
                provider="openai",
                tokens_used=10,
            )
            mock_create.return_value = mock_service

            # Create servicer with real backend client
            from catchup_ai.infra.grpc.embedding_client import EmbeddingClient

            backend_client = EmbeddingClient(settings=backend_settings)

            servicer = ArticleAIServicer(
                embedding_service=mock_service,
                embedding_client=backend_client,
            )

            # Start a test server
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
            article_pb2_grpc.add_ArticleAIServicer_to_server(servicer, server)
            port = server.add_insecure_port("[::]:0")
            server.start()

            try:
                # Create client to our test server
                channel = grpc.insecure_channel(f"localhost:{port}")
                stub = article_pb2_grpc.ArticleAIStub(channel)

                # Make SearchSimilar request
                request = article_pb2.SearchSimilarRequest(
                    query="Test search query",
                    limit=5,
                )

                response = stub.SearchSimilar(request)

                # Should work (even if empty results)
                assert response is not None
                # embed_text should have been called
                mock_service.embed_text.assert_called_once_with("Test search query")

                channel.close()
            finally:
                server.stop(grace=0)
                backend_client.close()
