"""gRPC client for backend EmbeddingService.

This client communicates with catchup-feed-backend's EmbeddingService
to store embeddings and perform similarity searches.
"""

from dataclasses import dataclass
from typing import Protocol

import grpc
import structlog

from catchup_ai.api.grpc.generated.embedding import (
    EmbeddingServiceStub,
    SearchSimilarRequest,
    SearchSimilarResponse,
    StoreEmbeddingRequest,
    StoreEmbeddingResponse,
)
from catchup_ai.infra.config.settings import BackendSettings, get_settings

logger = structlog.get_logger(__name__)


@dataclass
class SimilarArticleResult:
    """Result of similarity search."""

    article_id: int
    similarity: float


class EmbeddingClientProtocol(Protocol):
    """Protocol for embedding client implementations."""

    def store_embedding(
        self,
        article_id: int,
        embedding: list[float],
        embedding_type: str,
        provider: str,
        model: str,
        dimension: int,
    ) -> tuple[bool, int | None, str | None]:
        """Store an embedding in the backend.

        Returns:
            Tuple of (success, embedding_id, error_message)
        """
        ...

    def search_similar(
        self,
        embedding: list[float],
        embedding_type: str,
        limit: int = 10,
    ) -> list[SimilarArticleResult]:
        """Search for similar articles.

        Returns:
            List of similar articles with their similarity scores
        """
        ...


class EmbeddingClient:
    """gRPC client for backend EmbeddingService.

    This client connects to catchup-feed-backend's EmbeddingService
    to delegate embedding storage and similarity search operations.

    Example:
        client = EmbeddingClient()
        success, embedding_id, error = client.store_embedding(
            article_id=123,
            embedding=[0.1, 0.2, ...],
            embedding_type="content",
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
        )
    """

    def __init__(self, settings: BackendSettings | None = None) -> None:
        """Initialize the embedding client.

        Args:
            settings: Backend settings. If None, uses default settings.
        """
        self._settings = settings or get_settings().backend
        self._channel: grpc.Channel | None = None
        self._stub: EmbeddingServiceStub | None = None

    def _ensure_connection(self) -> EmbeddingServiceStub:
        """Ensure gRPC connection is established."""
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._settings.grpc_address)
            self._stub = EmbeddingServiceStub(self._channel)
            logger.info(
                "Connected to backend EmbeddingService",
                address=self._settings.grpc_address,
            )
        return self._stub

    def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
            logger.debug("Closed backend gRPC connection")

    def __enter__(self) -> "EmbeddingClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

    def store_embedding(
        self,
        article_id: int,
        embedding: list[float],
        embedding_type: str,
        provider: str,
        model: str,
        dimension: int,
    ) -> tuple[bool, int | None, str | None]:
        """Store an embedding in the backend.

        Args:
            article_id: ID of the article this embedding belongs to
            embedding: The embedding vector
            embedding_type: Type of content ("title", "content", "summary")
            provider: Embedding provider ("openai", "voyage")
            model: Model name used for embedding
            dimension: Dimension of the embedding vector

        Returns:
            Tuple of (success, embedding_id, error_message)
        """
        stub = self._ensure_connection()

        request = StoreEmbeddingRequest(
            article_id=article_id,
            embedding_type=embedding_type,
            provider=provider,
            model=model,
            dimension=dimension,
            embedding=embedding,
        )

        try:
            response: StoreEmbeddingResponse = stub.StoreEmbedding(
                request,
                timeout=self._settings.grpc_timeout,
            )

            if response.success:
                logger.info(
                    "Stored embedding successfully",
                    article_id=article_id,
                    embedding_id=response.embedding_id,
                    embedding_type=embedding_type,
                )
                return True, response.embedding_id, None
            else:
                logger.warning(
                    "Failed to store embedding",
                    article_id=article_id,
                    error=response.error_message,
                )
                return False, None, response.error_message

        except grpc.RpcError as e:
            error_msg = f"gRPC error: {e.code().name} - {e.details()}"
            logger.error(
                "gRPC error while storing embedding",
                article_id=article_id,
                error=error_msg,
            )
            return False, None, error_msg

    def search_similar(
        self,
        embedding: list[float],
        embedding_type: str,
        limit: int = 10,
    ) -> list[SimilarArticleResult]:
        """Search for similar articles.

        Args:
            embedding: Query embedding vector
            embedding_type: Type of embeddings to search against
            limit: Maximum number of results

        Returns:
            List of similar articles with their similarity scores
        """
        stub = self._ensure_connection()

        request = SearchSimilarRequest(
            embedding=embedding,
            embedding_type=embedding_type,
            limit=limit,
        )

        try:
            response: SearchSimilarResponse = stub.SearchSimilar(
                request,
                timeout=self._settings.grpc_timeout,
            )

            results = [
                SimilarArticleResult(
                    article_id=article.article_id,
                    similarity=article.similarity,
                )
                for article in response.articles
            ]

            logger.info(
                "Similarity search completed",
                embedding_type=embedding_type,
                limit=limit,
                results_count=len(results),
            )

            return results

        except grpc.RpcError as e:
            error_msg = f"gRPC error: {e.code().name} - {e.details()}"
            logger.error(
                "gRPC error during similarity search",
                error=error_msg,
            )
            return []
