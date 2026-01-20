"""SQLAlchemy models for catchup-ai.

These models map to the existing catchup-feed-backend PostgreSQL tables,
with additional pgvector support for embeddings.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Source(Base):
    """RSS/Web source model.

    Maps to existing 'sources' table in catchup-feed-backend.
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source_type: Mapped[str] = mapped_column(String(20), default="RSS")
    scraper_config: Mapped[dict | None] = mapped_column(JSONB)

    # Relationship
    articles: Mapped[list["Article"]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<Source(id={self.id}, name='{self.name}')>"


class Article(Base):
    """Article model with embedding support.

    Maps to existing 'articles' table in catchup-feed-backend,
    with additional columns for AI features:
    - embedding: vector(1536) for semantic search
    - category: classification result
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # AI-specific columns (added by catchup-ai migration)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    category: Mapped[str | None] = mapped_column(String(50))

    # Relationship
    source: Mapped["Source"] = relationship(back_populates="articles")

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title='{self.title[:30]}...')>"

    @property
    def has_embedding(self) -> bool:
        """Check if article has an embedding."""
        return self.embedding is not None


# pgvector index for cosine similarity search
# IVFFlat is efficient for approximate nearest neighbor search
Index(
    "idx_articles_embedding",
    Article.embedding,
    postgresql_using="ivfflat",
    postgresql_with={"lists": 100},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
