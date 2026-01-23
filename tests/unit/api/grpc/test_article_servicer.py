"""Tests for ArticleAI gRPC servicer."""

from unittest.mock import MagicMock

import pytest

from catchup_ai.api.grpc.article_servicer import ArticleAIServicer
from catchup_ai.api.grpc.generated import article_pb2
from catchup_ai.core.embedding.service import EmbeddingError, EmbeddingResult


@pytest.fixture
def mock_embedding_service():
    """Create mock embedding service."""
    service = MagicMock()
    service.embed_article.return_value = EmbeddingResult(
        vector=[0.1, 0.2, 0.3] * 512,  # 1536 dimensions
        model="text-embedding-3-small",
        provider="openai",
        tokens_used=100,
    )
    service.embed_text.return_value = EmbeddingResult(
        vector=[0.1, 0.2, 0.3] * 512,
        model="text-embedding-3-small",
        provider="openai",
        tokens_used=50,
    )
    return service


@pytest.fixture
def mock_embedding_client():
    """Create mock embedding client for backend calls."""
    client = MagicMock()
    client.search_similar.return_value = [
        MagicMock(article_id=1, similarity=0.95),
        MagicMock(article_id=2, similarity=0.85),
    ]
    return client


@pytest.fixture
def mock_context():
    """Create mock gRPC context."""
    context = MagicMock()
    return context


@pytest.fixture
def servicer(mock_embedding_service, mock_embedding_client):
    """Create servicer with mocked dependencies."""
    return ArticleAIServicer(
        embedding_service=mock_embedding_service,
        embedding_client=mock_embedding_client,
    )


class TestEmbedArticle:
    """Tests for EmbedArticle RPC method."""

    def test_embed_article_success(self, servicer, mock_embedding_service, mock_context):
        """Test successful article embedding."""
        request = article_pb2.EmbedArticleRequest(
            article_id=123,
            title="Test Article",
            content="This is test content.",
            url="https://example.com/article",
        )

        response = servicer.EmbedArticle(request, mock_context)

        assert response.article_id == 123
        assert response.success is True
        assert response.error_message == ""
        assert response.embedding_dimension == 1536
        assert len(response.embedding) == 1536
        assert response.provider == "openai"
        assert response.model == "text-embedding-3-small"
        mock_embedding_service.embed_article.assert_called_once()

    def test_embed_article_with_embedding_type(
        self, servicer, mock_embedding_service, mock_context
    ):
        """Test embedding with custom embedding_type."""
        request = article_pb2.EmbedArticleRequest(
            article_id=456,
            title="Title",
            content="Content",
            embedding_type="title",
        )

        response = servicer.EmbedArticle(request, mock_context)

        assert response.success is True
        assert response.embedding_type == "title"

    def test_embed_article_default_embedding_type(self, servicer, mock_context):
        """Test that default embedding_type is 'content'."""
        request = article_pb2.EmbedArticleRequest(
            article_id=789,
            title="Title",
            content="Content",
        )

        response = servicer.EmbedArticle(request, mock_context)

        assert response.embedding_type == "content"

    def test_embed_article_error(self, servicer, mock_embedding_service, mock_context):
        """Test error handling when embedding fails."""
        mock_embedding_service.embed_article.side_effect = EmbeddingError(
            "API error"
        )

        request = article_pb2.EmbedArticleRequest(
            article_id=123,
            title="Test",
            content="Content",
        )

        response = servicer.EmbedArticle(request, mock_context)

        assert response.article_id == 123
        assert response.success is False
        assert "API error" in response.error_message


class TestSearchSimilar:
    """Tests for SearchSimilar RPC method."""

    def test_search_similar_by_query(
        self, servicer, mock_embedding_service, mock_embedding_client, mock_context
    ):
        """Test searching by query text."""
        request = article_pb2.SearchSimilarRequest(
            query="test query",
            limit=5,
        )

        response = servicer.SearchSimilar(request, mock_context)

        assert len(response.articles) == 2
        assert response.articles[0].article_id == 1
        assert response.articles[0].similarity_score == pytest.approx(0.95)
        mock_embedding_service.embed_text.assert_called_once_with("test query")
        mock_embedding_client.search_similar.assert_called_once()

    def test_search_similar_default_limit(
        self, servicer, mock_embedding_client, mock_context
    ):
        """Test that default limit is 10."""
        request = article_pb2.SearchSimilarRequest(
            query="test",
            limit=0,  # Should use default
        )

        servicer.SearchSimilar(request, mock_context)

        call_args = mock_embedding_client.search_similar.call_args
        assert call_args.kwargs["limit"] == 10

    def test_search_similar_by_article_id_not_implemented(
        self, servicer, mock_context
    ):
        """Test that search by article_id returns UNIMPLEMENTED."""
        request = article_pb2.SearchSimilarRequest(
            article_id=123,
            limit=5,
        )

        response = servicer.SearchSimilar(request, mock_context)

        mock_context.set_code.assert_called()
        # Response should be empty
        assert len(response.articles) == 0

    def test_search_similar_no_search_criteria(self, servicer, mock_context):
        """Test error when neither query nor article_id provided."""
        request = article_pb2.SearchSimilarRequest(
            limit=5,
        )

        response = servicer.SearchSimilar(request, mock_context)

        mock_context.set_code.assert_called()
        assert len(response.articles) == 0

    def test_search_similar_embedding_error(
        self, servicer, mock_embedding_service, mock_context
    ):
        """Test error handling when embedding fails."""
        mock_embedding_service.embed_text.side_effect = EmbeddingError("API error")

        request = article_pb2.SearchSimilarRequest(
            query="test",
            limit=5,
        )

        response = servicer.SearchSimilar(request, mock_context)

        mock_context.set_code.assert_called()
        assert len(response.articles) == 0


class TestUnimplementedMethods:
    """Tests for placeholder RPC methods."""

    def test_query_articles_not_implemented(self, servicer, mock_context):
        """Test that QueryArticles returns UNIMPLEMENTED."""
        request = article_pb2.QueryArticlesRequest(
            question="What is AI?",
        )

        servicer.QueryArticles(request, mock_context)

        mock_context.set_code.assert_called()
        mock_context.set_details.assert_called()

    def test_generate_weekly_summary_not_implemented(self, servicer, mock_context):
        """Test that GenerateWeeklySummary returns UNIMPLEMENTED."""
        request = article_pb2.GenerateWeeklySummaryRequest()

        servicer.GenerateWeeklySummary(request, mock_context)

        mock_context.set_code.assert_called()
        mock_context.set_details.assert_called()

    def test_classify_article_not_implemented(self, servicer, mock_context):
        """Test that ClassifyArticle returns UNIMPLEMENTED."""
        request = article_pb2.ClassifyArticleRequest(
            article_id=1,
            title="Test",
            content="Content",
        )

        servicer.ClassifyArticle(request, mock_context)

        mock_context.set_code.assert_called()
        mock_context.set_details.assert_called()
