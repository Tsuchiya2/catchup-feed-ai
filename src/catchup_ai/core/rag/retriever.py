"""Article retriever using vector similarity search.

Retrieves relevant articles from the backend using embedding-based
similarity search.
"""

from dataclasses import dataclass

import structlog

from catchup_ai.core.embedding import EmbeddingService, create_embedding_service
from catchup_ai.infra.config.settings import get_settings
from catchup_ai.infra.grpc.embedding_client import EmbeddingClient, SimilarArticleResult

logger = structlog.get_logger()


@dataclass
class RetrievedArticle:
    """An article retrieved by similarity search."""

    article_id: int
    title: str
    url: str
    content: str
    similarity_score: float

    @classmethod
    def from_similar_result(
        cls, result: SimilarArticleResult, title: str = "", url: str = "", content: str = ""
    ) -> "RetrievedArticle":
        """Create from SimilarArticleResult with additional data."""
        return cls(
            article_id=result.article_id,
            title=title,
            url=url,
            content=content,
            similarity_score=result.similarity,
        )


class ArticleRetriever:
    """Retrieves relevant articles using vector similarity search.

    Uses embedding service to convert queries to vectors,
    then calls backend's SearchSimilar to find matching articles.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        embedding_client: EmbeddingClient | None = None,
    ):
        """Initialize the retriever.

        Args:
            embedding_service: Service for generating embeddings
            embedding_client: Client for backend communication
        """
        self._embedding_service = embedding_service or create_embedding_service()
        self._embedding_client = embedding_client or EmbeddingClient()
        self._settings = get_settings()
        self._logger = logger.bind(component="article_retriever")

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.5,
    ) -> list[RetrievedArticle]:
        """Retrieve articles relevant to a query.

        Args:
            query: Search query text
            limit: Maximum number of articles to return
            min_similarity: Minimum similarity score (0.0-1.0)

        Returns:
            List of retrieved articles sorted by relevance
        """
        self._logger.info("Retrieving articles", query=query[:50], limit=limit)

        # 1. Generate embedding for the query
        try:
            embedding_result = self._embedding_service.embed_text(query)
            query_vector = embedding_result.vector
        except Exception as e:
            self._logger.error("Failed to embed query", error=str(e))
            raise RetrievalError(f"Failed to embed query: {e}") from e

        # 2. Search for similar articles via backend
        try:
            similar_results = self._embedding_client.search_similar(
                embedding=list(query_vector),
                embedding_type="content",
                limit=limit,
            )
        except Exception as e:
            self._logger.error("Failed to search similar articles", error=str(e))
            raise RetrievalError(f"Failed to search: {e}") from e

        # 3. Filter by minimum similarity
        filtered_results = [
            r for r in similar_results if r.similarity >= min_similarity
        ]

        # 4. Convert to RetrievedArticle
        # Note: Backend only returns article_id and similarity.
        # Full article details need to be fetched separately.
        articles = [
            RetrievedArticle(
                article_id=r.article_id,
                title="",  # TODO: Fetch from backend
                url="",  # TODO: Fetch from backend
                content="",  # TODO: Fetch from backend
                similarity_score=r.similarity,
            )
            for r in filtered_results
        ]

        self._logger.info(
            "Articles retrieved",
            total_found=len(similar_results),
            after_filter=len(articles),
        )

        return articles

    def retrieve_by_article_id(
        self,
        article_id: int,
        limit: int = 5,
        min_similarity: float = 0.5,
    ) -> list[RetrievedArticle]:
        """Find articles similar to a given article.

        Args:
            article_id: ID of the source article
            limit: Maximum number of similar articles
            min_similarity: Minimum similarity score

        Returns:
            List of similar articles (excluding the source)

        Note:
            This requires the source article to have an embedding stored.
            Currently not fully implemented - needs backend's GetEmbeddings.
        """
        self._logger.info(
            "Retrieving similar articles",
            article_id=article_id,
            limit=limit,
        )

        # TODO: Implement when backend supports GetEmbeddings
        # 1. Get embedding for article_id from backend
        # 2. Use that embedding to search for similar articles
        # 3. Filter out the source article

        raise NotImplementedError(
            "Search by article_id not yet implemented. "
            "Use retrieve() with query text instead."
        )

    def close(self):
        """Close the embedding client connection."""
        self._embedding_client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class RetrievalError(Exception):
    """Error during article retrieval."""

    pass
