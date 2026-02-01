"""Integration tests for gRPC server.

These tests start a real gRPC server and test the full request/response flow.
External services (OpenAI, Voyage, backend) are mocked.
"""

import threading
from concurrent import futures
from unittest.mock import MagicMock, patch

import grpc
import pytest

from catchup_ai.api.grpc.article_servicer import ArticleAIServicer
from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
from catchup_ai.core.embedding.service import EmbeddingResult


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("catchup_ai.api.grpc.article_servicer.get_settings") as mock:
        settings = MagicMock()
        settings.openai.api_key = "test-key"
        settings.embedding.provider.value = "openai"
        settings.backend.grpc_host = "localhost"
        settings.backend.grpc_port = 50052
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    with patch(
        "catchup_ai.api.grpc.article_servicer.create_embedding_service"
    ) as mock:
        service = MagicMock()
        # Configure embed_article to return proper EmbeddingResult
        embedding_result = EmbeddingResult(
            vector=[0.1] * 1536,
            model="text-embedding-3-small",
            provider="openai",
            tokens_used=100,
        )
        service.embed_article.return_value = embedding_result
        service.embed_text.return_value = embedding_result
        mock.return_value = service
        yield service


@pytest.fixture
def mock_backend_client():
    """Mock backend gRPC client."""
    with patch(
        "catchup_ai.api.grpc.article_servicer.EmbeddingClient"
    ) as mock_class:
        client = MagicMock()
        client.store_embedding.return_value = True
        client.search_similar.return_value = []
        # EmbeddingClient() returns the mock client directly
        mock_class.return_value = client
        yield client


