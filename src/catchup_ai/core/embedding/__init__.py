"""Embedding module for catchup-ai.

Provides text embedding generation functionality.

Architecture note:
    catchup-ai generates embeddings, but does NOT store them.
    Storage and similarity search are delegated to catchup-feed-backend
    via gRPC (EmbeddingClient).

Supported providers:
- OpenAI (text-embedding-3-small)
- Voyage AI (voyage-3) - Anthropic recommended

Usage:
    from catchup_ai.core.embedding import create_embedding_service

    # Uses provider from EMBEDDING_PROVIDER env var
    service = create_embedding_service()
    result = service.embed_text("Hello, world!")

    # Result includes: vector, model, provider, tokens_used
    print(result.provider)  # "openai" or "voyage"
"""

from .factory import create_embedding_service, get_embedding_service
from .openai_adapter import OpenAIEmbeddingAdapter
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
    # Exceptions
    "EmbeddingError",
    "RateLimitError",
    "TokenLimitError",
]
