"""RAG Pipeline for article-based question answering.

Combines retrieval, context building, and generation into a
complete RAG workflow.
"""

from dataclasses import dataclass

import structlog

from .chunker import TextChunker
from .generator import LLMGenerator, create_generator
from .prompt_templates import ArticleContext
from .retriever import ArticleRetriever, RetrievedArticle

logger = structlog.get_logger()


@dataclass
class RAGResponse:
    """Complete RAG response with answer and sources."""

    answer: str
    source_articles: list[RetrievedArticle]
    confidence: float
    model: str
    provider: str
    tokens_used: int


@dataclass
class SummaryResponse:
    """Summary response with highlights."""

    summary: str
    highlights: list[str]
    articles: list[dict]
    period: str
    model: str
    provider: str
    tokens_used: int


@dataclass
class RAGConfig:
    """Configuration for RAG pipeline."""

    max_context_articles: int = 5
    min_similarity: float = 0.5
    max_context_tokens: int = 4000
    max_response_tokens: int = 2000
    chunk_size: int = 1000


class RAGPipeline:
    """Complete RAG pipeline for article Q&A.

    Flow:
    1. User asks a question
    2. Retriever finds relevant articles
    3. Context is built from retrieved articles
    4. Generator produces an answer based on context
    """

    def __init__(
        self,
        retriever: ArticleRetriever | None = None,
        generator: LLMGenerator | None = None,
        config: RAGConfig | None = None,
    ):
        """Initialize the RAG pipeline.

        Args:
            retriever: Article retriever. If None, creates default.
            generator: LLM generator. If None, creates default.
            config: Pipeline configuration. If None, uses defaults.
        """
        self._retriever = retriever or ArticleRetriever()
        self._generator = generator or create_generator()
        self._config = config or RAGConfig()
        self._chunker = TextChunker(chunk_size=self._config.chunk_size)
        self._logger = logger.bind(component="rag_pipeline")

    def query(
        self,
        question: str,
        max_articles: int | None = None,
    ) -> RAGResponse:
        """Answer a question using RAG.

        Args:
            question: User's question
            max_articles: Override max context articles

        Returns:
            RAGResponse with answer and sources
        """
        max_articles = max_articles or self._config.max_context_articles

        self._logger.info(
            "Processing RAG query",
            question=question[:100],
            max_articles=max_articles,
        )

        # 1. Retrieve relevant articles
        articles = self._retriever.retrieve(
            query=question,
            limit=max_articles,
            min_similarity=self._config.min_similarity,
        )

        if not articles:
            self._logger.warning("No relevant articles found")
            return RAGResponse(
                answer="I couldn't find any relevant articles to answer your question. "
                "Please try rephrasing or asking about a different topic.",
                source_articles=[],
                confidence=0.0,
                model=self._generator._model if hasattr(self._generator, "_model") else "unknown",
                provider=self._generator.__class__.__name__.replace("Generator", "").lower(),
                tokens_used=0,
            )

        # 2. Build context from articles
        context = self._build_context(articles)

        # 3. Generate answer
        result = self._generator.generate(
            question=question,
            context=context,
            max_tokens=self._config.max_response_tokens,
        )

        # 4. Calculate confidence based on similarity scores
        avg_similarity = sum(a.similarity_score for a in articles) / len(articles)
        confidence = min(avg_similarity * 1.2, 1.0)  # Slight boost, cap at 1.0

        self._logger.info(
            "RAG query completed",
            articles_used=len(articles),
            tokens_used=result.tokens_used,
            confidence=confidence,
        )

        return RAGResponse(
            answer=result.answer,
            source_articles=articles,
            confidence=confidence,
            model=result.model,
            provider=result.provider,
            tokens_used=result.tokens_used,
        )

    def summarize(
        self,
        articles: list[dict],
        period: str = "week",
    ) -> SummaryResponse:
        """Generate a summary of articles.

        Args:
            articles: List of articles with title, url, content, category
            period: Time period (week, month)

        Returns:
            SummaryResponse with summary and highlights
        """
        self._logger.info(
            "Generating summary",
            article_count=len(articles),
            period=period,
        )

        if not articles:
            return SummaryResponse(
                summary="No articles to summarize for this period.",
                highlights=[],
                articles=[],
                period=period,
                model="",
                provider="",
                tokens_used=0,
            )

        # Generate summary
        result = self._generator.summarize(
            articles=articles,
            period=period,
            max_tokens=self._config.max_response_tokens,
        )

        # Extract highlights from summary (simple heuristic)
        highlights = self._extract_highlights(result.answer)

        self._logger.info(
            "Summary completed",
            highlights_count=len(highlights),
            tokens_used=result.tokens_used,
        )

        return SummaryResponse(
            summary=result.answer,
            highlights=highlights,
            articles=articles,
            period=period,
            model=result.model,
            provider=result.provider,
            tokens_used=result.tokens_used,
        )

    def _build_context(
        self,
        articles: list[RetrievedArticle],
    ) -> list[ArticleContext]:
        """Build context from retrieved articles.

        Args:
            articles: Retrieved articles

        Returns:
            List of ArticleContext for the generator
        """
        context = []
        total_tokens = 0
        max_tokens = self._config.max_context_tokens

        for article in articles:
            # Estimate tokens for this article
            content = article.content or f"[Article ID: {article.article_id}]"
            article_tokens = self._chunker.estimate_tokens(content)

            # Check if we have room
            if total_tokens + article_tokens > max_tokens:
                # Truncate content to fit
                remaining_tokens = max_tokens - total_tokens
                if remaining_tokens > 100:
                    # Truncate to fit
                    char_limit = remaining_tokens * 4
                    content = content[:char_limit] + "..."
                else:
                    break

            context.append(
                ArticleContext(
                    article_id=article.article_id,
                    title=article.title or f"Article {article.article_id}",
                    url=article.url or "",
                    content=content,
                    relevance_score=article.similarity_score,
                )
            )

            total_tokens += self._chunker.estimate_tokens(content)

        return context

    def _extract_highlights(self, summary: str) -> list[str]:
        """Extract key highlights from summary text.

        Simple heuristic: look for bullet points or numbered items.

        Args:
            summary: Generated summary text

        Returns:
            List of highlight strings
        """
        import re

        highlights = []

        # Look for bullet points (-, *, •)
        bullet_pattern = r"^[\-\*•]\s+(.+)$"
        for line in summary.split("\n"):
            match = re.match(bullet_pattern, line.strip())
            if match:
                highlights.append(match.group(1).strip())

        # Look for numbered items
        number_pattern = r"^\d+[\.\)]\s+(.+)$"
        for line in summary.split("\n"):
            match = re.match(number_pattern, line.strip())
            if match:
                highlights.append(match.group(1).strip())

        # Remove duplicates while preserving order
        seen = set()
        unique_highlights = []
        for h in highlights:
            if h not in seen:
                seen.add(h)
                unique_highlights.append(h)

        return unique_highlights[:10]  # Limit to 10 highlights

    def close(self):
        """Close resources."""
        self._retriever.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
