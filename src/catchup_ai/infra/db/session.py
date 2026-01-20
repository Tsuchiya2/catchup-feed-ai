"""Database session management.

Provides connection pooling and session factory for SQLAlchemy.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from catchup_ai.infra.config.settings import get_settings


def get_engine():
    """Create SQLAlchemy engine with connection pooling."""
    settings = get_settings()
    return create_engine(
        settings.database.url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before use
        echo=settings.debug,  # Log SQL queries in debug mode
    )


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup.

    Usage:
        with get_session() as session:
            articles = session.query(Article).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_dependency() -> Generator[Session, None, None]:
    """Dependency injection helper for getting database sessions.

    Usage (for frameworks like FastAPI):
        @app.get("/articles")
        def get_articles(session: Session = Depends(get_session_dependency)):
            return session.query(Article).all()
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
