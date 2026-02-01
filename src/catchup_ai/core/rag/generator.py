"""LLM-based text generation for RAG responses.

Supports Claude (Anthropic) and OpenAI models for generating
answers based on retrieved context.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import structlog

from catchup_ai.infra.config.settings import get_settings

from .prompt_templates import ArticleContext, PromptTemplates

logger = structlog.get_logger()


class LLMProvider(Enum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    OPENAI = "openai"


@dataclass
class GenerationResult:
    """Result from LLM generation."""

    answer: str
    model: str
    provider: str
    tokens_used: int
    confidence: float = 0.0


class LLMGenerator(ABC):
    """Abstract base class for LLM generators."""

    @abstractmethod
    def generate(
        self,
        question: str,
        context: list[ArticleContext],
        max_tokens: int = 2000,
    ) -> GenerationResult:
        """Generate an answer based on context.

        Args:
            question: User's question
            context: Retrieved articles as context
            max_tokens: Maximum tokens in response

        Returns:
            GenerationResult with the answer
        """
        pass

    @abstractmethod
    def summarize(
        self,
        articles: list[dict],
        period: str = "week",
        max_tokens: int = 2000,
    ) -> GenerationResult:
        """Generate a summary of articles.

        Args:
            articles: List of articles to summarize
            period: Time period (week, month)
            max_tokens: Maximum tokens in response

        Returns:
            GenerationResult with the summary
        """
        pass


class ClaudeGenerator(LLMGenerator):
    """LLM generator using Claude (Anthropic) API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize Claude generator.

        Args:
            api_key: Anthropic API key. If None, uses settings.
            model: Claude model to use
        """
        settings = get_settings()
        self._api_key = api_key or settings.anthropic.api_key
        self._model = model
        self._logger = logger.bind(component="claude_generator", model=model)

        if not self._api_key:
            raise GenerationError(
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY in .env or pass api_key parameter."
            )

        # Lazy import
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        except ImportError:
            raise GenerationError(
                "anthropic is required. Install with: uv add anthropic"
            )

    def generate(
        self,
        question: str,
        context: list[ArticleContext],
        max_tokens: int = 2000,
    ) -> GenerationResult:
        """Generate answer using Claude."""
        self._logger.info(
            "Generating answer",
            question=question[:50],
            context_count=len(context),
        )

        system_prompt = PromptTemplates.rag_system_prompt()
        user_prompt = PromptTemplates.rag_user_prompt(question, context)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            answer = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            self._logger.info(
                "Answer generated",
                tokens_used=tokens_used,
                answer_length=len(answer),
            )

            return GenerationResult(
                answer=answer,
                model=self._model,
                provider="claude",
                tokens_used=tokens_used,
            )

        except Exception as e:
            self._logger.error("Generation failed", error=str(e))
            raise GenerationError(f"Claude generation failed: {e}") from e

    def summarize(
        self,
        articles: list[dict],
        period: str = "week",
        max_tokens: int = 2000,
    ) -> GenerationResult:
        """Generate summary using Claude."""
        self._logger.info(
            "Generating summary",
            article_count=len(articles),
            period=period,
        )

        system_prompt = PromptTemplates.summary_system_prompt()
        user_prompt = PromptTemplates.weekly_summary_prompt(articles, period)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            summary = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            self._logger.info(
                "Summary generated",
                tokens_used=tokens_used,
                summary_length=len(summary),
            )

            return GenerationResult(
                answer=summary,
                model=self._model,
                provider="claude",
                tokens_used=tokens_used,
            )

        except Exception as e:
            self._logger.error("Summarization failed", error=str(e))
            raise GenerationError(f"Claude summarization failed: {e}") from e


class OpenAIGenerator(LLMGenerator):
    """LLM generator using OpenAI API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ):
        """Initialize OpenAI generator.

        Args:
            api_key: OpenAI API key. If None, uses settings.
            model: OpenAI model to use
        """
        settings = get_settings()
        self._api_key = api_key or settings.openai.api_key
        self._model = model
        self._logger = logger.bind(component="openai_generator", model=model)

        if not self._api_key:
            raise GenerationError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY in .env or pass api_key parameter."
            )

        # Lazy import
        try:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        except ImportError:
            raise GenerationError(
                "openai is required. Install with: uv add openai"
            )

    def generate(
        self,
        question: str,
        context: list[ArticleContext],
        max_tokens: int = 2000,
    ) -> GenerationResult:
        """Generate answer using OpenAI."""
        self._logger.info(
            "Generating answer",
            question=question[:50],
            context_count=len(context),
        )

        system_prompt = PromptTemplates.rag_system_prompt()
        user_prompt = PromptTemplates.rag_user_prompt(question, context)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            answer = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0

            self._logger.info(
                "Answer generated",
                tokens_used=tokens_used,
                answer_length=len(answer) if answer else 0,
            )

            return GenerationResult(
                answer=answer or "",
                model=self._model,
                provider="openai",
                tokens_used=tokens_used,
            )

        except Exception as e:
            self._logger.error("Generation failed", error=str(e))
            raise GenerationError(f"OpenAI generation failed: {e}") from e

    def summarize(
        self,
        articles: list[dict],
        period: str = "week",
        max_tokens: int = 2000,
    ) -> GenerationResult:
        """Generate summary using OpenAI."""
        self._logger.info(
            "Generating summary",
            article_count=len(articles),
            period=period,
        )

        system_prompt = PromptTemplates.summary_system_prompt()
        user_prompt = PromptTemplates.weekly_summary_prompt(articles, period)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            summary = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0

            self._logger.info(
                "Summary generated",
                tokens_used=tokens_used,
                summary_length=len(summary) if summary else 0,
            )

            return GenerationResult(
                answer=summary or "",
                model=self._model,
                provider="openai",
                tokens_used=tokens_used,
            )

        except Exception as e:
            self._logger.error("Summarization failed", error=str(e))
            raise GenerationError(f"OpenAI summarization failed: {e}") from e


def create_generator(provider: LLMProvider | None = None) -> LLMGenerator:
    """Factory function to create an LLM generator.

    Args:
        provider: LLM provider to use. If None, uses settings.

    Returns:
        LLMGenerator instance
    """
    settings = get_settings()

    if provider is None:
        # Default to Claude if available, otherwise OpenAI
        if settings.anthropic.api_key:
            provider = LLMProvider.CLAUDE
        elif settings.openai.api_key:
            provider = LLMProvider.OPENAI
        else:
            raise GenerationError(
                "No LLM API key configured. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env"
            )

    if provider == LLMProvider.CLAUDE:
        return ClaudeGenerator()
    elif provider == LLMProvider.OPENAI:
        return OpenAIGenerator()
    else:
        raise GenerationError(f"Unknown provider: {provider}")


class GenerationError(Exception):
    """Error during text generation."""

    pass
