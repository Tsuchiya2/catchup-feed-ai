"""Embedding module for catchup-ai.

Provides text embedding generation and vector search functionality.

Supported providers:
- OpenAI (text-embedding-3-small)
- Voyage AI (voyage-3) - Anthropic recommended

Usage:
    from catchup_ai.core.embedding import create_embedding_service

    # Uses provider from EMBEDDING_PROVIDER env var
    service = create_embedding_service()
    result = service.embed_text("Hello, world!")
"""

from .factory import create_embedding_service, get_embedding_service
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

# Lazy import for Voyage (to avoid httpx dependency when not used)
# from .voyage_adapter import VoyageEmbeddingAdapter

__all__ = [
    # Factory (recommended way to create services)
    "create_embedding_service",
    "get_embedding_service",
    # Service interface
    "EmbeddingService",
    "EmbeddingResult",
    "ArticleEmbeddingInput",
    # Implementations
    "OpenAIEmbeddingAdapter",
    # "VoyageEmbeddingAdapter",  # Import directly if needed
    # Repository
    "ArticleVectorRepository",
    "SimilarArticleResult",
    # Exceptions
    "EmbeddingError",
    "RateLimitError",
    "TokenLimitError",
]
