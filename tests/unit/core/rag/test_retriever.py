"""Tests for article retriever."""

from unittest.mock import MagicMock, patch

import pytest

from catchup_ai.core.rag.retriever import (
    ArticleRetriever,
    RetrievalError,
    RetrievedArticle,
)
from catchup_ai.infra.grpc.embedding_client import SimilarArticleResult


class TestRetrievedArticle:
    """Tests for RetrievedArticle dataclass."""

    def test_create_article(self):
        """Test creating retrieved article."""
        article = RetrievedArticle(
            article_id=1,
            title="Test Article",
            url="https://example.com",
            content="Article content",
            similarity_score=0.85,
        )
        assert article.article_id == 1
        assert article.title == "Test Article"
        assert article.similarity_score == 0.85

    def test_from_similar_result(self):
        """Test creating from SimilarArticleResult."""
        result = SimilarArticleResult(article_id=1, similarity=0.9)
        article = RetrievedArticle.from_similar_result(
            result,
            title="Title",
            url="https://example.com",
            content="Content",
        )
        assert article.article_id == 1
        assert article.similarity_score == 0.9
        assert article.title == "Title"


class TestArticleRetriever:
    """Tests for ArticleRetriever."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = MagicMock()
        embedding_result = MagicMock()
        embedding_result.vector = [0.1] * 1536
        service.embed_text.return_value = embedding_result
        return service

    @pytest.fixture
    def mock_embedding_client(self):
        """Create mock embedding client."""
        client = MagicMock()
        return client

    def test_init_defaults(self, mock_embedding_service, mock_embedding_client):
        """Test default initialization."""
        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )
        assert retriever._embedding_service == mock_embedding_service
        assert retriever._embedding_client == mock_embedding_client

    def test_retrieve_success(self, mock_embedding_service, mock_embedding_client):
        """Test successful retrieval."""
        mock_embedding_client.search_similar.return_value = [
            SimilarArticleResult(article_id=1, similarity=0.9),
            SimilarArticleResult(article_id=2, similarity=0.8),
        ]

        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )
        articles = retriever.retrieve("What is AI?", limit=5, min_similarity=0.5)

        assert len(articles) == 2
        assert articles[0].article_id == 1
        assert articles[0].similarity_score == 0.9
        mock_embedding_service.embed_text.assert_called_once_with("What is AI?")
        mock_embedding_client.search_similar.assert_called_once()

    def test_retrieve_filters_by_similarity(
        self, mock_embedding_service, mock_embedding_client
    ):
        """Test filtering by minimum similarity."""
        mock_embedding_client.search_similar.return_value = [
            SimilarArticleResult(article_id=1, similarity=0.9),
            SimilarArticleResult(article_id=2, similarity=0.4),  # Below threshold
        ]

        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )
        articles = retriever.retrieve("Query", limit=5, min_similarity=0.5)

        assert len(articles) == 1
        assert articles[0].article_id == 1

    def test_retrieve_empty_results(
        self, mock_embedding_service, mock_embedding_client
    ):
        """Test retrieval with no results."""
        mock_embedding_client.search_similar.return_value = []

        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )
        articles = retriever.retrieve("Query")

        assert len(articles) == 0

    def test_retrieve_embedding_error(
        self, mock_embedding_service, mock_embedding_client
    ):
        """Test error during embedding."""
        mock_embedding_service.embed_text.side_effect = Exception("Embedding failed")

        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )

        with pytest.raises(RetrievalError) as exc_info:
            retriever.retrieve("Query")
        assert "Failed to embed query" in str(exc_info.value)

    def test_retrieve_search_error(
        self, mock_embedding_service, mock_embedding_client
    ):
        """Test error during search."""
        mock_embedding_client.search_similar.side_effect = Exception("Search failed")

        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )

        with pytest.raises(RetrievalError) as exc_info:
            retriever.retrieve("Query")
        assert "Failed to search" in str(exc_info.value)

    def test_retrieve_by_article_id_not_implemented(
        self, mock_embedding_service, mock_embedding_client
    ):
        """Test retrieve by article ID is not implemented."""
        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )

        with pytest.raises(NotImplementedError):
            retriever.retrieve_by_article_id(1)

    def test_close(self, mock_embedding_service, mock_embedding_client):
        """Test close method."""
        retriever = ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        )
        retriever.close()
        mock_embedding_client.close.assert_called_once()

    def test_context_manager(self, mock_embedding_service, mock_embedding_client):
        """Test context manager usage."""
        with ArticleRetriever(
            embedding_service=mock_embedding_service,
            embedding_client=mock_embedding_client,
        ) as retriever:
            pass
        mock_embedding_client.close.assert_called_once()