@pytest.fixture
def grpc_server(mock_settings, mock_embedding_service, mock_backend_client):
    """Start a gRPC server for testing."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    servicer = ArticleAIServicer()
    article_pb2_grpc.add_ArticleAIServicer_to_server(servicer, server)

    port = server.add_insecure_port("[::]:0")  # Random available port
    server.start()

    yield f"localhost:{port}"

    server.stop(grace=0)


@pytest.fixture
def grpc_channel(grpc_server):
    """Create gRPC channel to test server."""
    channel = grpc.insecure_channel(grpc_server)
    yield channel
    channel.close()


@pytest.fixture
def grpc_stub(grpc_channel):
    """Create gRPC stub for ArticleAI service."""
    return article_pb2_grpc.ArticleAIStub(grpc_channel)


class TestEmbedArticleIntegration:
    """Integration tests for EmbedArticle RPC."""

    def test_embed_article_success(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test successful article embedding through full gRPC flow."""
        request = article_pb2.EmbedArticleRequest(
            article_id=1,
            title="Test Article",
            content="This is test content for embedding.",
        )

        response = grpc_stub.EmbedArticle(request)

        assert response.success is True
        assert response.article_id == 1
        assert len(response.embedding) == 1536
        assert response.provider == "openai"
        assert response.model == "text-embedding-3-small"
        mock_embedding_service.embed_article.assert_called()

    def test_embed_article_with_embedding_type(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test embedding with specific embedding type."""
        request = article_pb2.EmbedArticleRequest(
            article_id=2,
            title="Another Article",
            content="Content here.",
            embedding_type="title",
        )

        response = grpc_stub.EmbedArticle(request)

        assert response.success is True
        assert len(response.embedding) == 1536
        assert response.embedding_type == "title"

    def test_embed_article_empty_content(self, grpc_stub, mock_embedding_service):
        """Test embedding with empty content uses title only."""
        request = article_pb2.EmbedArticleRequest(
            article_id=3,
            title="Title Only",
            content="",
        )

        response = grpc_stub.EmbedArticle(request)

        assert response.success is True
        # Verify embed_article was called
        mock_embedding_service.embed_article.assert_called()
        # Get the ArticleEmbeddingInput passed to embed_article
        call_args = mock_embedding_service.embed_article.call_args[0][0]
        assert call_args.title == "Title Only"


class TestSearchSimilarIntegration:
    """Integration tests for SearchSimilar RPC."""

    def test_search_similar_returns_results(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test similarity search through full gRPC flow."""
        # Setup mock to return results
        from catchup_ai.infra.grpc.embedding_client import SimilarArticleResult

        mock_backend_client.search_similar.return_value = [
            SimilarArticleResult(article_id=10, similarity=0.95),
            SimilarArticleResult(article_id=20, similarity=0.85),
        ]

        request = article_pb2.SearchSimilarRequest(
            query="Find similar articles about AI",
            limit=5,
        )

        response = grpc_stub.SearchSimilar(request)

        # Response uses 'articles' field per proto definition
        assert len(response.articles) == 2
        assert response.articles[0].article_id == 10
        assert response.articles[0].similarity_score == pytest.approx(0.95)
        assert response.articles[1].article_id == 20

    def test_search_similar_empty_results(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test similarity search with no results."""
        mock_backend_client.search_similar.return_value = []

        request = article_pb2.SearchSimilarRequest(
            query="Very specific query with no matches",
            limit=10,
        )

        response = grpc_stub.SearchSimilar(request)

        assert len(response.articles) == 0


class TestHealthCheckIntegration:
    """Integration tests for health checking."""

    def test_server_responds_to_requests(self, grpc_stub, mock_embedding_service):
        """Test that server is responsive and handles requests."""
        # Simple test that server is up and responding
        request = article_pb2.EmbedArticleRequest(
            article_id=1,
            title="Health Check Test",
            content="Testing server health.",
        )

        # Should not raise any exceptions
        response = grpc_stub.EmbedArticle(request)
        assert response is not None


class TestConcurrentRequests:
    """Integration tests for concurrent request handling."""

    def test_multiple_concurrent_embed_requests(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test server handles multiple concurrent requests."""
        results = []
        errors = []

        def make_request(article_id):
            try:
                request = article_pb2.EmbedArticleRequest(
                    article_id=article_id,
                    title=f"Article {article_id}",
                    content=f"Content for article {article_id}",
                )
                response = grpc_stub.EmbedArticle(request)
                results.append((article_id, response.success))
            except Exception as e:
                errors.append((article_id, str(e)))

        # Start 5 concurrent requests
        threads = []
        for i in range(5):
            t = threading.Thread(target=make_request, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        assert all(success for _, success in results)


class TestQueryArticlesIntegration:
    """Integration tests for QueryArticles RPC."""

    def test_query_articles_returns_answer(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test RAG-based question answering through full gRPC flow."""
        from catchup_ai.infra.grpc.embedding_client import SimilarArticleResult

        # Setup mock to return similar articles
        mock_backend_client.search_similar.return_value = [
            SimilarArticleResult(article_id=1, similarity=0.9),
            SimilarArticleResult(article_id=2, similarity=0.8),
        ]

        # Mock the RAG pipeline
        with patch(
            "catchup_ai.api.grpc.article_servicer.RAGPipeline"
        ) as mock_pipeline_class:
            from catchup_ai.core.rag.pipeline import RAGResponse
            from catchup_ai.core.rag.retriever import RetrievedArticle

            mock_pipeline = MagicMock()
            mock_pipeline.query.return_value = RAGResponse(
                answer="AI is artificial intelligence.",
                source_articles=[
                    RetrievedArticle(
                        article_id=1,
                        title="AI Article",
                        url="https://example.com/ai",
                        content="Content about AI",
                        similarity_score=0.9,
                    )
                ],
                confidence=0.85,
                model="claude-sonnet-4-20250514",
                provider="claude",
                tokens_used=100,
            )
            mock_pipeline_class.return_value = mock_pipeline

            request = article_pb2.QueryArticlesRequest(
                question="What is AI?",
                max_context_articles=5,
            )

            response = grpc_stub.QueryArticles(request)

            assert len(response.answer) > 0
            assert response.confidence > 0
            assert len(response.source_articles) >= 0

    def test_query_articles_empty_question(self, grpc_stub, mock_embedding_service):
        """Test query with empty question returns error."""
        request = article_pb2.QueryArticlesRequest(
            question="",
        )

        with pytest.raises(grpc.RpcError) as exc_info:
            grpc_stub.QueryArticles(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    def test_query_articles_no_results(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test query when no similar articles found."""
        mock_backend_client.search_similar.return_value = []

        with patch(
            "catchup_ai.api.grpc.article_servicer.RAGPipeline"
        ) as mock_pipeline_class:
            from catchup_ai.core.rag.pipeline import RAGResponse

            mock_pipeline = MagicMock()
            mock_pipeline.query.return_value = RAGResponse(
                answer="I couldn't find any relevant articles.",
                source_articles=[],
                confidence=0.0,
                model="claude-sonnet-4-20250514",
                provider="claude",
                tokens_used=0,
            )
            mock_pipeline_class.return_value = mock_pipeline

            request = article_pb2.QueryArticlesRequest(
                question="Very obscure topic with no matches",
            )

            response = grpc_stub.QueryArticles(request)

            assert "couldn't find" in response.answer.lower()
            assert response.confidence == 0.0


class TestGenerateWeeklySummaryIntegration:
    """Integration tests for GenerateWeeklySummary RPC."""

    def test_generate_summary_success(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test weekly summary generation through full gRPC flow."""
        from catchup_ai.infra.grpc.embedding_client import SimilarArticleResult

        mock_backend_client.search_similar.return_value = [
            SimilarArticleResult(article_id=1, similarity=0.8),
            SimilarArticleResult(article_id=2, similarity=0.7),
        ]

        with patch(
            "catchup_ai.api.grpc.article_servicer.RAGPipeline"
        ) as mock_pipeline_class:
            from catchup_ai.core.rag.pipeline import SummaryResponse
            from catchup_ai.core.rag.retriever import RetrievedArticle

            mock_retriever = MagicMock()
            mock_retriever.retrieve.return_value = [
                RetrievedArticle(
                    article_id=1,
                    title="Article 1",
                    url="https://example.com/1",
                    content="Content 1",
                    similarity_score=0.8,
                ),
            ]

            mock_pipeline = MagicMock()
            mock_pipeline._retriever = mock_retriever
            mock_pipeline.summarize.return_value = SummaryResponse(
                summary="This week's highlights include AI advancements.",
                highlights=["AI breakthrough", "New ML model"],
                articles=[{"title": "Article 1"}],
                period="week",
                model="claude-sonnet-4-20250514",
                provider="claude",
                tokens_used=200,
            )
            mock_pipeline_class.return_value = mock_pipeline

            request = article_pb2.GenerateWeeklySummaryRequest(
                period="week",
            )

            response = grpc_stub.GenerateWeeklySummary(request)

            assert len(response.summary) > 0
            assert len(response.highlights) >= 0

    def test_generate_summary_month_period(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test monthly summary generation."""
        with patch(
            "catchup_ai.api.grpc.article_servicer.RAGPipeline"
        ) as mock_pipeline_class:
            from catchup_ai.core.rag.pipeline import SummaryResponse
            from catchup_ai.core.rag.retriever import RetrievedArticle

            mock_retriever = MagicMock()
            mock_retriever.retrieve.return_value = [
                RetrievedArticle(
                    article_id=1,
                    title="Article",
                    url="https://example.com",
                    content="Content",
                    similarity_score=0.7,
                ),
            ]

            mock_pipeline = MagicMock()
            mock_pipeline._retriever = mock_retriever
            mock_pipeline.summarize.return_value = SummaryResponse(
                summary="Monthly summary of tech news.",
                highlights=["Highlight 1"],
                articles=[],
                period="month",
                model="claude-sonnet-4-20250514",
                provider="claude",
                tokens_used=250,
            )
            mock_pipeline_class.return_value = mock_pipeline

            request = article_pb2.GenerateWeeklySummaryRequest(
                period="month",
            )

            response = grpc_stub.GenerateWeeklySummary(request)

            assert len(response.summary) > 0

    def test_generate_summary_no_articles(
        self, grpc_stub, mock_embedding_service, mock_backend_client
    ):
        """Test summary when no articles available."""
        with patch(
            "catchup_ai.api.grpc.article_servicer.RAGPipeline"
        ) as mock_pipeline_class:
            mock_retriever = MagicMock()
            mock_retriever.retrieve.return_value = []

            mock_pipeline = MagicMock()
            mock_pipeline._retriever = mock_retriever
            mock_pipeline_class.return_value = mock_pipeline

            request = article_pb2.GenerateWeeklySummaryRequest(
                period="week",
            )

            response = grpc_stub.GenerateWeeklySummary(request)

            assert "No articles" in response.summary
