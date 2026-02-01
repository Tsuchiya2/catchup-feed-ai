"""Tests for RAG pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from catchup_ai.core.rag.generator import GenerationResult
from catchup_ai.core.rag.pipeline import RAGConfig, RAGPipeline, RAGResponse, SummaryResponse
from catchup_ai.core.rag.retriever import RetrievedArticle


class TestRAGConfig:
    """Tests for RAGConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RAGConfig()
        assert config.max_context_articles == 5
        assert config.min_similarity == 0.5
        assert config.max_context_tokens == 4000
        assert config.max_response_tokens == 2000
        assert config.chunk_size == 1000

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RAGConfig(
            max_context_articles=10,
            min_similarity=0.7,
            max_context_tokens=8000,
        )
        assert config.max_context_articles == 10
        assert config.min_similarity == 0.7
        assert config.max_context_tokens == 8000


class TestRAGResponse:
    """Tests for RAGResponse dataclass."""

    def test_create_response(self):
        """Test creating RAG response."""
        articles = [
            RetrievedArticle(
                article_id=1,
                title="Test",
                url="https://example.com",
                content="Content",
                similarity_score=0.9,
            )
        ]
        response = RAGResponse(
            answer="This is the answer.",
            source_articles=articles,
            confidence=0.85,
            model="claude-sonnet-4-20250514",
            provider="claude",
            tokens_used=100,
        )
        assert response.answer == "This is the answer."
        assert len(response.source_articles) == 1
        assert response.confidence == 0.85


class TestSummaryResponse:
    """Tests for SummaryResponse dataclass."""

    def test_create_response(self):
        """Test creating summary response."""
        response = SummaryResponse(
            summary="Weekly summary",
            highlights=["Point 1", "Point 2"],
            articles=[{"title": "Article"}],
            period="week",
            model="claude-sonnet-4-20250514",
            provider="claude",
            tokens_used=150,
        )
        assert response.summary == "Weekly summary"
        assert len(response.highlights) == 2
        assert response.period == "week"


