"""Article Vector Repository.

Handles storage and retrieval of article embeddings using pgvector.
Provides semantic search functionality via cosine similarity.
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from catchup_ai.infra.db.models import Article

logger = structlog.get_logger()


@dataclass
class SimilarArticleResult:
    """Result of a similarity search."""

    article_id: int
    title: str
    url: str
    similarity_score: float
    snippet: str | None = None


class ArticleVectorRepository:
    """Repository for article embeddings.

    Provides methods to:
    - Store embeddings for articles
    - Search for similar articles by vector
    - Search for similar articles by text query
    """

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self._session = session
        self._logger = logger.bind(repository="article_vector")

    def store_embedding(
        self,
        article_id: int,
        embedding: list[float],
    ) -> bool:
        """Store embedding vector for an article.

        Args:
            article_id: ID of the article
            embedding: Embedding vector (1536 dimensions)

        Returns:
            True if successful, False if article not found
        """
        article = self._session.get(Article, article_id)
        if article is None:
            self._logger.warning("Article not found", article_id=article_id)
            return False

        article.embedding = embedding
        self._session.flush()

        self._logger.info(
            "Embedding stored",
            article_id=article_id,
            dimension=len(embedding),
        )
        return True

    def store_embeddings_batch(
        self,
        embeddings: list[tuple[int, list[float]]],
    ) -> int:
        """Store embeddings for multiple articles.

        Args:
            embeddings: List of (article_id, embedding) tuples

        Returns:
            Number of successfully stored embeddings
        """
        success_count = 0
        for article_id, embedding in embeddings:
            if self.store_embedding(article_id, embedding):
                success_count += 1

        self._logger.info(
            "Batch embeddings stored",
            total=len(embeddings),
            success=success_count,
        )
        return success_count

    def search_similar_by_vector(
        self,
        query_vector: list[float],
        limit: int = 10,
        min_similarity: float = 0.5,
    ) -> list[SimilarArticleResult]:
        """Search for similar articles using a query vector.

        Uses cosine similarity via pgvector's <=> operator.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0.0 - 1.0)

        Returns:
            List of similar articles sorted by similarity (descending)
        """
        # pgvector's <=> returns cosine distance (1 - similarity)
        # So we calculate similarity as 1 - distance
        query = text("""
            SELECT
                id,
                title,
                url,
                1 - (embedding <=> :query_vector::vector) as similarity,
                LEFT(summary, 200) as snippet
            FROM articles
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> :query_vector::vector) >= :min_similarity
            ORDER BY embedding <=> :query_vector::vector
            LIMIT :limit
        """)

        result = self._session.execute(
            query,
            {
                "query_vector": str(query_vector),
                "min_similarity": min_similarity,
                "limit": limit,
            },
        )

        articles = [
            SimilarArticleResult(
                article_id=row.id,
                title=row.title,
                url=row.url,
                similarity_score=float(row.similarity),
                snippet=row.snippet,
            )
            for row in result
        ]

        self._logger.debug(
            "Similar articles found",
            count=len(articles),
            min_similarity=min_similarity,
        )

        return articles

    def search_similar_by_article_id(
        self,
        article_id: int,
        limit: int = 10,
        min_similarity: float = 0.5,
    ) -> list[SimilarArticleResult]:
        """Search for articles similar to a given article.

        Args:
            article_id: ID of the reference article
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold

        Returns:
            List of similar articles (excluding the reference article)
        """
        article = self._session.get(Article, article_id)
        if article is None or article.embedding is None:
            self._logger.warning(
                "Article not found or has no embedding",
                article_id=article_id,
            )
            return []

        # Search and exclude the reference article
        results = self.search_similar_by_vector(
            query_vector=list(article.embedding),
            limit=limit + 1,  # +1 to account for excluding self
            min_similarity=min_similarity,
        )

        # Filter out the reference article
        return [r for r in results if r.article_id != article_id][:limit]

    def get_articles_without_embedding(
        self,
        limit: int = 100,
    ) -> list[Article]:
        """Get articles that don't have embeddings yet.

        Useful for batch processing new articles.

        Args:
            limit: Maximum number of articles to return

        Returns:
            List of Article objects without embeddings
        """
        stmt = (
            select(Article)
            .where(Article.embedding.is_(None))
            .order_by(Article.created_at.desc())
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())

    def count_articles_with_embedding(self) -> int:
        """Count articles that have embeddings.

        Returns:
            Number of articles with embeddings
        """
        stmt = select(Article).where(Article.embedding.isnot(None))
        result = self._session.execute(stmt)
        return len(list(result.scalars().all()))

    def update_category(self, article_id: int, category: str) -> bool:
        """Update the category of an article.

        Args:
            article_id: ID of the article
            category: Category name

        Returns:
            True if successful, False if article not found
        """
        article = self._session.get(Article, article_id)
        if article is None:
            return False

        article.category = category
        self._session.flush()
        return True
