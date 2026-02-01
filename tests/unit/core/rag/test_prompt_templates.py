"""Tests for RAG prompt templates."""

import pytest

from catchup_ai.core.rag.prompt_templates import ArticleContext, PromptTemplates


class TestArticleContext:
    """Tests for ArticleContext dataclass."""

    def test_create_context(self):
        """Test creating article context."""
        context = ArticleContext(
            article_id=1,
            title="Test Article",
            url="https://example.com/article",
            content="This is the article content.",
            relevance_score=0.85,
        )
        assert context.article_id == 1
        assert context.title == "Test Article"
        assert context.url == "https://example.com/article"
        assert context.content == "This is the article content."
        assert context.relevance_score == 0.85


class TestPromptTemplates:
    """Tests for PromptTemplates methods."""

    def test_rag_system_prompt(self):
        """Test RAG system prompt generation."""
        prompt = PromptTemplates.rag_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain key instructions
        assert "article" in prompt.lower() or "context" in prompt.lower()

    def test_rag_user_prompt_with_context(self):
        """Test RAG user prompt with context articles."""
        context = [
            ArticleContext(
                article_id=1,
                title="AI Article",
                url="https://example.com/ai",
                content="AI is transforming industries.",
                relevance_score=0.9,
            ),
            ArticleContext(
                article_id=2,
                title="ML Article",
                url="https://example.com/ml",
                content="Machine learning is a subset of AI.",
                relevance_score=0.8,
            ),
        ]
        prompt = PromptTemplates.rag_user_prompt("What is AI?", context)
        assert isinstance(prompt, str)
        assert "What is AI?" in prompt
        assert "AI Article" in prompt
        assert "ML Article" in prompt

    def test_rag_user_prompt_empty_context(self):
        """Test RAG user prompt with empty context."""
        prompt = PromptTemplates.rag_user_prompt("What is AI?", [])
        assert isinstance(prompt, str)
        assert "What is AI?" in prompt

    def test_summary_system_prompt(self):
        """Test summary system prompt generation."""
        prompt = PromptTemplates.summary_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_weekly_summary_prompt(self):
        """Test weekly summary prompt generation."""
        articles = [
            {"title": "Article 1", "url": "https://example.com/1", "content": "Content 1", "category": "Tech"},
            {"title": "Article 2", "url": "https://example.com/2", "content": "Content 2", "category": "AI"},
        ]
        prompt = PromptTemplates.weekly_summary_prompt(articles, "week")
        assert isinstance(prompt, str)
        assert "Article 1" in prompt
        assert "Article 2" in prompt

    def test_weekly_summary_prompt_month_period(self):
        """Test summary prompt with month period."""
        articles = [{"title": "Article", "url": "https://example.com", "content": "Content"}]
        prompt = PromptTemplates.weekly_summary_prompt(articles, "month")
        assert isinstance(prompt, str)
        assert "month" in prompt.lower()