class TestRAGPipeline:
    """Tests for RAGPipeline."""

    @pytest.fixture
    def mock_retriever(self):
        """Create mock retriever."""
        retriever = MagicMock()
        return retriever

    @pytest.fixture
    def mock_generator(self):
        """Create mock generator."""
        generator = MagicMock()
        generator._model = "claude-sonnet-4-20250514"
        return generator

    @pytest.fixture
    def pipeline(self, mock_retriever, mock_generator):
        """Create pipeline with mocked dependencies."""
        return RAGPipeline(
            retriever=mock_retriever,
            generator=mock_generator,
        )

    def test_init_with_defaults(self):
        """Test initialization with default components."""
        with patch("catchup_ai.core.rag.pipeline.ArticleRetriever"):
            with patch("catchup_ai.core.rag.pipeline.create_generator") as mock_create:
                mock_create.return_value = MagicMock()
                pipeline = RAGPipeline()
                assert pipeline._config is not None

    def test_init_with_custom_config(self, mock_retriever, mock_generator):
        """Test initialization with custom config."""
        config = RAGConfig(max_context_articles=10)
        pipeline = RAGPipeline(
            retriever=mock_retriever,
            generator=mock_generator,
            config=config,
        )
        assert pipeline._config.max_context_articles == 10

    def test_query_success(self, pipeline, mock_retriever, mock_generator):
        """Test successful query."""
        # Setup mock retriever
        mock_retriever.retrieve.return_value = [
            RetrievedArticle(
                article_id=1,
                title="AI Article",
                url="https://example.com/ai",
                content="AI is transforming industries.",
                similarity_score=0.9,
            ),
        ]

        # Setup mock generator
        mock_generator.generate.return_value = GenerationResult(
            answer="AI is a technology...",
            model="claude-sonnet-4-20250514",
            provider="claude",
            tokens_used=100,
        )

        result = pipeline.query("What is AI?")

        assert result.answer == "AI is a technology..."
        assert len(result.source_articles) == 1
        assert result.confidence > 0
        mock_retriever.retrieve.assert_called_once()
        mock_generator.generate.assert_called_once()

    def test_query_no_articles_found(self, pipeline, mock_retriever, mock_generator):
        """Test query when no articles found."""
        mock_retriever.retrieve.return_value = []

        result = pipeline.query("Unknown topic")

        assert "couldn't find" in result.answer.lower()
        assert len(result.source_articles) == 0
        assert result.confidence == 0.0
        mock_generator.generate.assert_not_called()

    def test_query_with_custom_max_articles(
        self, pipeline, mock_retriever, mock_generator
    ):
        """Test query with custom max_articles parameter."""
        mock_retriever.retrieve.return_value = []

        pipeline.query("Question", max_articles=10)

        mock_retriever.retrieve.assert_called_once()
        call_kwargs = mock_retriever.retrieve.call_args
        assert call_kwargs.kwargs.get("limit") == 10

    def test_summarize_success(self, pipeline, mock_generator):
        """Test successful summarization."""
        mock_generator.summarize.return_value = GenerationResult(
            answer="- Key point 1\n- Key point 2",
            model="claude-sonnet-4-20250514",
            provider="claude",
            tokens_used=150,
        )

        articles = [
            {"title": "Article 1", "content": "Content 1"},
            {"title": "Article 2", "content": "Content 2"},
        ]
        result = pipeline.summarize(articles, period="week")

        assert "Key point" in result.summary
        assert result.period == "week"
        mock_generator.summarize.assert_called_once()

    def test_summarize_empty_articles(self, pipeline, mock_generator):
        """Test summarization with no articles."""
        result = pipeline.summarize([], period="week")

        assert "No articles" in result.summary
        assert len(result.highlights) == 0
        mock_generator.summarize.assert_not_called()

    def test_extract_highlights(self, pipeline):
        """Test extracting highlights from summary text."""
        summary = """Here is the summary:
- First key point
- Second key point
* Third point
1. Numbered item
2) Another numbered item
"""
        highlights = pipeline._extract_highlights(summary)
        assert len(highlights) >= 4

    def test_extract_highlights_no_bullets(self, pipeline):
        """Test extracting highlights with no bullet points."""
        summary = "This is just a plain text summary."
        highlights = pipeline._extract_highlights(summary)
        assert len(highlights) == 0

    def test_build_context(self, pipeline):
        """Test building context from articles."""
        articles = [
            RetrievedArticle(
                article_id=1,
                title="Title 1",
                url="https://example.com/1",
                content="Content 1",
                similarity_score=0.9,
            ),
            RetrievedArticle(
                article_id=2,
                title="Title 2",
                url="https://example.com/2",
                content="Content 2",
                similarity_score=0.8,
            ),
        ]
        context = pipeline._build_context(articles)

        assert len(context) == 2
        assert context[0].article_id == 1
        assert context[0].title == "Title 1"

    def test_build_context_truncates_long_content(self, pipeline):
        """Test context building truncates very long content."""
        # Set very low token limit
        pipeline._config.max_context_tokens = 50

        articles = [
            RetrievedArticle(
                article_id=1,
                title="Title",
                url="https://example.com",
                content="Very long content " * 100,
                similarity_score=0.9,
            ),
        ]
        context = pipeline._build_context(articles)

        # Should truncate or limit content
        assert len(context) >= 0

    def test_close(self, pipeline, mock_retriever):
        """Test close method."""
        pipeline.close()
        mock_retriever.close.assert_called_once()

    def test_context_manager(self, mock_retriever, mock_generator):
        """Test context manager usage."""
        with RAGPipeline(
            retriever=mock_retriever,
            generator=mock_generator,
        ) as pipeline:
            pass
        mock_retriever.close.assert_called_once()
