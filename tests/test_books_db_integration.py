"""Real-PostgreSQL (pgvector) integration tests for BookStore, gated by

TEST_DATABASE_URL (same convention as test_db_integration.py: unset = skip).
Run against a throwaway pgvector/pgvector:pg18 container.

Schema note: the books / book_chunks DDL below is copied from
pulse-phase2-design.md §4. The backend migration that creates these tables
does not exist yet — THIS DDL IS THE REFERENCE the backend migration must
implement verbatim (embedding is vector(1024), D-12: bge-m3). The tests
create it in a throwaway schema only because the Python side must not own
table creation in production (db.py raises SchemaMissingError instead).

Embeddings are deterministic fakes (1024-dim); no Ollama call happens here.
"""

import math
import os
from collections.abc import Iterator

import psycopg
import pytest

from pulse_books.db import BookStore, Chunk
from pulse_books.embedding import EMBEDDING_DIM
from pulse_books.errors import SchemaMissingError

DSN = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DSN, reason="TEST_DATABASE_URL not set; skipping real-postgres tests"
)

SCHEMA = "pulse_books_it"

# Copied from pulse-phase2-design.md §4 — the reference for the backend
# migration (see module docstring). Keep in sync with the design doc.
BOOKS_DDL = """
CREATE TABLE books (
  id          bigserial PRIMARY KEY,
  title       text NOT NULL,
  file_path   text NOT NULL,
  imported_at timestamptz NOT NULL DEFAULT now()
)"""

BOOK_CHUNKS_DDL = """
CREATE TABLE book_chunks (
  id        bigserial PRIMARY KEY,
  book_id   bigint NOT NULL REFERENCES books,
  position  int NOT NULL,
  content   text NOT NULL,
  embedding vector(1024),
  UNIQUE (book_id, position)
)"""


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(DSN, autocommit=True) as connection:
        # The extension lives at database level (U-24: enabled by migration
        # in production); installing into public keeps the vector type
        # visible from the throwaway schema via search_path.
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector SCHEMA public")
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        connection.execute(f"CREATE SCHEMA {SCHEMA}")
        connection.execute(f"SET search_path TO {SCHEMA}, public")
        connection.execute(BOOKS_DDL)
        connection.execute(BOOK_CHUNKS_DDL)
        try:
            yield connection
        finally:
            connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


@pytest.fixture
def store(conn: psycopg.Connection) -> BookStore:
    return BookStore(conn)


def unit_vector(direction: int) -> list[float]:
    """A deterministic 1024-dim unit vector along one axis."""
    vector = [0.0] * EMBEDDING_DIM
    vector[direction] = 1.0
    return vector


def blend(a: int, b: int, weight: float) -> list[float]:
    """A unit vector between axes a and b (cosine to axis a = weight-ish)."""
    vector = [0.0] * EMBEDDING_DIM
    norm = math.sqrt(weight**2 + (1.0 - weight) ** 2)
    vector[a] = weight / norm
    vector[b] = (1.0 - weight) / norm
    return vector


def count_rows(conn: psycopg.Connection, table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
    assert row is not None
    return int(row[0])


def test_ingest_writes_book_and_chunks(conn: psycopg.Connection, store: BookStore) -> None:
    result = store.replace_book(
        "Learning Go",
        "/books/learning-go.pdf",
        [
            Chunk(content="chapter one", embedding=unit_vector(0)),
            Chunk(content="chapter two", embedding=unit_vector(1)),
        ],
    )

    assert result.replaced is False
    assert result.chunk_count == 2
    rows = conn.execute(
        "SELECT position, content FROM book_chunks WHERE book_id = %s ORDER BY position",
        (result.book_id,),
    ).fetchall()
    assert rows == [(0, "chapter one"), (1, "chapter two")]
    book = conn.execute(
        "SELECT title, file_path FROM books WHERE id = %s", (result.book_id,)
    ).fetchone()
    assert book == ("Learning Go", "/books/learning-go.pdf")


def test_reingest_same_pdf_replaces_chunks_and_keeps_book_id(
    conn: psycopg.Connection, store: BookStore
) -> None:
    """Idempotent re-ingest: same file_path -> same book row, fresh chunks."""
    first = store.replace_book(
        "Learning Go",
        "/books/learning-go.pdf",
        [Chunk(content=f"old {i}", embedding=unit_vector(i)) for i in range(3)],
    )

    second = store.replace_book(
        "Learning Go (2nd ed)",
        "/books/learning-go.pdf",
        [Chunk(content=f"new {i}", embedding=unit_vector(i)) for i in range(2)],
    )

    assert second.replaced is True
    assert second.book_id == first.book_id  # stable id for future references
    assert count_rows(conn, "books") == 1
    assert count_rows(conn, "book_chunks") == 2  # no orphans from the first run
    contents = [
        row[0]
        for row in conn.execute(
            "SELECT content FROM book_chunks ORDER BY position"
        ).fetchall()
    ]
    assert contents == ["new 0", "new 1"]
    title = conn.execute("SELECT title FROM books WHERE id = %s", (second.book_id,)).fetchone()
    assert title == ("Learning Go (2nd ed)",)


def test_different_pdfs_coexist(conn: psycopg.Connection, store: BookStore) -> None:
    store.replace_book("Book A", "/books/a.pdf", [Chunk("a", unit_vector(0))])
    store.replace_book("Book B", "/books/b.pdf", [Chunk("b", unit_vector(1))])

    assert count_rows(conn, "books") == 2
    assert count_rows(conn, "book_chunks") == 2


def test_search_orders_by_cosine_similarity(store: BookStore) -> None:
    store.replace_book(
        "Learning Go",
        "/books/learning-go.pdf",
        [
            Chunk(content="unrelated appendix", embedding=unit_vector(5)),
            Chunk(content="channels in depth", embedding=unit_vector(0)),
            Chunk(content="goroutines overview", embedding=blend(0, 1, 0.8)),
        ],
    )

    hits = store.search(unit_vector(0), top_k=2)

    assert [hit.content for hit in hits] == ["channels in depth", "goroutines overview"]
    assert hits[0].similarity == pytest.approx(1.0)
    assert hits[0].similarity > hits[1].similarity > 0.5
    assert hits[0].book_title == "Learning Go"
    assert hits[0].position == 1


def test_search_top_k_limits_results(store: BookStore) -> None:
    store.replace_book(
        "Learning Go",
        "/books/learning-go.pdf",
        [Chunk(content=f"chunk {i}", embedding=unit_vector(i)) for i in range(5)],
    )

    assert len(store.search(unit_vector(0), top_k=3)) == 3


def test_search_empty_table_returns_nothing(store: BookStore) -> None:
    assert store.search(unit_vector(0)) == []


def test_missing_tables_raise_operator_error(conn: psycopg.Connection, store: BookStore) -> None:
    """The Python side does not own the schema: a missing table must say so."""
    conn.execute("DROP TABLE book_chunks")
    conn.execute("DROP TABLE books")

    with pytest.raises(SchemaMissingError, match="backend のマイグレーション適用が必要"):
        store.replace_book("t", "/books/t.pdf", [Chunk("x", unit_vector(0))])
    with pytest.raises(SchemaMissingError, match="backend のマイグレーション適用が必要"):
        store.search(unit_vector(0))
