"""Embedding service interface.

Defines the contract for embedding providers (OpenAI, local models, etc.).
Uses Protocol for structural subtyping (duck typing with type hints).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingResult:
    """Result of an embedding operation.

    Attributes:
        vector: The embedding vector
        model: The model used to generate the embedding
        tokens_used: Number of tokens processed
    """

    vector: list[float]
    model: str
    tokens_used: int

    @property
    def dimension(self) -> int:
        """Get the dimension of the embedding vector."""
        return len(self.vector)


@dataclass(frozen=True)
class ArticleEmbeddingInput:
    """Input for embedding an article.

    Combines title and content for richer semantic representation.
    """

    article_id: int
    title: str
    content: str
    url: str | None = None

    def to_text(self, max_length: int = 8000) -> str:
        """Convert to text for embedding.

        Combines title and content, prioritizing title.
        Truncates to max_length to stay within model limits.
        """
        # Title is more important for semantic meaning
        combined = f"Title: {self.title}\n\nContent: {self.content}"

        if len(combined) > max_length:
            # Keep full title, truncate content
            title_part = f"Title: {self.title}\n\nContent: "
            remaining = max_length - len(title_part)
            combined = title_part + self.content[:remaining] + "..."

        return combined


class EmbeddingService(ABC):
    """Abstract base class for embedding services.

    Implementations should handle:
    - API rate limiting
    - Retry logic
    - Token counting
    """

    @abstractmethod
    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with the vector and metadata

        Raises:
            EmbeddingError: If embedding fails
        """
        pass

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts (batch).

        More efficient than calling embed_text multiple times.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResults in the same order

        Raises:
            EmbeddingError: If embedding fails
        """
        pass

    def embed_article(self, article: ArticleEmbeddingInput) -> EmbeddingResult:
        """Generate embedding for an article.

        Args:
            article: Article input with title and content

        Returns:
            EmbeddingResult with the vector
        """
        text = article.to_text()
        return self.embed_text(text)

    def embed_articles(
        self, articles: list[ArticleEmbeddingInput]
    ) -> list[EmbeddingResult]:
        """Generate embeddings for multiple articles (batch).

        Args:
            articles: List of article inputs

        Returns:
            List of EmbeddingResults in the same order
        """
        texts = [article.to_text() for article in articles]
        return self.embed_texts(texts)


class EmbeddingError(Exception):
    """Base exception for embedding errors."""

    pass


class RateLimitError(EmbeddingError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after: {retry_after}s")


class TokenLimitError(EmbeddingError):
    """Raised when text exceeds token limit."""

    def __init__(self, tokens: int, limit: int):
        self.tokens = tokens
        self.limit = limit
        super().__init__(f"Token limit exceeded: {tokens} > {limit}")
