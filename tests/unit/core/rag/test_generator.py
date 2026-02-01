"""Tests for LLM generators."""

from unittest.mock import MagicMock, patch

import pytest

from catchup_ai.core.rag.generator import (
    ClaudeGenerator,
    GenerationError,
    GenerationResult,
    LLMProvider,
    OpenAIGenerator,
    create_generator,
)
from catchup_ai.core.rag.prompt_templates import ArticleContext


class TestGenerationResult:
    """Tests for GenerationResult dataclass."""

    def test_create_result(self):
        """Test creating generation result."""
        result = GenerationResult(
            answer="This is the answer.",
            model="claude-sonnet-4-20250514",
            provider="claude",
            tokens_used=100,
            confidence=0.95,
        )
        assert result.answer == "This is the answer."
        assert result.model == "claude-sonnet-4-20250514"
        assert result.provider == "claude"
        assert result.tokens_used == 100
        assert result.confidence == 0.95


class TestClaudeGenerator:
    """Tests for ClaudeGenerator."""

    def test_init_without_api_key_raises_error(self):
        """Test initialization without API key raises error."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = ""
            with pytest.raises(GenerationError) as exc_info:
                ClaudeGenerator()
            assert "API key" in str(exc_info.value)

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"
            with patch("anthropic.Anthropic"):
                generator = ClaudeGenerator()
                assert generator._model == "claude-sonnet-4-20250514"

    def test_generate_success(self):
        """Test successful generation."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Generated answer")]
            mock_response.usage.input_tokens = 50
            mock_response.usage.output_tokens = 30

            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                generator = ClaudeGenerator()
                context = [
                    ArticleContext(
                        article_id=1,
                        title="Test",
                        url="https://example.com",
                        content="Content",
                        relevance_score=0.9,
                    )
                ]
                result = generator.generate("What is AI?", context)

                assert result.answer == "Generated answer"
                assert result.provider == "claude"
                assert result.tokens_used == 80

    def test_generate_error(self):
        """Test generation error handling."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"

            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = Exception("API error")
                mock_anthropic.return_value = mock_client

                generator = ClaudeGenerator()
                with pytest.raises(GenerationError) as exc_info:
                    generator.generate("Question", [])
                assert "API error" in str(exc_info.value)

    def test_summarize_success(self):
        """Test successful summarization."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Weekly summary")]
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 50

            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                generator = ClaudeGenerator()
                articles = [{"title": "Article", "url": "https://example.com", "content": "Content"}]
                result = generator.summarize(articles, "week")

                assert result.answer == "Weekly summary"
                assert result.tokens_used == 150


class TestOpenAIGenerator:
    """Tests for OpenAIGenerator."""

    def test_init_without_api_key_raises_error(self):
        """Test initialization without API key raises error."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.openai.api_key = ""
            with pytest.raises(GenerationError) as exc_info:
                OpenAIGenerator()
            assert "API key" in str(exc_info.value)

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.openai.api_key = "sk-test-key"
            with patch("openai.OpenAI"):
                generator = OpenAIGenerator()
                assert generator._model == "gpt-4o-mini"

    def test_generate_success(self):
        """Test successful generation."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.openai.api_key = "sk-test-key"

            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Generated answer"))]
            mock_response.usage.total_tokens = 80

            with patch("openai.OpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                generator = OpenAIGenerator()
                result = generator.generate("What is AI?", [])

                assert result.answer == "Generated answer"
                assert result.provider == "openai"
                assert result.tokens_used == 80


class TestCreateGenerator:
    """Tests for create_generator factory function."""

    def test_create_claude_generator(self):
        """Test creating Claude generator."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"
            with patch("anthropic.Anthropic"):
                generator = create_generator(LLMProvider.CLAUDE)
                assert isinstance(generator, ClaudeGenerator)

    def test_create_openai_generator(self):
        """Test creating OpenAI generator."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.openai.api_key = "sk-test-key"
            with patch("openai.OpenAI"):
                generator = create_generator(LLMProvider.OPENAI)
                assert isinstance(generator, OpenAIGenerator)

    def test_create_default_claude(self):
        """Test default to Claude when available."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"
            mock_settings.return_value.openai.api_key = ""
            with patch("anthropic.Anthropic"):
                generator = create_generator()
                assert isinstance(generator, ClaudeGenerator)

    def test_create_default_openai_fallback(self):
        """Test fallback to OpenAI when Claude not available."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = ""
            mock_settings.return_value.openai.api_key = "sk-test-key"
            with patch("openai.OpenAI"):
                generator = create_generator()
                assert isinstance(generator, OpenAIGenerator)

    def test_create_no_api_keys_raises_error(self):
        """Test error when no API keys configured."""
        with patch("catchup_ai.core.rag.generator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic.api_key = ""
            mock_settings.return_value.openai.api_key = ""
            with pytest.raises(GenerationError) as exc_info:
                create_generator()
            assert "No LLM API key" in str(exc_info.value)
