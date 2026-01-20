"""Embedding module for catchup-ai.

Provides text embedding generation and vector search functionality.
"""

from .openai_adapter import OpenAIEmbeddingAdapter
from .repository import ArticleVectorRepository, SimilarArticleResult
from .service import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingResult,
    EmbeddingService,
    RateLimitError,
    TokenLimitError,
)

__all__ = [
    # Service interface
    "EmbeddingService",
    "EmbeddingResult",
    "ArticleEmbeddingInput",
    # Implementations
    "OpenAIEmbeddingAdapter",
    # Repository
    "ArticleVectorRepository",
    "SimilarArticleResult",
    # Exceptions
    "EmbeddingError",
    "RateLimitError",
    "TokenLimitError",
]
