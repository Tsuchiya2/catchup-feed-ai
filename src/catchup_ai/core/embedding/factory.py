"""Embedding service factory.

Creates the appropriate embedding service based on configuration.
This enables easy switching between providers (OpenAI, Voyage, etc.)
without changing application code.

Usage:
    from catchup_ai.core.embedding import create_embedding_service

    # Uses provider from EMBEDDING_PROVIDER env var
    service = create_embedding_service()

    # Or specify explicitly
    service = create_embedding_service(provider="voyage")
"""

import structlog

from catchup_ai.infra.config.settings import EmbeddingProvider, get_settings

from .openai_adapter import OpenAIEmbeddingAdapter
from .service import EmbeddingService

logger = structlog.get_logger()


def create_embedding_service(
    provider: str | EmbeddingProvider | None = None,
) -> EmbeddingService:
    """Create an embedding service instance based on configuration.

    This factory function implements the Strategy Pattern, allowing
    the application to switch between embedding providers at runtime
    based on configuration.

    Args:
        provider: Embedding provider to use. If None, uses EMBEDDING_PROVIDER
                  from environment. Options: "openai", "voyage"

    Returns:
        An instance of EmbeddingService

    Raises:
        ValueError: If the specified provider is not supported

    Example:
        # Use configured provider (from .env)
        service = create_embedding_service()

        # Explicitly use OpenAI
        service = create_embedding_service("openai")

        # Explicitly use Voyage (Anthropic recommended)
        service = create_embedding_service("voyage")
    """
    settings = get_settings()

    # Determine provider
    if provider is None:
        provider = settings.embedding.provider
    elif isinstance(provider, str):
        provider = EmbeddingProvider(provider.lower())

    logger.info("Creating embedding service", provider=provider.value)

    # Create appropriate adapter
    if provider == EmbeddingProvider.OPENAI:
        return OpenAIEmbeddingAdapter()

    elif provider == EmbeddingProvider.VOYAGE:
        # Lazy import to avoid dependency when not using Voyage
        from .voyage_adapter import VoyageEmbeddingAdapter

        return VoyageEmbeddingAdapter()

    else:
        raise ValueError(
            f"Unsupported embedding provider: {provider}. "
            f"Supported providers: {[p.value for p in EmbeddingProvider]}"
        )


# Convenience alias
get_embedding_service = create_embedding_service
